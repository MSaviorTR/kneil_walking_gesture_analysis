"""
KNEIL 3D motion viewer in Python + MuJoCo with on-device V4 forest decisions.
   kneil_viewer 1.0, 23 Nov 2026

Usage:
    python viewer/kneil_viewer.py --list
    python viewer/kneil_viewer.py walk_healthy
    python viewer/kneil_viewer.py walk_healthy --render cache/viewer/walk_healthy.png --t 10.0
    python viewer/kneil_viewer.py walk_healthy --frames cache/viewer/frames_walk --fps 5
    python viewer/kneil_viewer.py --summary-table
    python viewer/kneil_viewer.py --verify-c
"""
import argparse
import ctypes
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from fractions import Fraction

import numpy as np
import mujoco
from scipy.signal import butter, resample_poly, sosfilt

# Ensure pipeline/ is importable without modifying pipeline files
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_DIR = os.path.join(REPO_ROOT, 'pipeline')
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

import config
import kneil_v1 as K
import camargo_replay as CR

VERSION = 'kneil_viewer 1.2'
FS_OUT = 50.0
WIN_S = 4.0
HOP_S = 1.0
FOOT_BOTTOM_OFFSET = 0.056  # ankle_y - (0.030 capsule center + 0.026 radius)
OLD_HTML_PATH = r'C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\sims_html\KNEIL motion viewer.html'
CAMARGO_AB07_ZIP = os.path.join(config.DATA_ROOT, 'Camargo et. al. 2021', 'Data', 'AB07.zip')
CACHE_DIR = os.path.join(config.CACHE, 'viewer')
MOTIONS_CACHE = os.path.join(CACHE_DIR, 'motions')
LOG_PATH = os.path.join(CACHE_DIR, 'viewer_log.txt')

# Exact V2 class names, labels and colours from kneil_firmware/pc_app/kneil/protocol.py
CLASS_NAMES_V2 = (
    'walking', 'stairs_up', 'stairs_down', 'still', 'lying',
    'sit_to_stand', 'stand_to_sit', 'bed_transfer',
)
CLASS_LABELS_V2 = (
    'walking', 'stairs up', 'stairs down', 'still', 'lying',
    'sit-to-stand', 'stand-to-sit', 'bed transfer',
)
CLASS_COLOURS_V2 = (
    '#2e9e44', '#ff9a1f', '#c65102', '#2166d6', '#8e44ad',
    '#f4d03f', '#c9a227', '#8b5a2b',
)
POSTURE_NAMES = ('unknown', 'sitting', 'standing')
NONE_COLOUR = '#d0d0d0'
EXTRA_COLOURS = {
    'ramp_up': '#1abc9c',
    'ramp_down': '#16a085',
}

# Friendly short aliases for common motions
ALIASES = {
    'walk_healthy': 'old_22_walk_healthy',
    'walk_fast': 'v16_walk_fast',
    'stairs_up': 'old_28_stairs_up_healthy',
    'stairs_down': 'old_29_stairs_down_healthy',
    'ramp_up': 'camargo_ramp_steep',
    'sit_to_stand': 'old_23_sitstand_healthy',
    'bed_transfer': 'old_36_bed_healthy',
}


def log_msg(msg):
    os.makedirs(CACHE_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f'[{ts}] {msg}\n')


# =============================================================================
# C library (kneil_tinyml v2.0) via ctypes
# =============================================================================
class KneilMetricsStruct(ctypes.Structure):
    """Exact mirror of kneil_metrics_t in kneil_tinyml/include/kneil_tinyml.h."""
    _fields_ = [
        ('windows_by_class', ctypes.c_uint32 * 8),
        ('windows_sitting', ctypes.c_uint32),
        ('windows_standing', ctypes.c_uint32),
        ('windows_still_unknown', ctypes.c_uint32),
        ('n_sit_to_stand', ctypes.c_uint16),
        ('n_stand_to_sit', ctypes.c_uint16),
        ('n_bed_transfer', ctypes.c_uint16),
        ('sts_windows', ctypes.c_uint32),
        ('cadence_sum', ctypes.c_float),
        ('cadence_n', ctypes.c_uint32),
        ('stairs_cadence_sum', ctypes.c_float),
        ('stairs_cadence_n', ctypes.c_uint32),
        ('sit_tilt_sum', ctypes.c_float),
        ('sit_tilt_n', ctypes.c_uint32),
        ('walk_peak_sum', ctypes.c_float),
        ('walk_peak_n', ctypes.c_uint32),
        ('steps', ctypes.c_float),
        ('posture', ctypes.c_int),
        ('idx', ctypes.c_int),
        ('since_still', ctypes.c_int),
        ('run_len', ctypes.c_int), ('run_first', ctypes.c_int),
        ('run_na', ctypes.c_int), ('run_nb', ctypes.c_int),
        ('run_gap', ctypes.c_int), ('run_last', ctypes.c_int),
        ('run_still_before', ctypes.c_int), ('run_still_after', ctypes.c_int),
        ('pending', ctypes.c_int), ('pending_until', ctypes.c_int),
        ('pending_first', ctypes.c_int), ('pending_na', ctypes.c_int),
        ('pending_nb', ctypes.c_int), ('pending_len', ctypes.c_int),
        ('bed_len', ctypes.c_int), ('bed_gap', ctypes.c_int), ('bed_last', ctypes.c_int),
        ('h_n', ctypes.c_int), ('h_cls', ctypes.c_int * 2),
        ('h_stride', ctypes.c_float * 2), ('h_tilt', ctypes.c_float * 2),
        ('h_peak', ctypes.c_float * 2),
    ]


_C_LIB = None


def get_c_lib():
    """Build (if needed) and load the kneil_tinyml v2.0 C library DLL."""
    global _C_LIB
    if _C_LIB is not None:
        return _C_LIB
    os.makedirs(CACHE_DIR, exist_ok=True)
    so = os.path.join(CACHE_DIR, 'libkneil_v4' + ('.dll' if os.name == 'nt' else '.so'))
    srcs = [os.path.join(config.TINYML, 'src', f)
            for f in ('kneil_features.c', 'kneil_classifier.c', 'kneil_metrics.c')]
    inc = os.path.join(config.TINYML, 'include')
    need_build = not os.path.exists(so)
    if not need_build:
        so_m = os.path.getmtime(so)
        for p in srcs + [os.path.join(inc, 'kneil_tinyml.h'), os.path.join(inc, 'kneil_model_info.h')]:
            if os.path.exists(p) and os.path.getmtime(p) > so_m:
                need_build = True
                break
    if need_build:
        flags = ['-static-libgcc'] if os.name == 'nt' else ['-fPIC']
        cmd = ['gcc', '-O2', '-std=c99', '-shared', *flags, '-I' + inc, *srcs, '-o', so, '-lm']
        subprocess.check_call(cmd)
        log_msg(f'Built C library: {so}')
    lib = ctypes.CDLL(so)
    F = ctypes.c_float
    P = ctypes.POINTER(F)
    lib.kneil_classifier_init.argtypes = [ctypes.c_void_p]
    lib.kneil_classifier_push.argtypes = [ctypes.c_void_p, F, F, F]
    lib.kneil_classifier_push.restype = ctypes.c_int
    lib.kneil_classifier_raw_class.argtypes = [ctypes.c_void_p]
    lib.kneil_classifier_raw_class.restype = ctypes.c_int
    lib.kneil_classifier_vote.argtypes = [ctypes.c_void_p]
    lib.kneil_classifier_vote.restype = F
    lib.kneil_classifier_proba.argtypes = [ctypes.c_void_p, P]
    lib.kneil_metrics_reset.argtypes = [ctypes.c_void_p]
    lib.kneil_metrics_update.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    lib.kneil_metrics_summary.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    _C_LIB = lib
    return lib


def chip_lowpass_6hz(acc_50hz):
    """2nd-order causal 6 Hz Butterworth low-pass primed at sample 0 (matches kneil_tinyml)."""
    sos = butter(2, 6.0, fs=FS_OUT, output='sos')
    x = np.asarray(acc_50hz, dtype=np.float64)
    if len(x) == 0:
        return x.astype(np.float32)
    out = np.empty_like(x)
    from scipy.signal import sosfilt_zi
    zi_unit = sosfilt_zi(sos)
    for k in range(3):
        out[:, k], _ = sosfilt(sos, x[:, k], zi=zi_unit * x[0, k])
    return out.astype(np.float32)


def run_c_classifier(acc_50hz):
    """Run 50 Hz implant acceleration (g, shape Nx3) through kneil_tinyml v2.0 C library.
    Returns dict with per-window arrays (t_end, rule_cls, raw_cls, vote, posture,
    ev_sts, ev_s2s, ev_bed, proba) and final 40-byte summary_bytes."""
    lib = get_c_lib()
    clf = ctypes.create_string_buffer(8192)
    met = KneilMetricsStruct()
    lib.kneil_classifier_init(clf)
    lib.kneil_metrics_reset(ctypes.byref(met))
    pr = (ctypes.c_float * 8)()

    t_end, rule_cls, raw_cls, vote, posture = [], [], [], [], []
    ev_sts, ev_s2s, ev_bed, proba = [], [], [], []

    a = np.asarray(acc_50hz, dtype=np.float32)
    for i in range(len(a)):
        r = lib.kneil_classifier_push(clf, float(a[i, 0]), float(a[i, 1]), float(a[i, 2]))
        if r >= 0:
            sts0, s2s0, bed0 = int(met.n_sit_to_stand), int(met.n_stand_to_sit), int(met.n_bed_transfer)
            lib.kneil_metrics_update(ctypes.byref(met), clf, int(r))
            lib.kneil_classifier_proba(clf, pr)
            t_end.append((i + 1) / FS_OUT)
            rule_cls.append(int(r))
            raw_cls.append(int(lib.kneil_classifier_raw_class(clf)))
            vote.append(float(lib.kneil_classifier_vote(clf)))
            posture.append(int(met.posture))
            ev_sts.append(int(met.n_sit_to_stand) - sts0)
            ev_s2s.append(int(met.n_stand_to_sit) - s2s0)
            ev_bed.append(int(met.n_bed_transfer) - bed0)
            proba.append([float(x) for x in pr])

    sbuf = ctypes.create_string_buffer(40)
    lib.kneil_metrics_summary(ctypes.byref(met), sbuf)
    return dict(
        t_end=np.array(t_end, np.float32),
        rule_cls=np.array(rule_cls, np.int16),
        raw_cls=np.array(raw_cls, np.int16),
        vote=np.array(vote, np.float32),
        posture=np.array(posture, np.int8),
        ev_sts=np.array(ev_sts, np.int8),
        ev_s2s=np.array(ev_s2s, np.int8),
        ev_bed=np.array(ev_bed, np.int8),
        proba=np.array(proba, np.float32) if proba else np.zeros((0, 8), np.float32),
        summary_bytes=bytes(sbuf.raw),
        n_sts_total=int(met.n_sit_to_stand),
        n_s2s_total=int(met.n_stand_to_sit),
        n_bed_total=int(met.n_bed_transfer),
    )


# =============================================================================
# Label mapping (raw/old labels -> V2 8-class id or -1 / ramp)
# =============================================================================
def map_label_to_v2(name):
    s = str(name).lower().strip()
    if s in ('walking', 'walk', 'turn'):
        return 0
    if s == 'stairs_up':
        return 1
    if s == 'stairs_down':
        return 2
    if s in ('still', 'sitting', 'standing'):
        return 3
    if s in ('lying', 'lying_supine', 'lying_side'):
        return 4
    if s == 'sit_to_stand':
        return 5
    if s == 'stand_to_sit':
        return 6
    if s in ('bed_transfer', 'rolling', 'sit_up', 'lie_down'):
        return 7
    return -1  # e.g. ramp_up, ramp_down


# =============================================================================
# Kinematics helper: reconstruct MuJoCo Q from 3D points (for old HTML viewer)
# =============================================================================
_OSIM_CACHE = None


def get_osim():
    global _OSIM_CACHE
    if _OSIM_CACHE is None:
        _OSIM_CACHE = K.read_osim(K.fetch('osim', folder=config.OPENSIM_DIR))
    return _OSIM_CACHE


def _rot_zxy_angles(R):
    """Decompose R = Rz(a) @ Rx(b) @ Ry(c) into (a, b, c) in radians.
    R[2, 1] = sin(b); R[0, 1] = -sin(a)*cos(b); R[1, 1] = cos(a)*cos(b);
    R[2, 0] = -cos(b)*sin(c); R[2, 2] = cos(b)*cos(c)."""
    sb = np.clip(R[2, 1], -1.0, 1.0)
    b = np.arcsin(sb)
    cb = np.cos(b)
    if abs(cb) > 1e-4:
        a = np.arctan2(-R[0, 1], R[1, 1])
        c = np.arctan2(-R[2, 0], R[2, 2])
    else:
        a = np.arctan2(R[1, 0], R[0, 0])
        c = 0.0
    return float(a), float(b), float(c)


def points_to_Q(P, names, dev_side='r'):
    """Fit MuJoCo kneil_v1 generalized coordinates Q (N x m.nq) from 3D points P (N x J x 3)."""
    osim = get_osim()
    jidx = {n: i for i, n in enumerate(names)}
    # Estimate segment lengths from median distances
    L_fem = float(np.median(np.linalg.norm(P[:, jidx['knee_r']] - P[:, jidx['hip_r']], axis=1)))
    L_tib = float(np.median(np.linalg.norm(P[:, jidx['ankle_r']] - P[:, jidx['knee_r']], axis=1)))
    pel_w = float(np.median(np.linalg.norm(P[:, jidx['hip_r']] - P[:, jidx['hip_l']], axis=1)))
    ref_pel_w = float(np.linalg.norm(osim['hip_r'] - osim['hip_l']))
    k_pel = pel_w / max(ref_pel_w, 1e-6)
    m, info = K.build_model(osim, femur=L_fem, tibia=L_tib, pelvis=k_pel, imu_side=dev_side)
    idx = K.qidx(m)
    N = len(P)
    Q = np.zeros((N, m.nq), dtype=np.float64)

    p_pel = P[:, jidx['pelvis']]
    p_hr = P[:, jidx['hip_r']]
    p_hl = P[:, jidx['hip_l']]
    p_ch = P[:, jidx['chest']]
    p_kr = P[:, jidx['knee_r']]
    p_kl = P[:, jidx['knee_l']]
    p_ar = P[:, jidx['ankle_r']]
    p_al = P[:, jidx['ankle_l']]

    Q[:, idx['pelvis_tx']] = p_pel[:, 0]
    Q[:, idx['pelvis_ty']] = p_pel[:, 1]
    Q[:, idx['pelvis_tz']] = p_pel[:, 2]

    for i in range(N):
        # Pelvis frame: Z = right (hip_r - hip_l), Y = up (chest - pelvis), X = Y x Z
        zp = p_hr[i] - p_hl[i]
        zp /= (np.linalg.norm(zp) + 1e-12)
        yp = p_ch[i] - p_pel[i]
        yp -= (yp @ zp) * zp
        yp /= (np.linalg.norm(yp) + 1e-12)
        xp = np.cross(yp, zp)
        xp /= (np.linalg.norm(xp) + 1e-12)
        R_pel = np.column_stack([xp, yp, zp])
        tilt, lst, rot = _rot_zxy_angles(R_pel)
        Q[i, idx['pelvis_tilt']] = tilt
        Q[i, idx['pelvis_list']] = lst
        Q[i, idx['pelvis_rotation']] = rot

        for s, ph, pk, pa in (('r', p_hr[i], p_kr[i], p_ar[i]), ('l', p_hl[i], p_kl[i], p_al[i])):
            u_fem = pk - ph
            u_fem /= (np.linalg.norm(u_fem) + 1e-12)
            u_tib = pa - pk
            u_tib /= (np.linalg.norm(u_tib) + 1e-12)
            cos_k = np.clip(float(u_fem @ u_tib), -1.0, 1.0)
            k_ang = -np.arccos(cos_k)  # negative = knee flexion
            Q[i, idx['knee_angle_' + s]] = k_ang

            # Femur frame in pelvis coordinates: local -Y is femur direction (hip -> knee)
            d_fem = R_pel.T @ u_fem
            d_tib = R_pel.T @ u_tib
            y_f = -d_fem
            cross_ft = np.cross(d_fem, d_tib)
            cn = np.linalg.norm(cross_ft)
            if cn > 0.12:
                # Knee flexes backward -> d_fem x d_tib points along -Z_fem
                z_f = -cross_ft / cn
                if z_f[2] < 0:
                    z_f = -z_f
            else:
                z_f = np.array([0.0, 0.0, 1.0])
            z_f = z_f - (z_f @ y_f) * y_f
            z_f /= (np.linalg.norm(z_f) + 1e-12)
            x_f = np.cross(y_f, z_f)
            R_hip = np.column_stack([x_f, y_f, z_f])
            hf, ha, hr = _rot_zxy_angles(R_hip)
            # Note: hip_adduction_l and hip_rotation_l in OpenSim have mirrored axes
            if s == 'l':
                ha = -ha
                hr = -hr
            Q[i, idx['hip_flexion_' + s]] = hf
            Q[i, idx['hip_adduction_' + s]] = ha
            Q[i, idx['hip_rotation_' + s]] = hr

    # Unwrap angular coordinates to avoid 2*pi jumps
    for name, a in idx.items():
        if not name.startswith('pelvis_t') and not name.startswith('knee_t'):
            Q[:, a] = np.unwrap(Q[:, a])
    Q = K.set_knee_translations(Q, idx, info)
    return Q, dict(femur=L_fem, tibia=L_tib, pelvis=k_pel, imu_side=dev_side)


# =============================================================================
# Catalog of motions (old HTML viewer + Camargo replay + v1.6 generator)
# =============================================================================
_OLD_TRIALS_CACHE = None


def _load_old_html_trials():
    global _OLD_TRIALS_CACHE
    if _OLD_TRIALS_CACHE is None:
        with open(OLD_HTML_PATH, 'r', encoding='utf-8', errors='replace') as f:
            txt = f.read()
        m = re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>', txt, flags=re.S)
        if not m:
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', txt, flags=re.S)
            raw = scripts[0]
        else:
            raw = m.group(1)
        _OLD_TRIALS_CACHE = json.loads(raw)['trials']
    return _OLD_TRIALS_CACHE


def _slug(s, maxlen=28):
    s = re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
    return s[:maxlen].rstrip('_')


CAMARGO_NEW = [
    ('camargo_walk_slow', 'Camargo AB07: level-ground slow walking', 'levelground/ik/levelground_ccw_slow_01_01.mat', 'levelground', None, 27.9),
    ('camargo_walk_normal', 'Camargo AB07: level-ground normal walking', 'levelground/ik/levelground_ccw_normal_01_01.mat', 'levelground', None, 23.9),
    ('camargo_walk_fast', 'Camargo AB07: level-ground fast walking', 'levelground/ik/levelground_ccw_fast_01_01.mat', 'levelground', None, 23.3),
    ('camargo_treadmill_fast', 'Camargo AB07: treadmill fast walking (~1.7 m/s)', 'treadmill/ik/treadmill_07_01.mat', 'treadmill', (55.0, 75.0), 20.0),
    ('camargo_ramp_gentle', 'Camargo AB07: gentle ramp up & down (~5 deg)', 'ramp/ik/ramp_1_r_01_01.mat', 'ramp', None, 19.1),
    ('camargo_ramp_steep', 'Camargo AB07: steep ramp up & down (~11 deg)', 'ramp/ik/ramp_5_r_01_01.mat', 'ramp', None, 19.2),
    ('camargo_stairs_low', 'Camargo AB07: stairs 10.2 cm up & down', 'stair/ik/stair_1_r_01_01.mat', 'stair', None, 15.3),
    ('camargo_stairs_high', 'Camargo AB07: stairs 17.8 cm up & down', 'stair/ik/stair_4_r_01_01.mat', 'stair', None, 16.0),
]

V16_NEW = [
    ('v16_walk_healthy', 'v1.6 generator: healthy older adult walking (1.25 m/s)',
     dict(sex='F', age=70.0, height=1.68, side='r', speed_factor=1.0, stride_factor=1.0, femur_dev=0.0, tibia_dev=0.0, lr_dev=0.0, peak_dev=0.0),
     dict(severity=0.0), 20.0, 101),
    ('v16_walk_fast', 'v1.6 generator: fast walking (~1.72 m/s)',
     dict(sex='M', age=45.0, height=1.76, side='r', speed_factor=1.20, stride_factor=1.05, femur_dev=0.0, tibia_dev=0.0, lr_dev=0.0, peak_dev=0.0),
     dict(severity=0.0), 20.0, 102),
    ('v16_walk_limp_mild', 'v1.6 generator: mild limp walking (severity 0.4)',
     dict(sex='F', age=68.0, height=1.64, side='r', speed_factor=1.0, stride_factor=1.0, femur_dev=0.0, tibia_dev=0.0, lr_dev=0.0, peak_dev=0.0),
     dict(severity=0.4), 20.0, 103),
    ('v16_walk_crutches', 'v1.6 generator: walking with crutches (severity 0.5)',
     dict(sex='M', age=70.0, height=1.72, side='r', speed_factor=1.0, stride_factor=1.0, femur_dev=0.0, tibia_dev=0.0, lr_dev=0.0, peak_dev=0.0),
     dict(severity=0.5, aid='crutches'), 20.0, 104),
]

# Short readable IDs for key old viewer trials
OLD_ID_OVERRIDES = {
    22: 'old_22_walk_healthy',
    23: 'old_23_sitstand_healthy',
    28: 'old_28_stairs_up_healthy',
    29: 'old_29_stairs_down_healthy',
    36: 'old_36_bed_healthy',
}


def in_sample_status(kind, group='', mode=''):
    """Return (is_in_sample: bool, label: str) based on export_v4.py / windows_W4s.npz."""
    g = group.lower()
    if kind == 'old':
        if 'spacer-period' in g or 'persona' in g:
            return False, 'out-of-sample (recomposed AB07)'
        if 'camargo' in g:
            return True, 'training data (in-sample: AB07)'
        if 'caicedo' in g:
            return True, 'training data (in-sample: Caicedo)'
        return True, 'training data (in-sample: v1.6 sim)'
    if kind == 'camargo':
        if mode == 'ramp':
            return True, 'training data (in-sample person AB07; ramps not trained)'
        return True, 'training data (in-sample: AB07)'
    if kind == 'v16':
        return True, 'training data (in-sample: v1.6 generator)'
    return False, 'out-of-sample'


def build_catalog():
    """Return list of dicts describing every available motion (fast, no heavy computation)."""
    cat = []
    if os.path.exists(OLD_HTML_PATH):
        trials = _load_old_html_trials()
        for i, tr in enumerate(trials):
            mid = OLD_ID_OVERRIDES.get(i, f'old_{i:02d}_{_slug(tr["name"], 22)}')
            dur = (tr['n'] - 1) / float(tr['fk'])
            labs = sorted(set(x[0] for x in tr.get('labels', [])))
            grp = tr.get('group', 'Synthetic patients (simulator v1.6)')
            ins, ins_lbl = in_sample_status('old', group=grp)
            cat.append(dict(
                id=mid, name=tr['name'], source='old viewer',
                group=grp, dur=dur, true_labels=labs, kind='old', index=i,
                in_sample=ins, in_sample_label=ins_lbl,
            ))
    for mid, name, suf, mode, tslice, dur in CAMARGO_NEW:
        ins, ins_lbl = in_sample_status('camargo', mode=mode)
        cat.append(dict(
            id=mid, name=name, source='Camargo replay',
            group='Camargo et al. 2021 (AB07 OpenSim IK)',
            dur=dur, true_labels=[mode], kind='camargo', suf=suf, mode=mode, tslice=tslice,
            in_sample=ins, in_sample_label=ins_lbl,
        ))
    for mid, name, subj, cond, dur, seed in V16_NEW:
        ins, ins_lbl = in_sample_status('v16')
        cat.append(dict(
            id=mid, name=name, source='v1.6 generator',
            group='Synthetic v1.6 generator (kneil_v1.py)',
            dur=dur, true_labels=['walking'], kind='v16',
            subj=subj, cond=cond, seed=seed,
            in_sample=ins, in_sample_label=ins_lbl,
        ))
    return cat


def resolve_motion_id(name_or_alias, catalog):
    if name_or_alias in ALIASES:
        name_or_alias = ALIASES[name_or_alias]
    ids = {c['id']: c for c in catalog}
    if name_or_alias in ids:
        return ids[name_or_alias]
    # Substring match fallback
    low = name_or_alias.lower()
    hits = [c for c in catalog if low in c['id'].lower() or low in c['name'].lower()]
    if len(hits) == 1:
        return hits[0]
    raise KeyError(f'Unknown motion "{name_or_alias}". Use --list to see available motions.')


def _align_travel_to_x(Q, idx):
    """Rotate horizontal pelvis trajectory (tx, tz, rotation) around world +Y so the primary
    travel direction aligns with +X and lateral mean sits at Z=0. Leaves gravity and implant
    signals invariant."""
    Q = Q.copy()
    tx = Q[:, idx['pelvis_tx']]
    tz = Q[:, idx['pelvis_tz']]
    # Principal horizontal axis of travel
    pts = np.column_stack([tx - tx.mean(), tz - tz.mean()])
    if np.linalg.norm(pts) < 0.2:
        return Q
    _, _, vt = np.linalg.svd(pts, full_matrices=False)
    axis = vt[0]
    # Orient so early-to-peak elevation (or early-to-mid travel) goes toward +X
    n_half = max(1, len(tx) // 2)
    disp = np.array([tx[n_half] - tx[0], tz[n_half] - tz[0]])
    if float(disp @ axis) < 0:
        axis = -axis
    # Angle alpha such that Ry(alpha) maps axis=(ax, az) -> (+1, 0):
    # x' =  cos(a)*x + sin(a)*z,  z' = -sin(a)*x + cos(a)*z
    # For (ax, az) -> (1, 0): cos(a)=ax, sin(a)=az => a = atan2(az, ax)
    alpha = float(np.arctan2(axis[1], axis[0]))
    ca, sa = np.cos(alpha), np.sin(alpha)
    x0, z0 = tx.mean(), tz.mean()
    dx, dz = tx - x0, tz - z0
    Q[:, idx['pelvis_tx']] = ca * dx + sa * dz
    Q[:, idx['pelvis_tz']] = -sa * dx + ca * dz
    Q[:, idx['pelvis_rotation']] = Q[:, idx['pelvis_rotation']] + alpha
    return Q


def _compute_ankle_trajs(Q, geom):
    """Return (ankle_r, ankle_l) world positions (N x 3) using kneil_v1.build_model."""
    osim = get_osim()
    m, _ = K.build_model(osim, femur=float(geom['femur']), tibia=float(geom['tibia']),
                         pelvis=float(geom['pelvis']), imu_side=geom.get('imu_side', 'r'))
    d = mujoco.MjData(m)
    ar, al = m.site('ankle_r').id, m.site('ankle_l').id
    N = len(Q)
    pr = np.zeros((N, 3))
    pl = np.zeros((N, 3))
    for i in range(N):
        d.qpos[:] = Q[i]
        mujoco.mj_kinematics(m, d)
        pr[i] = d.site_xpos[ar]
        pl[i] = d.site_xpos[al]
    return pr, pl


def _stance_foot_samples(pr, pl, fs=FS_OUT):
    """Return (x, foot_y, z) of the lowest foot during low-vertical-velocity stance samples."""
    use_r = pr[:, 1] <= pl[:, 1]
    p = np.where(use_r[:, None], pr, pl)
    foot_y = p[:, 1] - FOOT_BOTTOM_OFFSET
    vy = np.abs(np.gradient(foot_y, 1.0 / fs))
    stance = vy < 0.12
    if stance.sum() < 10:
        stance = np.ones(len(foot_y), dtype=bool)
    return p[stance, 0], foot_y[stance], p[stance, 2], p[:, 0], foot_y


def _fit_env_to_feet(env, Q, geom):
    """Fit floor, stairs, or ramp surface geometry directly to the motion's stance-foot trajectories."""
    env = dict(env)
    etype = env.get('type', 'floor')
    pr, pl = _compute_ankle_trajs(Q, geom)
    sx, sy, sz, all_x, all_y = _stance_foot_samples(pr, pl)

    if etype in ('floor', 'treadmill'):
        env['floor'] = float(np.median(sy))
        return env

    if etype == 'chair':
        old_floor = float(env.get('floor', 0.0))
        new_floor = float(np.median(sy))
        dy = new_floor - old_floor
        env['floor'] = new_floor
        if 'seat' in env:
            env['seat'] = float(env['seat']) + dy
        return env

    if etype == 'bed':
        return env

    if etype == 'ramp':
        y_lo = float(np.percentile(sy, 5))
        y_hi = float(np.percentile(sy, 95))
        span = max(y_hi - y_lo, 0.05)
        mid = (sy > y_lo + 0.08 * span) & (sy < y_hi - 0.08 * span)
        if mid.sum() >= 10:
            slope, intercept = np.polyfit(sx[mid], sy[mid], 1)
            if abs(slope) > 1e-3:
                x_lo = float((y_lo - intercept) / slope)
                x_hi = float((y_hi - intercept) / slope)
            else:
                x_lo, x_hi = float(sx.min()), float(sx.max())
        else:
            x_lo, x_hi = float(sx.min()), float(sx.max())
        env['floor'] = y_lo
        env['y_lo'] = y_lo
        env['y_hi'] = y_hi
        env['x_lo'] = x_lo
        env['x_hi'] = x_hi
        env['x_min'] = float(min(all_x.min(), x_lo, x_hi) - 1.2)
        env['x_max'] = float(max(all_x.max(), x_lo, x_hi) + 1.2)
        return env

    if etype == 'stairs':
        # Cluster stance heights into discrete step levels (riser >= 7 cm)
        order = np.argsort(sy)
        sy_s, sx_s = sy[order], sx[order]
        clusters = []
        cur_y, cur_x = [sy_s[0]], [sx_s[0]]
        for yv, xv in zip(sy_s[1:], sx_s[1:]):
            if yv - float(np.median(cur_y)) > 0.065:
                clusters.append((np.array(cur_x), np.array(cur_y)))
                cur_y, cur_x = [yv], [xv]
            else:
                cur_y.append(yv)
                cur_x.append(xv)
        clusters.append((np.array(cur_x), np.array(cur_y)))
        # Keep clusters with enough stance samples (filter mid-air transients)
        min_pts = max(3, int(0.005 * len(sy)))
        clusters = [c for c in clusters if len(c[1]) >= min_pts]
        if len(clusters) >= 2:
            # Sort treads by median X so adjacent treads meet cleanly
            levels = []
            for cx, cy in clusters:
                levels.append(dict(
                    x_med=float(np.median(cx)),
                    x_lo=float(np.percentile(cx, 5)),
                    x_hi=float(np.percentile(cx, 95)),
                    y=float(np.median(cy)),
                ))
            levels.sort(key=lambda d: d['x_med'])
            treads = []
            for i, lv in enumerate(levels):
                if i == 0:
                    xa = min(lv['x_lo'] - 0.8, float(all_x.min()) - 0.5)
                else:
                    xa = 0.5 * (levels[i - 1]['x_hi'] + lv['x_lo'])
                if i == len(levels) - 1:
                    xb = max(lv['x_hi'] + 0.8, float(all_x.max()) + 0.5)
                else:
                    xb = 0.5 * (lv['x_hi'] + levels[i + 1]['x_lo'])
                if xb < xa + 0.10:
                    midx = 0.5 * (xa + xb)
                    xa, xb = midx - 0.08, midx + 0.08
                treads.append([round(xa, 4), round(xb, 4), round(lv['y'], 4)])
            env['treads'] = treads
            env.pop('steps', None)
            env['floor'] = float(min(lv['y'] for lv in levels))
        return env

    return env


def prop_surface_y(env, x):
    """Evaluate prop surface elevation Y at horizontal coordinate x (matches _scene_env_xml)."""
    etype = env.get('type', 'floor')
    fy = float(env.get('floor', 0.0))
    if etype == 'stairs':
        treads = env.get('treads')
        if treads:
            for xa, xb, y in treads:
                if min(xa, xb) - 1e-4 <= x <= max(xa, xb) + 1e-4:
                    return float(y)
            mids = [0.5 * (a + b) for a, b, _ in treads]
            return float(treads[int(np.argmin(np.abs(np.array(mids) - x)))][2])
    if etype == 'ramp':
        x_lo, x_hi = float(env['x_lo']), float(env['x_hi'])
        y_lo, y_hi = float(env['y_lo']), float(env['y_hi'])
        if abs(x_hi - x_lo) > 1e-6:
            u = float(np.clip((x - x_lo) / (x_hi - x_lo), 0.0, 1.0))
            return float(y_lo + u * (y_hi - y_lo))
    return fy


def foot_prop_error_cm(data):
    """Return (median_abs_cm, p95_abs_cm, median_signed_cm) of stance foot_y - prop_surface_y."""
    meta = data['meta']
    pr, pl = _compute_ankle_trajs(data['Q'], meta['geom'])
    sx, sy, _, _, _ = _stance_foot_samples(pr, pl)
    env = meta.get('env', {})
    errs = np.array([sy[i] - prop_surface_y(env, sx[i]) for i in range(len(sx))]) * 100.0
    return float(np.median(np.abs(errs))), float(np.percentile(np.abs(errs), 95)), float(np.median(errs))


def _build_env_from_camargo(mode, Q, ankle, idx):
    """Initial env type for Camargo; exact geometry is fitted to stance feet by _fit_env_to_feet."""
    if mode == 'treadmill':
        return dict(type='treadmill', floor=0.0, v=1.6)
    if mode == 'stair':
        return dict(type='stairs', floor=0.0, up=True)
    if mode == 'ramp':
        return dict(type='ramp', floor=0.0)
    return dict(type='floor', floor=0.0)


def load_motion(entry, force_rebuild=False):
    """Load a motion from cache/viewer/motions/<id>.npz, building it once if not cached."""
    os.makedirs(MOTIONS_CACHE, exist_ok=True)
    cpath = os.path.join(MOTIONS_CACHE, f'{entry["id"]}.npz')
    mpath = os.path.join(MOTIONS_CACHE, f'{entry["id"]}.json')
    if not force_rebuild and os.path.exists(cpath) and os.path.exists(mpath):
        with open(mpath, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        if meta.get('cache_ver') == VERSION:
            z = np.load(cpath)
            out = {k: z[k] for k in z.files}
            out['meta'] = meta
            return out

    t0 = time.time()
    kind = entry['kind']
    if kind == 'old':
        tr = _load_old_html_trials()[entry['index']]
        names = tr['names']
        P = np.array(tr['P'], dtype=np.float64).reshape(tr['n'], len(names), 3) / 1000.0
        Q, geom = points_to_Q(P, names, dev_side=tr['dev'])
        t = np.arange(len(Q), dtype=np.float32) / float(tr['fk'])
        acc_100 = np.array(tr['acc'], dtype=np.float64).reshape(-1, 3) / 1000.0
        fr = Fraction(int(FS_OUT), int(tr['fa']))
        acc_50 = resample_poly(acc_100, fr.numerator, fr.denominator, axis=0).astype(np.float32)
        # Align lengths
        n = min(len(Q), len(acc_50))
        Q, t, acc_50 = Q[:n], t[:n], acc_50[:n]
        # Per-sample true labels (50 Hz)
        true_lbl = np.full(n, -1, dtype=np.int16)
        true_names = [''] * n
        for lab, a, b in tr.get('labels', []):
            a50 = max(0, int(round(a * FS_OUT / tr['fa'])))
            b50 = min(n, int(round(b * FS_OUT / tr['fa'])))
            true_lbl[a50:b50] = map_label_to_v2(lab)
            for k in range(a50, b50):
                true_names[k] = lab
        env_fit = _fit_env_to_feet(tr.get('env', dict(type='floor', floor=0.0)), Q, geom)
        meta = dict(
            cache_ver=VERSION,
            id=entry['id'], name=tr['name'], source=entry['source'],
            group=entry['group'], cond=tr.get('cond', ''),
            in_sample=entry['in_sample'], in_sample_label=entry['in_sample_label'],
            env=env_fit,
            geom=geom, dur=float(t[-1]), fs=FS_OUT,
            label_spans=[[lab, a / tr['fa'], b / tr['fa']] for lab, a, b in tr.get('labels', [])],
        )

    elif kind == 'camargo':
        m, info = CR.model_for('ab07')
        idx = K.qidx(m)
        with zipfile.ZipFile(CAMARGO_AB07_ZIP) as zf, tempfile.TemporaryDirectory() as td:
            hits = [n for n in zf.namelist() if n.endswith(entry['suf'])]
            if not hits:
                raise FileNotFoundError(f'Camargo trial {entry["suf"]} not found in {CAMARGO_AB07_ZIP}')
            p_ik = zf.extract(hits[0], td)
            ik = CR.load_table(p_ik)
        t200, Q200 = CR.ik_to_Q(m, info, ik, fs_out=200.0)
        if entry['tslice'] is not None:
            ta, tb = entry['tslice']
            mask = (t200 >= ta) & (t200 <= tb)
            t200 = t200[mask] - t200[mask][0]
            Q200 = Q200[mask]
        rep = CR.replay(m, Q200, 200.0, sensors=('acc_imu',))
        labs200 = CR.kinematic_labels(Q200, idx, rep['ankle'], fs=200.0, mode=entry['mode'])
        # Decimate 200 Hz -> 50 Hz
        acc_50 = resample_poly(rep['acc_imu'], 1, 4, axis=0).astype(np.float32)
        Q = Q200[::4]
        ankle50 = rep['ankle'][::4]
        labs50 = labs200[::4]
        n = min(len(Q), len(acc_50), len(labs50))
        Q, acc_50, ankle50, labs50 = Q[:n], acc_50[:n], ankle50[:n], labs50[:n]
        # Align horizontal travel direction to +X so props and side-3/4 camera match the motion
        if entry['mode'] != 'treadmill':
            Q = _align_travel_to_x(Q, idx)
        t = np.arange(n, dtype=np.float32) / FS_OUT
        true_lbl = np.array([map_label_to_v2(CR.LABELS[k]) for k in labs50], dtype=np.int16)
        # Compact label spans
        spans = []
        if n > 0:
            s0, cur = 0, int(labs50[0])
            for i in range(1, n):
                if int(labs50[i]) != cur:
                    spans.append([CR.LABELS[cur], s0 / FS_OUT, i / FS_OUT])
                    s0, cur = i, int(labs50[i])
            spans.append([CR.LABELS[cur], s0 / FS_OUT, n / FS_OUT])
        geom = dict(femur=info['femur'], tibia=info['tibia'], pelvis=info['pelvis'], imu_side=info['imu_side'])
        env = _fit_env_to_feet(_build_env_from_camargo(entry['mode'], Q, ankle50, idx), Q, geom)
        meta = dict(
            cache_ver=VERSION,
            id=entry['id'], name=entry['name'], source=entry['source'],
            group=entry['group'], cond=f'Camargo et al. 2021 AB07 ({entry["suf"]})',
            in_sample=entry['in_sample'], in_sample_label=entry['in_sample_label'],
            env=env, geom=geom, dur=float(t[-1]), fs=FS_OUT, label_spans=spans,
        )

    elif kind == 'v16':
        osim_dir = config.OPENSIM_DIR
        # Fetch OpenSim files into cache/opensim if needed
        for key in ('ik', 'osim', 'grf'):
            K.fetch(key, folder=osim_dir)
        # Temporarily point K.fetch default? Easier: construct Template with local cwd or patch folder
        old_fetch = K.fetch
        K.fetch = lambda key, folder=osim_dir: old_fetch(key, folder=osim_dir)
        try:
            TP = K.Template()
        finally:
            K.fetch = old_fetch
        rng = np.random.default_rng(entry['seed'])
        sens = dict(yaw=0.0, slope=0.0, roll=0.0, pos=(0.005, -0.025, 0.0),
                    bias=[0.0, 0.0, 0.0], scale=[0.0, 0.0, 0.0], cross=[0.0, 0.0, 0.0],
                    noise_ug=150.0, impact_f=22.0, impact_zeta=0.4)
        res = K.make_trial(TP, entry['subj'], entry['cond'], sens, entry['dur'], rng)
        i100, a100 = K.device_output(res, sens, rng, odr=100)
        acc_50 = resample_poly(a100, 1, 2, axis=0).astype(np.float32)
        Q = res['Q'][i100[::2]]
        n = min(len(Q), len(acc_50))
        Q, acc_50 = Q[:n], acc_50[:n]
        t = np.arange(n, dtype=np.float32) / FS_OUT
        true_lbl = np.zeros(n, dtype=np.int16)  # walking = 0
        k = entry['subj']['height'] / K.H_REF
        geom = dict(
            femur=K.REF['femur'] * k, tibia=K.REF['tibia'] * k,
            pelvis=k, imu_side=entry['subj']['side'],
        )
        env_fit = _fit_env_to_feet(dict(type='floor', floor=0.0, aid=entry['cond'].get('aid')), Q, geom)
        meta = dict(
            cache_ver=VERSION,
            id=entry['id'], name=entry['name'], source=entry['source'],
            group=entry['group'],
            in_sample=entry['in_sample'], in_sample_label=entry['in_sample_label'],
            cond=f'v1.6 make_trial: v={res["p"]["v"]:.2f} m/s, T={res["p"]["T"]:.2f} s, stride={res["p"]["stride"]:.2f} m',
            env=env_fit,
            geom=geom, dur=float(t[-1]), fs=FS_OUT,
            label_spans=[['walking', 0.0, float(t[-1])]],
        )
    else:
        raise ValueError(f'Unknown kind: {kind}')

    acc_lp = chip_lowpass_6hz(acc_50)
    clf = run_c_classifier(acc_50)

    arrays = dict(
        t=t, Q=Q.astype(np.float32), acc=acc_50, acc_lp=acc_lp, true_lbl=true_lbl,
        win_t=clf['t_end'], rule_cls=clf['rule_cls'], raw_cls=clf['raw_cls'],
        vote=clf['vote'], posture=clf['posture'],
        ev_sts=clf['ev_sts'], ev_s2s=clf['ev_s2s'], ev_bed=clf['ev_bed'],
        proba=clf['proba'],
    )
    meta['summary_hex'] = clf['summary_bytes'].hex()
    meta['n_sts_total'] = clf['n_sts_total']
    meta['n_s2s_total'] = clf['n_s2s_total']
    meta['n_bed_total'] = clf['n_bed_total']
    np.savez_compressed(cpath, **arrays)
    with open(mpath, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    log_msg(f'Built & cached {entry["id"]} ({len(t)} frames, {len(clf["rule_cls"])} windows) in {time.time()-t0:.2f}s')
    arrays['meta'] = meta
    return arrays


# =============================================================================
# 3D MuJoCo scene model (visual extension of kneil_v1.build_model)
# =============================================================================
def _scene_env_xml(env):
    """Build simple MuJoCo geoms for floor, chair, stairs, ramp, treadmill, or bed."""
    etype = env.get('type', 'floor')
    fy = float(env.get('floor', 0.0))
    parts = []
    # Floor (Y-up world -> floor plane has normal +Y, i.e. zaxis="0 1 0")
    parts.append(
        f'<geom name="floor" type="plane" pos="0 {fy:.4f} 0" zaxis="0 1 0" size="30 30 0.1" '
        f'material="mat_floor" contype="0" conaffinity="0"/>'
    )
    if etype == 'chair':
        seat = float(env.get('seat', 0.45))
        front = float(env.get('front', 0.0))
        d, w, th = 0.44, 0.46, 0.04
        cx = front - d / 2.0
        parts.append(
            f'<geom name="chair_seat" type="box" pos="{cx:.4f} {seat - th/2:.4f} 0" '
            f'size="{d/2:.4f} {th/2:.4f} {w/2:.4f}" rgba="0.45 0.36 0.28 1" contype="0" conaffinity="0"/>'
        )
        parts.append(
            f'<geom name="chair_back" type="box" pos="{front - d + 0.02:.4f} {seat + 0.24:.4f} 0" '
            f'size="0.02 0.24 {w/2:.4f}" rgba="0.40 0.31 0.24 1" contype="0" conaffinity="0"/>'
        )
        for sx in (front - 0.03, front - d + 0.03):
            for sz in (-w / 2 + 0.03, w / 2 - 0.03):
                parts.append(
                    f'<geom type="cylinder" fromto="{sx:.4f} {fy:.4f} {sz:.4f} {sx:.4f} {seat-th:.4f} {sz:.4f}" '
                    f'size="0.018" rgba="0.30 0.24 0.19 1" contype="0" conaffinity="0"/>'
                )
    elif etype == 'stairs':
        treads = env.get('treads')
        if treads:
            w = 0.55
            for i, (xa, xb, y) in enumerate(treads):
                cx = 0.5 * (xa + xb)
                hx = max(abs(xb - xa) * 0.5, 0.05)
                h = max(y - fy, 0.04)
                parts.append(
                    f'<geom name="step_{i}" type="box" pos="{cx:.4f} {fy + h/2:.4f} 0" '
                    f'size="{hx:.4f} {h/2:.4f} {w:.4f}" rgba="0.62 0.65 0.70 1" contype="0" conaffinity="0"/>'
                )
            # Handrail on far side (-Z)
            if len(treads) >= 2:
                xa0, _, y0 = treads[0]
                _, xb1, y1 = treads[-1]
                parts.append(
                    f'<geom name="rail" type="capsule" fromto="{xa0:.4f} {y0+0.9:.4f} {-w:.4f} '
                    f'{xb1:.4f} {y1+0.9:.4f} {-w:.4f}" size="0.02" rgba="0.35 0.38 0.42 1" contype="0" conaffinity="0"/>'
                )
        elif env.get('steps'):
            steps = env['steps']
            run = float(env.get('run', 0.30))
            w = 0.55
            for i, (xs, ys) in enumerate(steps):
                h = max(ys - fy, 0.04)
                parts.append(
                    f'<geom name="step_{i}" type="box" pos="{xs + run/2:.4f} {fy + h/2:.4f} 0" '
                    f'size="{run/2:.4f} {h/2:.4f} {w:.4f}" rgba="0.62 0.65 0.70 1" contype="0" conaffinity="0"/>'
                )
    elif etype == 'ramp':
        x_lo = float(env.get('x_lo', -1.5))
        x_hi = float(env.get('x_hi', 2.5))
        y_lo = float(env.get('y_lo', fy))
        y_hi = float(env.get('y_hi', fy + 0.5))
        x_max = float(env.get('x_max', max(x_lo, x_hi) + 1.5))
        dx, dy = x_hi - x_lo, y_hi - y_lo
        length = float(np.hypot(dx, dy))
        ang = float(np.arctan2(dy, dx))
        th = 0.04
        # Offset normal to slope so top surface passes exactly through (x_lo, y_lo) -> (x_hi, y_hi)
        nx, ny = -np.sin(ang), np.cos(ang)
        cx = 0.5 * (x_lo + x_hi) - (th * 0.5) * nx
        cy = 0.5 * (y_lo + y_hi) - (th * 0.5) * ny
        parts.append(
            f'<geom name="ramp_deck" type="box" pos="{cx:.4f} {cy:.4f} 0" '
            f'euler="0 0 {ang:.5f}" size="{length/2:.4f} {th/2:.4f} 0.65" '
            f'rgba="0.52 0.62 0.60 1" contype="0" conaffinity="0"/>'
        )
        # Top flat landing platform from x_hi to x_max at height y_hi
        if x_hi > x_lo:
            lx0, lx1 = x_hi, max(x_max, x_hi + 1.2)
        else:
            lx0, lx1 = min(float(env.get('x_min', x_hi - 1.2)), x_hi - 1.2), x_hi
        lh = max(y_hi - fy, 0.04)
        parts.append(
            f'<geom name="ramp_top" type="box" pos="{0.5*(lx0+lx1):.4f} {fy + lh/2:.4f} 0" '
            f'size="{0.5*abs(lx1-lx0):.4f} {lh/2:.4f} 0.65" '
            f'rgba="0.60 0.64 0.68 1" contype="0" conaffinity="0"/>'
        )
    elif etype == 'treadmill':
        parts.append(
            f'<geom name="tm_deck" type="box" pos="0 {fy - 0.04:.4f} 0" size="1.05 0.04 0.36" '
            f'rgba="0.22 0.24 0.28 1" contype="0" conaffinity="0"/>'
        )
        for sz in (-0.38, 0.38):
            parts.append(
                f'<geom type="capsule" fromto="-0.7 {fy+0.92:.4f} {sz:.2f} 0.8 {fy+0.92:.4f} {sz:.2f}" '
                f'size="0.018" rgba="0.40 0.43 0.48 1" contype="0" conaffinity="0"/>'
            )
    elif etype == 'bed':
        by = float(env.get('bed', 0.48))
        x0 = float(env.get('x0', -1.0))
        x1 = float(env.get('x1', 1.2))
        w = float(env.get('w', 0.50))
        cx = 0.5 * (x0 + x1)
        hx = 0.5 * abs(x1 - x0)
        parts.append(
            f'<geom name="bed_mattress" type="box" pos="{cx:.4f} {by - 0.10:.4f} 0" '
            f'size="{hx:.4f} 0.10 {w:.4f}" rgba="0.82 0.85 0.90 1" contype="0" conaffinity="0"/>'
        )
        parts.append(
            f'<geom name="bed_frame" type="box" pos="{cx:.4f} {fy + (by - 0.20)/2:.4f} 0" '
            f'size="{hx + 0.03:.4f} {max(by - 0.20, 0.04)/2:.4f} {w + 0.03:.4f}" '
            f'rgba="0.42 0.34 0.27 1" contype="0" conaffinity="0"/>'
        )
    return '\n    '.join(parts)


def build_visual_model(meta):
    """Build a visual MuJoCo MjModel using exact kneil_v1 kinematics + scene props + implant axes."""
    osim = get_osim()
    g = meta['geom']
    femur = float(g['femur'])
    tibia = float(g['tibia'])
    pelvis = float(g['pelvis'])
    imu_side = g.get('imu_side', 'r')
    imu_pos = (0.005, -0.025, 0.0)
    R_dev, xy_imu = K.site_xyaxes()
    ax_len = 0.16
    ex = np.array(imu_pos) + R_dev[:, 0] * ax_len  # x anterior (red)
    ey = np.array(imu_pos) + R_dev[:, 1] * ax_len  # y left (green)
    ez = np.array(imu_pos) + R_dev[:, 2] * ax_len  # z superior (blue)

    legs = ''
    for s in 'rl':
        h = osim['hip_' + s] * pelvis
        ax = lambda v: ' '.join(f'{c:g}' for c in v)
        a = osim['hip_axes_' + s]
        is_dev = (s == imu_side)
        tib_rgba = '0.18 0.52 0.72 1' if is_dev else '0.52 0.58 0.66 1'
        fem_rgba = '0.32 0.42 0.56 1' if is_dev else '0.46 0.52 0.60 1'
        implant_xml = ''
        if is_dev:
            p0 = f'{imu_pos[0]:.4f} {imu_pos[1]:.4f} {imu_pos[2]:.4f}'
            vo = f'{vis_o[0]:.4f} {vis_o[1]:.4f} {vis_o[2]:.4f}'
            implant_xml = f"""
          <site name="imu" pos="{p0}" xyaxes="{xy_imu}" size="0.014" rgba="0.0 0.85 0.85 1"/>
          <geom name="implant_insert" type="cylinder" pos="0 -0.015 0" zaxis="0 1 0" size="0.048 0.016" rgba="0.90 0.92 0.96 1" contype="0" conaffinity="0"/>
          <geom name="implant_chip" type="box" pos="{p0}" size="0.015 0.010 0.015" rgba="0.0 0.85 0.85 1" contype="0" conaffinity="0"/>
          <geom name="ax_x" type="capsule" fromto="{vo} {ex[0]:.4f} {ex[1]:.4f} {ex[2]:.4f}" size="0.007" rgba="0.90 0.18 0.18 1" contype="0" conaffinity="0"/>
          <geom name="ax_y" type="capsule" fromto="{vo} {ey[0]:.4f} {ey[1]:.4f} {ey[2]:.4f}" size="0.007" rgba="0.16 0.75 0.28 1" contype="0" conaffinity="0"/>
          <geom name="ax_z" type="capsule" fromto="{vo} {ez[0]:.4f} {ez[1]:.4f} {ez[2]:.4f}" size="0.007" rgba="0.15 0.42 0.92 1" contype="0" conaffinity="0"/>"""
        legs += f"""
      <body name="femur_{s}" pos="{h[0]:.5f} {h[1]:.5f} {h[2]:.5f}">
        <joint name="hip_flexion_{s}" axis="{ax(a[0])}"/>
        <joint name="hip_adduction_{s}" axis="{ax(a[1])}"/>
        <joint name="hip_rotation_{s}" axis="{ax(a[2])}"/>
        <geom name="hip_jnt_{s}" type="sphere" size="0.052" rgba="0.72 0.75 0.80 1" contype="0" conaffinity="0"/>
        <geom name="femur_g_{s}" type="capsule" fromto="0 0 0 0 {-femur:.4f} 0" size="0.048" rgba="{fem_rgba}" contype="0" conaffinity="0"/>
        <body name="tibia_{s}">
          <joint name="knee_tx_{s}" type="slide" axis="1 0 0"/>
          <joint name="knee_ty_{s}" type="slide" axis="0 1 0"/>
          <joint name="knee_angle_{s}" axis="0 0 1"/>
          <geom name="knee_jnt_{s}" type="sphere" size="0.046" rgba="0.78 0.80 0.84 1" contype="0" conaffinity="0"/>
          <geom name="tibia_g_{s}" type="capsule" fromto="0 0 0 0 {-tibia:.4f} 0" size="0.036" rgba="{tib_rgba}" contype="0" conaffinity="0"/>
          <geom name="foot_g_{s}" type="capsule" fromto="-0.03 {-tibia - 0.03:.4f} 0 0.14 {-tibia - 0.03:.4f} 0" size="0.026" rgba="0.28 0.30 0.34 1" contype="0" conaffinity="0"/>{implant_xml}
          <site name="ankle_{s}" pos="0 {-tibia:.4f} 0" size="0.005" rgba="0 0 0 0"/>
        </body>
      </body>"""

    env_xml = _scene_env_xml(meta.get('env', {}))
    xml = f"""<mujoco model="kneil_viewer">
  <option gravity="0 {-K.G} 0" timestep="{1 / FS_OUT}"/>
  <visual>
    <global offwidth="1280" offheight="960"/>
    <headlight diffuse="0.65 0.65 0.65" ambient="0.35 0.35 0.35" specular="0.2 0.2 0.2"/>
  </visual>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.93 0.95 0.98" rgb2="0.82 0.86 0.92" width="128" height="128"/>
    <texture name="tex_floor" type="2d" builtin="checker" rgb1="0.88 0.90 0.92" rgb2="0.80 0.83 0.87" width="256" height="256"/>
    <material name="mat_floor" texture="tex_floor" texrepeat="20 20" reflectance="0.05"/>
  </asset>
  <worldbody>
    <light pos="2 4 3" dir="-0.4 -1 -0.5" diffuse="0.8 0.8 0.8" specular="0.2 0.2 0.2" castshadow="true"/>
    <light pos="-3 3 -2" dir="0.5 -0.8 0.4" diffuse="0.35 0.35 0.4" castshadow="false"/>
    {env_xml}
    <body name="pelvis">
      <joint name="pelvis_tx" type="slide" axis="1 0 0"/>
      <joint name="pelvis_ty" type="slide" axis="0 1 0"/>
      <joint name="pelvis_tz" type="slide" axis="0 0 1"/>
      <joint name="pelvis_tilt" axis="0 0 1"/>
      <joint name="pelvis_list" axis="1 0 0"/>
      <joint name="pelvis_rotation" axis="0 1 0"/>
      <geom name="pelvis_g" type="capsule" fromto="0 0 {-0.10*pelvis:.4f} 0 0 {0.10*pelvis:.4f}" size="0.075" rgba="0.38 0.44 0.52 1" contype="0" conaffinity="0"/>
      <geom name="torso_g" type="capsule" fromto="0 0.04 0 0 {0.48*pelvis:.4f} 0" size="0.085" rgba="0.42 0.48 0.56 0.85" contype="0" conaffinity="0"/>
      <geom name="head_g" type="sphere" pos="0 {0.64*pelvis:.4f} 0" size="0.095" rgba="0.72 0.75 0.80 0.90" contype="0" conaffinity="0"/>{legs}
    </body>
  </worldbody>
</mujoco>"""
    return mujoco.MjModel.from_xml_string(xml)


def default_camera_for(env):
    """Return sensible (azimuth, elevation, distance) for a motion's scene type (Y-up world -> MuJoCo Z-up camera)."""
    # Note: MuJoCo's free camera uses Z-up internally, whereas kneil_v1 uses Y-up!
    # We compute a clean explicit lookat camera using a fixed camera or mjvCamera.
    etype = env.get('type', 'floor')
    if etype == 'bed':
        return dict(offset=np.array([0.8, 1.8, 2.4]), look_dy=0.0)
    if etype == 'stairs':
        return dict(offset=np.array([0.6, 0.7, 3.0]), look_dy=0.0)
    if etype == 'ramp':
        return dict(offset=np.array([0.6, 0.7, 3.2]), look_dy=0.0)
    if etype == 'chair':
        return dict(offset=np.array([0.8, 0.5, 2.4]), look_dy=-0.1)
    return dict(offset=np.array([0.6, 0.5, 2.7]), look_dy=-0.1)


def _set_yup_camera(m, cam_pos, target):
    """Configure a MuJoCo camera named 'track' or return explicit camera matrix for Y-up world."""
    # MuJoCo's MjvCamera always uses world +Z as up; for Y-up models, using an explicit
    # worldbody <camera> with pos + xyaxes gives a perfectly level Y-up horizon!
    f = target - cam_pos
    f = f / (np.linalg.norm(f) + 1e-12)
    up = np.array([0.0, 1.0, 0.0])
    r = np.cross(f, up)
    if np.linalg.norm(r) < 1e-6:
        r = np.array([1.0, 0.0, 0.0])
    else:
        r = r / np.linalg.norm(r)
    u = np.cross(r, f)
    return cam_pos, r, u


def build_visual_model_with_cam(meta):
    """Same as build_visual_model(), plus a movable Y-up camera in worldbody for crisp renders."""
    # Insert a <camera name="view" .../> into worldbody
    m = build_visual_model(meta)
    return m


# =============================================================================
# Plotting & headless composite frame renderer
# =============================================================================
def _render_3d_frame(m, d, Q_row, env, width=900, height=720):
    """Render one Y-up 3D frame of the KNEIL MuJoCo model using mujoco.Renderer."""
    d.qpos[:] = Q_row
    mujoco.mj_forward(m, d)
    pel = d.xpos[m.body('pelvis').id].copy()
    cdef = default_camera_for(env)
    target = pel + np.array([0.0, cdef['look_dy'], 0.0])
    cam_pos = target + cdef['offset']
    # Build an explicit MjvCamera? MjvCamera uses Z-up, so instead we orient a named camera via model.cam_pos / cam_quat!
    # Wait: if we add <camera name="main"/> to build_visual_model, we can update m.cam_pos[0] and m.cam_quat[0] every frame!
    cam_id = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, 'main')
    if cam_id >= 0:
        _, r, u = _set_yup_camera(m, cam_pos, target)
        f = target - cam_pos
        f /= (np.linalg.norm(f) + 1e-12)
        # MuJoCo camera frame: +X right, +Y up, -Z forward
        R = np.column_stack([r, u, -f])
        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, R.ravel())
        m.cam_pos[cam_id] = cam_pos
        m.cam_quat[cam_id] = quat
        mujoco.mj_forward(m, d)
    return pel


def add_camera_to_model(meta):
    """Build visual MjModel with a controllable Y-up <camera name="main"/> and optional CAD knee implant."""
    osim = get_osim()
    g = meta['geom']
    femur = float(g['femur'])
    tibia = float(g['tibia'])
    pelvis = float(g['pelvis'])
    imu_side = g.get('imu_side', 'r')
    imu_pos = (0.005, -0.025, 0.0)
    R_dev, xy_imu = K.site_xyaxes()
    # Visual triad origin offset slightly anterior-lateral so all 3 axes (X, Y, Z) clear the knee implant
    vis_o = np.array([0.048, -0.025, 0.048 if imu_side == 'r' else -0.048])
    ax_len = 0.16
    ex = vis_o + R_dev[:, 0] * ax_len
    ey = vis_o + R_dev[:, 1] * ax_len
    ez = vis_o + R_dev[:, 2] * ax_len

    # Prepare decimated CAD meshes in cache/viewer/cad/ if owner's OBJ is present
    cad_meta = None
    cad_assets_xml = ''
    k_off = np.array([0.0, -femur, 0.0])
    try:
        import implant_cad as IC
        if IC.cad_available() and imu_side == 'r':
            cad_meta = IC.prepare_cad_meshes()
            k_off = IC.knee_standing_offset(osim, femur=femur)
            cad_assets_xml = (
                f'\n    <mesh name="cad_femoral" file="{cad_meta["stl"]["femoral"]}"/>'
                f'\n    <mesh name="cad_spacer" file="{cad_meta["stl"]["spacer"]}"/>'
                f'\n    <mesh name="cad_tibial" file="{cad_meta["stl"]["tibial"]}"/>'
            )
    except Exception as exc:
        log_msg(f'CAD mesh load skipped: {exc}')
        cad_meta = None

    legs = ''
    for s in 'rl':
        h = osim['hip_' + s] * pelvis
        ax = lambda v: ' '.join(f'{c:g}' for c in v)
        a = osim['hip_axes_' + s]
        is_dev = (s == imu_side)
        use_cad = is_dev and (cad_meta is not None)
        tib_rgba = '0.16 0.50 0.72 1' if is_dev else '0.52 0.58 0.66 1'
        fem_rgba = '0.30 0.40 0.54 1' if is_dev else '0.46 0.52 0.60 1'
        fem_geom_xml = (
            f'<geom name="femur_g_{s}" type="capsule" fromto="0 0 0 0 {-(femur - 0.055):.4f} 0" size="0.042" rgba="{fem_rgba}" contype="0" conaffinity="0"/>'
            f'\n        <geom name="cad_fem_g" type="mesh" mesh="cad_femoral" pos="{k_off[0]:.5f} {k_off[1]:.5f} {k_off[2]:.5f}" rgba="0.78 0.81 0.85 1" contype="0" conaffinity="0"/>'
            if use_cad else
            f'<geom name="femur_g_{s}" type="capsule" fromto="0 0 0 0 {-femur:.4f} 0" size="0.048" rgba="{fem_rgba}" contype="0" conaffinity="0"/>'
        )
        tib_geom_xml = (
            f'<geom name="tibia_g_{s}" type="capsule" fromto="0 -0.075 0 0 {-tibia:.4f} 0" size="0.032" rgba="{tib_rgba}" contype="0" conaffinity="0"/>'
            f'\n          <geom name="cad_sp_g" type="mesh" mesh="cad_spacer" pos="0 0 0" rgba="0.95 0.95 0.93 1" contype="0" conaffinity="0"/>'
            f'\n          <geom name="cad_tib_g" type="mesh" mesh="cad_tibial" pos="0 0 0" rgba="0.75 0.78 0.82 1" contype="0" conaffinity="0"/>'
            if use_cad else
            f'<geom name="knee_jnt_{s}" type="sphere" size="0.046" rgba="0.78 0.80 0.84 1" contype="0" conaffinity="0"/>'
            f'\n          <geom name="tibia_g_{s}" type="capsule" fromto="0 0 0 0 {-tibia:.4f} 0" size="0.036" rgba="{tib_rgba}" contype="0" conaffinity="0"/>'
        )
        implant_xml = ''
        if is_dev:
            p0 = f'{imu_pos[0]:.4f} {imu_pos[1]:.4f} {imu_pos[2]:.4f}'
            vo = f'{vis_o[0]:.4f} {vis_o[1]:.4f} {vis_o[2]:.4f}'
            insert_fallback = '' if use_cad else '\n          <geom name="implant_insert" type="cylinder" pos="0 -0.015 0" zaxis="0 1 0" size="0.048 0.016" rgba="0.90 0.92 0.96 1" contype="0" conaffinity="0"/>'
            implant_xml = f"""
          <site name="imu" pos="{p0}" xyaxes="{xy_imu}" size="0.014" rgba="0.0 0.85 0.85 1"/>{insert_fallback}
          <geom name="implant_chip" type="box" pos="{p0}" size="0.012 0.008 0.012" rgba="0.0 0.88 0.88 1" contype="0" conaffinity="0"/>
          <geom name="ax_x" type="capsule" fromto="{vo} {ex[0]:.4f} {ex[1]:.4f} {ex[2]:.4f}" size="0.006" rgba="0.90 0.18 0.18 1" contype="0" conaffinity="0"/>
          <geom name="ax_y" type="capsule" fromto="{vo} {ey[0]:.4f} {ey[1]:.4f} {ey[2]:.4f}" size="0.006" rgba="0.16 0.75 0.28 1" contype="0" conaffinity="0"/>
          <geom name="ax_z" type="capsule" fromto="{vo} {ez[0]:.4f} {ez[1]:.4f} {ez[2]:.4f}" size="0.006" rgba="0.15 0.42 0.92 1" contype="0" conaffinity="0"/>"""
        legs += f"""
      <body name="femur_{s}" pos="{h[0]:.5f} {h[1]:.5f} {h[2]:.5f}">
        <joint name="hip_flexion_{s}" axis="{ax(a[0])}"/>
        <joint name="hip_adduction_{s}" axis="{ax(a[1])}"/>
        <joint name="hip_rotation_{s}" axis="{ax(a[2])}"/>
        <geom name="hip_jnt_{s}" type="sphere" size="0.052" rgba="0.72 0.75 0.80 1" contype="0" conaffinity="0"/>
        {fem_geom_xml}
        <body name="tibia_{s}">
          <joint name="knee_tx_{s}" type="slide" axis="1 0 0"/>
          <joint name="knee_ty_{s}" type="slide" axis="0 1 0"/>
          <joint name="knee_angle_{s}" axis="0 0 1"/>
          {tib_geom_xml}
          <geom name="foot_g_{s}" type="capsule" fromto="-0.03 {-tibia - 0.03:.4f} 0 0.14 {-tibia - 0.03:.4f} 0" size="0.026" rgba="0.28 0.30 0.34 1" contype="0" conaffinity="0"/>{implant_xml}
          <site name="ankle_{s}" pos="0 {-tibia:.4f} 0" size="0.005" rgba="0 0 0 0"/>
        </body>
      </body>"""

    env_xml = _scene_env_xml(meta.get('env', {}))
    xml = f"""<mujoco model="kneil_viewer">
  <option gravity="0 {-K.G} 0" timestep="{1 / FS_OUT}"/>
  <visual>
    <global offwidth="1280" offheight="960"/>
    <headlight diffuse="0.65 0.65 0.65" ambient="0.35 0.35 0.35" specular="0.2 0.2 0.2"/>
  </visual>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.93 0.95 0.98" rgb2="0.82 0.86 0.92" width="128" height="128"/>
    <texture name="tex_floor" type="2d" builtin="checker" rgb1="0.88 0.90 0.92" rgb2="0.80 0.83 0.87" width="256" height="256"/>
    <material name="mat_floor" texture="tex_floor" texrepeat="20 20" reflectance="0.05"/>{cad_assets_xml}
  </asset>
  <worldbody>
    <camera name="main" pos="0.6 1.4 2.7" fovy="42"/>
    <light pos="2 4 3" dir="-0.4 -1 -0.5" diffuse="0.8 0.8 0.8" specular="0.2 0.2 0.2" castshadow="true"/>
    <light pos="-3 3 -2" dir="0.5 -0.8 0.4" diffuse="0.35 0.35 0.4" castshadow="false"/>
    {env_xml}
    <body name="pelvis">
      <joint name="pelvis_tx" type="slide" axis="1 0 0"/>
      <joint name="pelvis_ty" type="slide" axis="0 1 0"/>
      <joint name="pelvis_tz" type="slide" axis="0 0 1"/>
      <joint name="pelvis_tilt" axis="0 0 1"/>
      <joint name="pelvis_list" axis="1 0 0"/>
      <joint name="pelvis_rotation" axis="0 1 0"/>
      <geom name="pelvis_g" type="capsule" fromto="0 0 {-0.10*pelvis:.4f} 0 0 {0.10*pelvis:.4f}" size="0.075" rgba="0.38 0.44 0.52 1" contype="0" conaffinity="0"/>
      <geom name="torso_g" type="capsule" fromto="0 0.04 0 0 {0.48*pelvis:.4f} 0" size="0.085" rgba="0.42 0.48 0.56 0.85" contype="0" conaffinity="0"/>
      <geom name="head_g" type="sphere" pos="0 {0.64*pelvis:.4f} 0" size="0.095" rgba="0.72 0.75 0.80 0.90" contype="0" conaffinity="0"/>{legs}
    </body>
  </worldbody>
</mujoco>"""
    return mujoco.MjModel.from_xml_string(xml)


def decision_at(data, t_cur):
    """Return latest window decision dict at time t_cur (or None if before first 4 s window)."""
    wt = data['win_t']
    if len(wt) == 0 or t_cur < wt[0] - 1e-6:
        return None
    k = int(np.searchsorted(wt, t_cur, side='right')) - 1
    k = max(0, min(k, len(wt) - 1))
    return dict(
        idx=k, t_end=float(wt[k]),
        rule_cls=int(data['rule_cls'][k]),
        raw_cls=int(data['raw_cls'][k]),
        vote=float(data['vote'][k]),
        posture=int(data['posture'][k]),
        n_sts=int(data['ev_sts'][:k + 1].sum()),
        n_s2s=int(data['ev_s2s'][:k + 1].sum()),
        n_bed=int(data['ev_bed'][:k + 1].sum()),
    )


def render_composite_png(data, t_cur, out_path, renderer=None, m=None, d=None):
    """Render side-by-side 3D MuJoCo view + synchronized signals & V4 forest decision to PNG."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    meta = data['meta']
    t = data['t']
    t_cur = float(np.clip(t_cur, 0.0, float(t[-1])))
    fi = int(np.clip(round(t_cur * FS_OUT), 0, len(t) - 1))

    own_r = False
    if m is None:
        m = add_camera_to_model(meta)
        d = mujoco.MjData(m)
    if renderer is None:
        renderer = mujoco.Renderer(m, height=720, width=840)
        own_r = True

    _render_3d_frame(m, d, data['Q'][fi], meta.get('env', {}))
    renderer.update_scene(d, camera='main')
    img3d = renderer.render()
    if own_r:
        renderer.close()

    fig = plt.figure(figsize=(16, 8.2), dpi=120, facecolor='#f7f8fa')
    gs = fig.add_gridspec(4, 2, width_ratios=[1.05, 1.15], height_ratios=[1.1, 1.1, 1.1, 1.05],
                          wspace=0.14, hspace=0.34, left=0.03, right=0.98, top=0.90, bottom=0.09)

    # Left: 3D view
    ax3d = fig.add_subplot(gs[:, 0])
    ax3d.imshow(img3d)
    ax3d.set_axis_off()
    ax3d.set_title(f'{meta["name"]}  ({meta["source"]})', fontsize=12, fontweight='bold', pad=6)

    dec = decision_at(data, t_cur)
    ins_lbl = meta.get('in_sample_label', '')
    if dec is not None:
        col = CLASS_COLOURS_V2[dec['rule_cls']]
        lbl = CLASS_LABELS_V2[dec['rule_cls']]
        raw_lbl = CLASS_LABELS_V2[dec['raw_cls']]
        rule_tag = '  [stairs rule -> walking]' if dec['raw_cls'] != dec['rule_cls'] else ''
        hud = (f't = {t_cur:5.2f} s / {t[-1]:.1f} s  |  {ins_lbl}\n'
               f'Forest: {lbl}  (raw: {raw_lbl}, vote {dec["vote"]*100:.0f}%){rule_tag}\n'
               f'Posture: {POSTURE_NAMES[dec["posture"]]}  |  Events: STS {dec["n_sts"]}, S2S {dec["n_s2s"]}, Bed {dec["n_bed"]}')
    else:
        col = NONE_COLOUR
        hud = f't = {t_cur:5.2f} s / {t[-1]:.1f} s  |  {ins_lbl}\nForest: waiting for first 4 s window'

    ax3d.text(0.02, 0.98, hud, transform=ax3d.transAxes, va='top', ha='left', fontsize=9.5,
              color='#111111', bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor=col, linewidth=2.5, alpha=0.92))
    ax3d.text(0.02, 0.02, 'Implant axes: X anterior (red), Y left (green), Z superior (blue)',
              transform=ax3d.transAxes, va='bottom', ha='left', fontsize=8.5,
              color='#222222', bbox=dict(boxstyle='round,pad=0.25', facecolor='white', edgecolor='#cccccc', alpha=0.85))

    # Right: 3 acceleration panels + 1 timeline panel
    acc, acc_lp = data['acc'], data['acc_lp']
    ax_names = [('x anterior (g)', '#d62728'), ('y left (g)', '#2ca02c'), ('z superior (g)', '#1f77b4')]
    t_max = float(t[-1])
    for k, (aname, acol) in enumerate(ax_names):
        ax = fig.add_subplot(gs[k, 1])
        ax.plot(t, acc[:, k], color=acol, alpha=0.25, lw=0.8, label='50 Hz raw')
        ax.plot(t, acc_lp[:, k], color=acol, lw=1.4, label='6 Hz LP (chip)')
        ax.axvline(t_cur, color='#111111', lw=1.3, ls='--')
        ax.set_xlim(0, t_max)
        ax.set_ylabel(aname, fontsize=9)
        ax.grid(True, alpha=0.25)
        ax.tick_params(labelsize=8.5)
        if k == 0:
            ax.legend(loc='upper right', fontsize=8, frameon=True)
            ax.set_title('Simulated implant acceleration (50 Hz) & V4 forest decision (4 s / 1 s hop)', fontsize=11, pad=5)

    # Bottom right: Forest decision timeline + True label timeline underneath
    ax_t = fig.add_subplot(gs[3, 1])
    wt = data['win_t']
    for k in range(len(wt)):
        tc = float(wt[k])
        c_rule = int(data['rule_cls'][k])
        c_raw = int(data['raw_cls'][k])
        ax_t.barh(1.0, HOP_S, left=tc - HOP_S, height=0.58, color=CLASS_COLOURS_V2[c_rule], edgecolor='white', lw=0.3)
        if c_raw != c_rule:
            # Mark stairs-rule override with a small top dot in raw colour
            ax_t.plot(tc - 0.5 * HOP_S, 1.32, marker='v', markersize=4, color=CLASS_COLOURS_V2[c_raw])
        if data['ev_sts'][k] > 0:
            ax_t.plot(tc - 0.5, 1.0, marker='^', markersize=6, color='black')
        if data['ev_s2s'][k] > 0:
            ax_t.plot(tc - 0.5, 1.0, marker='v', markersize=6, color='black')
        if data['ev_bed'][k] > 0:
            ax_t.plot(tc - 0.5, 1.0, marker='D', markersize=5, color='white', markeredgecolor='black')

    for lab, ta, tb in meta.get('label_spans', []):
        v2 = map_label_to_v2(lab)
        col_t = CLASS_COLOURS_V2[v2] if v2 >= 0 else EXTRA_COLOURS.get(lab, NONE_COLOUR)
        ax_t.barh(0.0, max(tb - ta, 0.05), left=ta, height=0.58, color=col_t, edgecolor='none')

    ax_t.axvline(t_cur, color='#111111', lw=1.3, ls='--')
    ax_t.set_xlim(0, t_max)
    ax_t.set_ylim(-0.55, 1.55)
    ax_t.set_yticks([0.0, 1.0])
    ax_t.set_yticklabels(['True', 'Forest V4'], fontsize=9)
    ax_t.set_xlabel('Time (s)', fontsize=9)
    ax_t.tick_params(labelsize=8.5)
    ax_t.grid(True, axis='x', alpha=0.25)

    # Compact legend at bottom
    used = set(int(x) for x in data['rule_cls']) | set(int(x) for x in data['raw_cls'])
    for lab, _, _ in meta.get('label_spans', []):
        v2 = map_label_to_v2(lab)
        if v2 >= 0:
            used.add(v2)
    handles = [Patch(facecolor=CLASS_COLOURS_V2[i], label=CLASS_LABELS_V2[i]) for i in sorted(used)]
    for lab, _, _ in meta.get('label_spans', []):
        if lab in EXTRA_COLOURS and all(h.get_label() != lab.replace('_', ' ') for h in handles):
            handles.append(Patch(facecolor=EXTRA_COLOURS[lab], label=lab.replace('_', ' ')))
    fig.legend(handles=handles, loc='lower center', ncol=min(len(handles), 8), fontsize=8.5, frameon=False)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


# =============================================================================
# Interactive viewer (mujoco.viewer.launch_passive + matplotlib)
# =============================================================================
def run_interactive(catalog, start_entry):
    import matplotlib.pyplot as plt
    import mujoco.viewer

    idx_cur = next(i for i, c in enumerate(catalog) if c['id'] == start_entry['id'])
    state = dict(paused=False, speed=1.0, t=0.0, switch=0)

    while True:
        entry = catalog[idx_cur]
        data = load_motion(entry)
        meta = data['meta']
        m = add_camera_to_model(meta)
        d = mujoco.MjData(m)
        t_arr = data['t']
        dur = float(t_arr[-1])
        state['t'] = 0.0
        state['switch'] = 0

        plt.ion()
        fig, axes = plt.subplots(4, 1, figsize=(7.5, 7.2), sharex=True)
        fig.canvas.manager.set_window_title(f'KNEIL Signals — {meta["name"]}')
        ax_names = [('x ant (g)', '#d62728'), ('y left (g)', '#2ca02c'), ('z sup (g)', '#1f77b4')]
        cursors = []
        for k, (aname, acol) in enumerate(ax_names):
            axes[k].plot(t_arr, data['acc'][:, k], color=acol, alpha=0.25, lw=0.8)
            axes[k].plot(t_arr, data['acc_lp'][:, k], color=acol, lw=1.3)
            axes[k].set_ylabel(aname, fontsize=9)
            axes[k].grid(True, alpha=0.25)
            cursors.append(axes[k].axvline(0.0, color='k', ls='--'))
        for k in range(len(data['win_t'])):
            tc = float(data['win_t'][k])
            axes[3].barh(1.0, HOP_S, left=tc - HOP_S, height=0.55, color=CLASS_COLOURS_V2[int(data['rule_cls'][k])])
        for lab, ta, tb in meta.get('label_spans', []):
            v2 = map_label_to_v2(lab)
            col_t = CLASS_COLOURS_V2[v2] if v2 >= 0 else EXTRA_COLOURS.get(lab, NONE_COLOUR)
            axes[3].barh(0.0, max(tb - ta, 0.05), left=ta, height=0.55, color=col_t)
        axes[3].set_yticks([0.0, 1.0])
        axes[3].set_yticklabels(['True', 'Forest'])
        axes[3].set_xlabel('Time (s)')
        axes[3].set_xlim(0, dur)
        cursors.append(axes[3].axvline(0.0, color='k', ls='--'))
        fig.tight_layout()
        fig.show()

        def key_cb(keycode):
            if keycode == 32:  # space
                state['paused'] = not state['paused']
            elif keycode == 262:  # right
                state['t'] = min(dur, state['t'] + 1.0)
            elif keycode == 263:  # left
                state['t'] = max(0.0, state['t'] - 1.0)
            elif keycode in (ord('N'), ord('n')):
                state['switch'] = +1
            elif keycode in (ord('P'), ord('p')):
                state['switch'] = -1
            elif keycode in (ord('+'), ord('=')):
                state['speed'] = min(4.0, state['speed'] * 1.25)
            elif keycode in (ord('-'), ord('_')):
                state['speed'] = max(0.2, state['speed'] / 1.25)

        t_prev = time.perf_counter()
        last_plot = 0.0
        with mujoco.viewer.launch_passive(m, d, key_callback=key_cb) as viewer:
            while viewer.is_running() and state['switch'] == 0:
                now = time.perf_counter()
                dt = min(0.05, now - t_prev)
                t_prev = now
                if not state['paused']:
                    state['t'] = (state['t'] + dt * state['speed']) % max(dur, 1e-3)
                fi = int(np.clip(round(state['t'] * FS_OUT), 0, len(t_arr) - 1))
                d.qpos[:] = data['Q'][fi]
                mujoco.mj_forward(m, d)
                viewer.cam.lookat[:] = d.xpos[m.body('pelvis').id]
                viewer.sync()
                if now - last_plot >= 0.06:
                    for c in cursors:
                        c.set_xdata([state['t'], state['t']])
                    dec = decision_at(data, state['t'])
                    if dec:
                        axes[0].set_title(
                            f'{meta["name"]} | t={state["t"]:.1f}s | {CLASS_LABELS_V2[dec["rule_cls"]]} '
                            f'(raw {CLASS_LABELS_V2[dec["raw_cls"]]} {dec["vote"]*100:.0f}%) | {POSTURE_NAMES[dec["posture"]]}',
                            fontsize=9.5,
                        )
                    fig.canvas.draw_idle()
                    plt.pause(0.001)
                    last_plot = now
                time.sleep(0.01)

        plt.close(fig)
        if state['switch'] == 0:
            break
        idx_cur = (idx_cur + state['switch']) % len(catalog)


# =============================================================================
# Acceptance check helpers: summary table + C vs Python verification
# =============================================================================
def print_summary_table(catalog, out_json=None):
    rows = []
    hdr = f'{"ID":30s} | {"Source":14s} | {"Split":26s} | {"Dur":5s} | {"True":20s} | Forest V4 class shares (% of windows)'
    print(hdr)
    print('-' * len(hdr))
    for entry in catalog:
        data = load_motion(entry)
        rc = data['rule_cls']
        rawc = data['raw_cls']
        n_w = len(rc)
        shares = {}
        if n_w > 0:
            for c in range(8):
                cnt = int((rc == c).sum())
                if cnt > 0:
                    shares[CLASS_NAMES_V2[c]] = round(100.0 * cnt / n_w, 1)
            raw_stairs = int(((rawc == 1) | (rawc == 2)).sum())
            rule_stairs = int(((rc == 1) | (rc == 2)).sum())
        else:
            raw_stairs = rule_stairs = 0
        s_str = ', '.join(f'{k}:{v:.0f}%' for k, v in sorted(shares.items(), key=lambda kv: -kv[1]))
        if raw_stairs != rule_stairs:
            s_str += f'  (raw stairs {100.0*raw_stairs/n_w:.0f}% -> rule {100.0*rule_stairs/n_w:.0f}%)'
        t_str = ','.join(sorted(set(x[0] for x in data['meta'].get('label_spans', []))))[:20]
        split_s = entry['in_sample_label'][:26]
        print(f'{entry["id"]:30s} | {entry["source"]:14s} | {split_s:26s} | {data["meta"]["dur"]:4.1f}s | {t_str:20s} | {s_str}')
        rows.append(dict(
            id=entry['id'], name=entry['name'], source=entry['source'],
            in_sample=entry['in_sample'], in_sample_label=entry['in_sample_label'],
            dur=round(data['meta']['dur'], 1), n_windows=n_w,
            true_labels=sorted(set(x[0] for x in data['meta'].get('label_spans', []))),
            shares=shares, raw_stairs_pct=round(100.0 * raw_stairs / n_w, 1) if n_w else 0.0,
            rule_stairs_pct=round(100.0 * rule_stairs / n_w, 1) if n_w else 0.0,
            n_sts=data['meta']['n_sts_total'], n_s2s=data['meta']['n_s2s_total'], n_bed=data['meta']['n_bed_total'],
        ))
    if out_json:
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=2)
    return rows


def check_feet_table(catalog):
    """Print stance foot-to-prop |error| (median and 95th percentile, cm) for all non-bed motions."""
    hdr = f'{"ID":30s} | {"Env":9s} | {"med|err| cm":11s} | {"p95|err| cm":11s} | {"signed cm":9s} | Status'
    print(hdr)
    print('-' * len(hdr))
    ok_all = True
    for entry in catalog:
        data = load_motion(entry)
        et = data['meta'].get('env', {}).get('type', 'floor')
        if et == 'bed':
            continue
        med, p95, sgn = foot_prop_error_cm(data)
        ok = med < 2.0
        ok_all = ok_all and ok
        print(f'{entry["id"]:30s} | {et:9s} | {med:11.2f} | {p95:11.2f} | {sgn:+9.2f} | {"PASS" if ok else "WARN"}')
    return ok_all


def verify_c_vs_python(catalog, motion_names=('walk_healthy', 'walk_fast', 'sit_to_stand')):
    """Acceptance Check 5: verify kneil_tinyml C library == metrics_ref.py + sklearn forest on 3 motions."""
    import joblib
    import metrics_ref as MR
    import stage3 as S3
    from export_v4 import forest_votes

    model_path = os.path.join(config.V4_OUT, 'tinyml_final_v4_lp6', 'model_forest.joblib')
    model = joblib.load(model_path)
    Wn = int(FS_OUT * WIN_S)

    all_ok = True
    for mname in motion_names:
        entry = resolve_motion_id(mname, catalog)
        data = load_motion(entry)
        acc = data['acc']
        # Python features (same path as check_step_e.py)
        b = S3.T.apply_lowpass(np.asarray(acc, np.float64), FS_OUT, 6.0).astype(np.float32)
        Xp = np.array(
            [S3.T.features(S3.T_lib(), b[s:s + Wn, 0], b[s:s + Wn, 1], b[s:s + Wn, 2], FS_OUT)
             for s in range(0, len(b) - Wn + 1, int(FS_OUT * HOP_S))],
            dtype=np.float32,
        ).reshape(-1, S3.T.NF)
        sk_vote = forest_votes(model, Xp)
        # Reconstruct vote share of winning class from tree votes
        tree_preds = np.column_stack([est.predict(Xp).astype(np.int32) for est in model.estimators_])
        n_trees = tree_preds.shape[1]
        py_vote = np.array([(tree_preds[i] == sk_vote[i]).sum() / n_trees for i in range(len(Xp))], dtype=np.float32)
        py_rule = np.array([MR.stairs_rule(int(sk_vote[i]), float(py_vote[i]), 0.60) for i in range(len(Xp))], dtype=np.int16)

        # Replay through metrics_ref.py
        pm = MR.Metrics(stairs_min_vote=0.60, smooth=True, hop_s=1.0)
        for i in range(len(Xp)):
            pm.push(int(sk_vote[i]), float(py_vote[i]))

        c_raw = data['raw_cls']
        c_rule = data['rule_cls']
        k = min(len(c_raw), len(sk_vote))
        raw_mism = int((c_raw[:k] != sk_vote[:k]).sum())
        rule_mism = int((c_rule[:k] != py_rule[:k]).sum())
        sts_ok = (pm.n_sts == data['meta']['n_sts_total'])
        s2s_ok = (pm.n_s2s == data['meta']['n_s2s_total'])
        bed_ok = (pm.n_bed == data['meta']['n_bed_total'])
        post_ok = (pm.posture == int(data['posture'][-1])) if k > 0 else True
        ok = (raw_mism == 0 and rule_mism == 0 and sts_ok and s2s_ok and bed_ok and post_ok and len(c_raw) == len(sk_vote))
        all_ok = all_ok and ok
        print(f'  {entry["id"]:28s} | win={k:3d} | raw_mism={raw_mism} | rule_mism={rule_mism} | '
              f'events(C/Py): STS {data["meta"]["n_sts_total"]}/{pm.n_sts}, S2S {data["meta"]["n_s2s_total"]}/{pm.n_s2s}, '
              f'Bed {data["meta"]["n_bed_total"]}/{pm.n_bed} | posture C/Py={int(data["posture"][-1])}/{pm.posture} | '
              f'{"PASS" if ok else "FAIL"}')
    return all_ok


def main():
    print(VERSION, flush=True)
    log_msg(f'Start: {VERSION} argv={sys.argv[1:]}')
    ap = argparse.ArgumentParser(description='KNEIL 3D MuJoCo motion viewer with V4 forest decisions')
    ap.add_argument('motion', nargs='?', help='motion id or alias (use --list)')
    ap.add_argument('--list', action='store_true', help='list all available motions')
    ap.add_argument('--render', metavar='OUT.png', help='render one headless composite PNG')
    ap.add_argument('--t', type=float, default=8.0, help='time in seconds for --render (default 8.0)')
    ap.add_argument('--frames', metavar='DIR', help='render a numbered PNG sequence into DIR')
    ap.add_argument('--fps', type=float, default=10.0, help='frame rate for --frames (default 10)')
    ap.add_argument('--summary-table', action='store_true', help='print forest class shares for all motions')
    ap.add_argument('--summary-json', metavar='OUT.json', help='also save summary table to JSON')
    ap.add_argument('--verify-c', action='store_true', help='verify C library == metrics_ref + sklearn on 3 motions')
    ap.add_argument('--check-feet', action='store_true', help='check stance foot-to-prop error (cm) on all motions')
    ap.add_argument('--rebuild', action='store_true', help='ignore cache and rebuild motion')
    args = ap.parse_args()

    catalog = build_catalog()
    if args.list:
        print(f'Total motions: {len(catalog)}')
        print(f'{"ID":30s} | {"Source":14s} | {"Dur":6s} | {"Split":34s} | Name')
        print('-' * 135)
        for c in catalog:
            print(f'{c["id"]:30s} | {c["source"]:14s} | {c["dur"]:5.1f}s | {c["in_sample_label"][:34]:34s} | {c["name"]}')
        print('\nAliases:', ', '.join(f'{k} -> {v}' for k, v in ALIASES.items()))
        return 0

    if args.check_feet:
        check_feet_table(catalog)
        return 0

    if args.verify_c:
        ok = verify_c_vs_python(catalog)
        print('C vs Python verification:', 'PASS' if ok else 'FAIL')
        return 0 if ok else 1

    if args.summary_table:
        print_summary_table(catalog, out_json=args.summary_json)
        return 0

    if not args.motion:
        ap.print_help()
        return 1

    entry = resolve_motion_id(args.motion, catalog)
    data = load_motion(entry, force_rebuild=args.rebuild)

    if args.render:
        render_composite_png(data, args.t, args.render)
        print(f'Rendered {args.render} at t={args.t:.2f} s')
        log_msg(f'Rendered {args.render} ({entry["id"]} at t={args.t:.2f}s)')
        return 0

    if args.frames:
        os.makedirs(args.frames, exist_ok=True)
        dur = float(data['t'][-1])
        m = add_camera_to_model(data['meta'])
        d = mujoco.MjData(m)
        r = mujoco.Renderer(m, height=720, width=840)
        ts = np.arange(0.0, dur + 1e-6, 1.0 / args.fps)
        try:
            for i, tt in enumerate(ts):
                outp = os.path.join(args.frames, f'frame_{i:04d}.png')
                render_composite_png(data, float(tt), outp, renderer=r, m=m, d=d)
        finally:
            r.close()
        print(f'Wrote {len(ts)} frames to {args.frames}')
        log_msg(f'Wrote {len(ts)} frames ({entry["id"]}) to {args.frames}')
        return 0

    run_interactive(catalog, entry)
    return 0


if __name__ == '__main__':
    sys.exit(main())
