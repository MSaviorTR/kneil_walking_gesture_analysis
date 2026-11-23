"""
KNEIL A1 part A: walking-aid gait personas from the measured Camargo joint angles.   aid_gait 1.0, 23 Nov 2026

For every Camargo subject except AB07 (21 people; AB07's recomposed strides are the viewer's independent test
set), this builds one measured stride template from the level-ground kinematic replay (camargo_replay.py ->
kneil_v1 MuJoCo model -> implant accelerometer), then generates walking-aid personas from it:

  speed target 0.15-0.55 m/s (strides stretched in time), pause share 0-45 % with irregular pauses,
  pick-up walker / rollator / crutches, step-to or step-through, full / partial / toe-touch weight bearing
  (a small non-weight-bearing set, implant leg held, labelled by rule C), standing rests and turns.

Every 4 s window (1 s hop) is labelled by rule C from the foot contacts of the generated motion: walking iff
>= 2 foot contacts of either leg and >= 50 % of the window moving; otherwise still. The chip's 20 features are
computed with the same C code and 6 Hz causal low-pass as the training data.

Outputs (config.out_dir('stepF', out_name)): aid_personas.csv, aid_windows_W4s.npz, streams/<persona>.npz,
plots for the test run, aid_gait_log.txt. Resume: a persona whose stream file exists is not regenerated.

CLI:
  python pipeline/aid_gait.py --max-people 2 --personas-per-person 1 --plot --out-name aid_gait_test2
  python pipeline/aid_gait.py                      # full run: 21 people x 22 personas = 462
"""
import argparse
import datetime
import json
import os
import sys
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import butter, resample_poly, sosfilt

import config
import camargo_replay as CR
import kneil_v1 as K
import stage01 as S1
import stage3 as S3

VERSION = 'aid_gait 1.0'
FS = 200.0                    # replay rate (the measured IK is low-passed at 12 Hz)
FS_OUT = 50.0                 # chip rate
WIN_S, HOP_S = 4.0, 1.0
W, H = int(WIN_S * FS_OUT), int(HOP_S * FS_OUT)
TRANSITION_S = 1.0            # stand -> walk and walk -> stand (long enough to avoid training on the transient)
EDGE_S = 0.5                 # walking samples this close to a transition are not used for training
DUR_TARGET = 36.0             # seconds per persona (27 windows at 4 s / 1 s)
N_HARM = 5                    # Fourier harmonics of a measured stride
CAMARGO = os.path.join(config.DATA_ROOT, 'Camargo et. al. 2021', 'Data')
EXCLUDED = {'ab07'}           # the viewer's 8 spacer personas are recomposed from AB07: keep it out
BANDS = ((0.15, 0.25), (0.25, 0.35), (0.35, 0.45), (0.45, 0.55))
BAND_NAMES = ('0.15-0.25', '0.25-0.35', '0.35-0.45', '0.45-0.55')
WB_GAIN = {'full': 1.0, 'partial': 0.8, 'toe-touch': 0.55, 'non-weight-bearing': 0.25}
# Soft-tissue / strap roughness of a real shank recording (the measured replay is smooth at 6 Hz): band-limited
# noise, bigger for the slower, softer walking-aid gaits. Tuned to the G2 viewer-persona hf_ratio (~0.15-0.33).
ROUGH = {'pick-up walker': 0.030, 'crutches': 0.020, 'rollator': 0.012}

# aid, speed band, weight bearing, step pattern, target pause share, long rest, turn
PERSONA_SPECS = [
    ('pick-up walker', 0, 'full', 'step-through', 0.42, True, True),
    ('pick-up walker', 0, 'partial', 'step-through', 0.40, True, False),
    ('pick-up walker', 0, 'toe-touch', 'step-through', 0.38, False, False),
    ('pick-up walker', 1, 'full', 'step-through', 0.32, False, True),
    ('pick-up walker', 1, 'partial', 'step-through', 0.30, False, False),
    ('pick-up walker', 1, 'toe-touch', 'step-through', 0.28, False, False),
    ('pick-up walker', 2, 'full', 'step-through', 0.22, False, False),
    ('pick-up walker', 2, 'partial', 'step-to', 0.20, True, False),
    ('rollator', 1, 'full', 'step-through', 0.20, False, True),
    ('rollator', 2, 'full', 'step-through', 0.18, False, False),
    ('rollator', 2, 'partial', 'step-through', 0.15, False, True),
    ('rollator', 3, 'full', 'step-through', 0.12, False, False),
    ('rollator', 3, 'partial', 'step-through', 0.10, False, False),
    ('rollator', 3, 'toe-touch', 'step-through', 0.08, False, False),
    ('rollator', 2, 'full', 'step-through', 0.05, False, False),
    ('crutches', 0, 'full', 'step-to', 0.30, True, False),
    ('crutches', 1, 'partial', 'step-to', 0.25, False, True),
    ('crutches', 1, 'toe-touch', 'step-to', 0.22, False, False),
    ('crutches', 2, 'partial', 'step-through', 0.18, False, False),
    ('crutches', 2, 'toe-touch', 'step-through', 0.15, False, False),
    ('crutches', 3, 'full', 'step-through', 0.10, False, False),
    ('crutches', 0, 'non-weight-bearing', 'step-to', 0.35, True, False),
]


def log(msg, path=None):
    line = f'[{datetime.datetime.now().strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def person_list():
    return [p for p in sorted(CR.HEIGHT) if p not in EXCLUDED]


def extract_person(root, person):
    """Extract the Camargo zip once (cache is git-ignored; the dataset itself is read-only)."""
    d = os.path.join(root, person.upper())
    if os.path.isdir(d):
        return d
    zp = os.path.join(CAMARGO, person.upper() + '.zip')
    if not os.path.exists(zp):
        raise FileNotFoundError(zp)
    os.makedirs(root, exist_ok=True)
    tmp = d + '.tmp'
    os.makedirs(tmp, exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        z.extractall(tmp)
    src = os.path.join(tmp, person.upper())
    os.replace(src, d)
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    return d


def _clean_contacts(ankle, fs):
    """Foot contacts with a 0.45 s refractory period per leg (G2 rule)."""
    raw = CR.foot_contacts(ankle, fs=fs, v_swing=-0.18, v_contact=-0.04)
    out = []
    for i in raw:
        t = i / fs
        if not out or t - out[-1] >= 0.45:
            out.append(t)
    return np.array(out, float)


def _smoothstep(u):
    """Quintic smootherstep: value and first two derivatives are continuous at both ends."""
    u = np.clip(u, 0.0, 1.0)
    return u * u * u * (u * (u * 6.0 - 15.0) + 10.0)


def stride_template(root, person, log_path):
    """Measured stride template (Fourier coefficients) + standing pose + stride length, from 2 slow trials."""
    d = extract_person(root, person)
    trials = CR.find_trials(os.path.dirname(d), person.upper(), 'levelground')
    names = [t[0] for t in trials]
    pick = [t for t in trials if 'ccw_slow' in t[0]][:2]
    if not pick:
        pick = [t for t in trials if 'ccw_normal' in t[0]][:2]
    if not pick:
        pick = [t for t in trials if 'ccw' in t[0]][:2]
    if not pick:
        pick = trials[:2]
    if not pick:
        raise RuntimeError(f'{person}: no level-ground trial in {names[:5]}...')
    m, info = CR.model_for(person)
    idx = K.qidx(m)
    phases = np.linspace(0.0, 1.0, 201)
    segs, stand, speeds, lens = [], [], [], []
    for name, ikp, _ in pick:
        ik = CR.load_table(ikp)
        _, Q = CR.ik_to_Q(m, info, ik)
        rep = CR.replay(m, Q, FS, sensors=('acc_imu', 'gyr_imu'))
        ev = _clean_contacts(rep['ankle'], FS)
        good = [i for i in range(len(ev) - 1) if 0.6 <= ev[i + 1] - ev[i] <= 2.5]
        for i in good:
            a, b = int(round(ev[i] * FS)), int(round(ev[i + 1] * FS))
            if b - a < 20:
                continue
            seg = Q[a:b + 1]
            ph = np.linspace(0.0, 1.0, len(seg))
            seg2 = np.column_stack([np.interp(phases, ph, seg[:, k]) for k in range(seg.shape[1])])
            segs.append(seg2)
            tx, tz = seg2[:, idx['pelvis_tx']], seg2[:, idx['pelvis_tz']]
            lens.append(float(np.hypot(tx[-1] - tx[0], tz[-1] - tz[0])))
        kin = CR.kinematic_labels(Q, idx, rep['ankle'], fs=FS, mode='levelground')
        st = Q[kin == 0]
        if len(st) < 50:
            st = np.vstack([Q[:100], Q[-100:]])
        stand.append(np.median(st, axis=0))
        sp = CR.walking_speed_at(Q, idx, rep['ankle'], np.round(ev * FS).astype(int), fs=FS)
        if np.isfinite(sp).any():
            speeds.append(float(np.nanmedian(sp)))
    if len(segs) < 4:
        raise RuntimeError(f'{person}: only {len(segs)} usable strides')
    S = np.stack(segs)                                   # (n_strides, 201, nq)
    med = np.median(S, axis=0)
    coef = {}
    for nm, a in idx.items():
        if nm.startswith('knee_t'):
            continue
        y = med[:, a]
        if nm in ('pelvis_tx', 'pelvis_ty'):
            y = y - (y[0] + (y[-1] - y[0]) * phases)
            nh = 3
        elif nm == 'pelvis_rotation':
            nh = 3
        else:
            nh = N_HARM
        coef[nm] = K.fourier_fit(phases[:-1], y[:-1], nh)
    ty_mean = float(np.mean(med[:, idx['pelvis_ty']]))
    L = float(np.median(lens))
    if not np.isfinite(L) or L < 0.25:
        L = 0.9
    log(f'{person}: {len(pick)} trials, {len(segs)} strides, L={L:.3f} m, base speed '
        f'{(np.median(speeds) if speeds else float("nan")):.2f} m/s', log_path)
    return dict(coef=coef, ty_mean=ty_mean, L=L, stand=np.median(np.stack(stand), axis=0),
                idx=idx, m=m, info=info, geom=dict(femur=info['femur'], tibia=info['tibia'],
                                                   pelvis=info['pelvis'], imu_side=info['imu_side']),
                n_strides=len(segs))


def _blend(a, va, b, vb, n):
    """Cubic Hermite blend from row a (slope va per sample) to b (slope vb), n samples, endpoint exact."""
    if n <= 0:
        return np.empty((0, len(a)))
    u = np.arange(1, n + 1) / n
    h00 = 2 * u ** 3 - 3 * u ** 2 + 1
    h10 = u ** 3 - 2 * u ** 2 + u
    h01 = -2 * u ** 3 + 3 * u ** 2
    h11 = u ** 3 - u ** 2
    a, b = np.asarray(a), np.asarray(b)
    return (h00[:, None] * a[None, :] + h10[:, None] * n * np.asarray(va)[None, :] +
            h01[:, None] * b[None, :] + h11[:, None] * n * np.asarray(vb)[None, :])


def _walk_chunk(tpl, T, n_cycles, amp, yaw, turn_deg, rng):
    idx = tpl['idx']
    n = max(10, int(round(n_cycles * T * FS)))
    t = np.arange(n) / FS
    r = K.smooth_noise(t, T, 0.03, rng) if n > 20 else np.zeros(n)
    phi = np.cumsum(1.0 / (T * (1.0 + r))) / FS
    phi *= n_cycles / phi[-1]                       # end exactly at phase 0 (heel strike, close to standing)
    ph = phi % 1.0
    Q = np.zeros((n, tpl['m'].nq))
    for nm, c in tpl['coef'].items():
        y = K.fourier_eval(c, ph)
        if nm == 'pelvis_tx':
            Q[:, idx[nm]] = tpl['_tx0'] + tpl['L_eff'] * phi + y
        elif nm == 'pelvis_ty':
            Q[:, idx[nm]] = tpl['ty_mean'] + y
        elif nm in ('pelvis_tz', 'pelvis_rotation'):
            Q[:, idx[nm]] = y
        else:
            Q[:, idx[nm]] = c[0] + amp * (y - c[0])
    if turn_deg:
        u = _smoothstep(t / max(0.8, min(2.5, 0.5 * n / FS)))
        Q[:, idx['pelvis_rotation']] += np.radians(turn_deg) * u
    Q[:, idx['pelvis_rotation']] += yaw
    dist = float(tpl['L_eff'] * phi[-1])
    return Q, np.ones(n), yaw + np.radians(turn_deg), dist


def _stand_chunk(tpl, dur, tx, tz, yaw, rng):
    idx = tpl['idx']
    n = max(1, int(round(dur * FS)))
    Q = np.tile(tpl['stand'], (n, 1))
    Q[:, idx['pelvis_tx']] = tx
    Q[:, idx['pelvis_tz']] = tz
    Q[:, idx['pelvis_rotation']] += yaw
    t = np.arange(n) / FS
    ph = rng.uniform(0, 2 * np.pi, 6)
    Q[:, idx['pelvis_tilt']] += np.radians(0.35) * np.sin(2 * np.pi * 0.22 * t + ph[0])
    Q[:, idx['pelvis_list']] += np.radians(0.30) * np.sin(2 * np.pi * 0.17 * t + ph[1])
    Q[:, idx['pelvis_rotation']] += np.radians(0.20) * np.sin(2 * np.pi * 0.13 * t + ph[2])
    Q[:, idx['hip_flexion_r']] += np.radians(0.20) * np.sin(2 * np.pi * 0.25 * t + ph[3])
    Q[:, idx['knee_angle_r']] += np.radians(0.25) * np.sin(2 * np.pi * 0.19 * t + ph[4])
    return Q, np.zeros(n)


def _held_right_leg(tpl, Q):
    """Non-weight-bearing: the implant leg is held still relative to the pelvis (crutches, left leg steps)."""
    idx = tpl['idx']
    hold = {'hip_flexion_r': 22.0, 'hip_adduction_r': 4.0, 'hip_rotation_r': 0.0,
            'knee_angle_r': 48.0, 'ankle_angle_r': -5.0, 'subtalar_angle_r': 0.0, 'mtp_angle_r': 0.0}
    for k, v in hold.items():
        if k in idx:
            Q[:, idx[k]] = np.radians(v)
    return Q


def _ankles(m, Q):
    import mujoco
    d = mujoco.MjData(m)
    ar, al = m.site('ankle_r').id, m.site('ankle_l').id
    pr, pl = np.zeros((len(Q), 3)), np.zeros((len(Q), 3))
    for i in range(len(Q)):
        d.qpos[:] = Q[i]
        mujoco.mj_kinematics(m, d)
        pr[i], pl[i] = d.site_xpos[ar], d.site_xpos[al]
    return pr, pl


def _build_motion(tpl, spec, rng, v_target, pause_target, long_rest, turn):
    """One persona at 200 Hz: Q, moving mask, measured speed/pause/cadence."""
    aid, _, wb, step, _, _, _ = spec
    fs = FS
    step_factor = 0.62 if step == 'step-to' else 1.0
    tpl = dict(tpl)
    tpl['L_eff'] = tpl['L'] * step_factor * rng.uniform(0.9, 1.1)
    # T so that the average speed including transitions and pauses hits v_target:
    #   v_avg = N*L_eff*(1-pause) / (N*T + 2*TRANSITION), N ~ 6 cycles per chunk
    # step-to advances only L_eff per cycle: use the full measured stride length for the joint timing, so the
    # legs move at a plausible (slower) speed instead of a doubled cadence.
    L_T = tpl['L'] if step == 'step-to' else tpl['L_eff']
    T = L_T * max(0.12, 1.0 - pause_target) / max(0.08, v_target) - 2.0 * TRANSITION_S / 6.0
    T = max(0.35, T)
    amp = float(np.clip(rng.normal(1.0, 0.06), 0.85, 1.15))
    amp *= {'pick-up walker': 0.90, 'crutches': 0.95, 'rollator': 1.0}[aid]
    if step == 'step-to':
        amp *= 0.80
    segs = []                    # walk segments (Q, moving) and pause descriptors
    tx, tz, yaw = 0.0, 0.0, 0.0
    segs.append(dict(kind='stand', dur=1.6, tx=tx, tz=tz, yaw=yaw, moving=0))
    last = _stand_chunk(tpl, 1.6, tx, tz, yaw, rng)[0][-1]
    walk_total = 0.0
    while walk_total < (DUR_TARGET - 2.0) * (1.0 - pause_target):
        n_cycles = int(rng.integers(4, 9))
        turn_here = turn and (walk_total == 0.0 or rng.random() < 0.35)
        turn_deg = float(rng.choice([-45.0, -30.0, 30.0, 45.0])) if turn_here else 0.0
        tpl['_tx0'] = tx
        Qw, mw, yaw2, dist = _walk_chunk(tpl, T, n_cycles, amp, yaw, turn_deg, rng)
        pre = _blend(last, np.zeros_like(last), Qw[0], Qw[1] - Qw[0], int(TRANSITION_S * fs))
        segs.append(dict(kind='walk', Q=pre, moving=np.ones(len(pre), np.float32),
                         edge=np.ones(len(pre), np.float32)))
        edge_w = np.zeros(len(Qw), np.float32)
        n_edge = min(len(edge_w), int(EDGE_S * fs))
        edge_w[:n_edge] = 1.0
        edge_w[-n_edge:] = 1.0
        segs.append(dict(kind='walk', Q=Qw, moving=mw.astype(np.float32), edge=edge_w))
        tx0 = tx + dist
        stand_row = _stand_chunk(tpl, 1.0 / fs, tx0, tz, yaw2, rng)[0][0]
        post = _blend(Qw[-1], Qw[-1] - Qw[-2], stand_row, np.zeros_like(stand_row),
                      int(TRANSITION_S * fs))
        segs.append(dict(kind='walk', Q=post, moving=np.ones(len(post), np.float32),
                         edge=np.ones(len(post), np.float32)))
        walk_total += (len(pre) + len(Qw) + len(post)) / fs
        last = post[-1]
        tx, yaw = tx0, yaw2
        if long_rest and rng.random() < 0.35:
            pause = rng.uniform(5.0, 9.0)
        else:
            pause = float(np.clip(rng.lognormal(0.0, 0.45), 0.4, 3.0))
        segs.append(dict(kind='stand', dur=pause, tx=tx, tz=tz, yaw=yaw, moving=0))
    segs.append(dict(kind='stand', dur=1.8, tx=tx, tz=tz, yaw=yaw, moving=0))
    # make the pause share match the target (the walking part defines the speed)
    n_walk = sum(len(s['Q']) for s in segs if s['kind'] == 'walk')
    n_pause = sum(max(1, int(round(s['dur'] * fs))) for s in segs if s['kind'] == 'stand')
    want_pause = n_walk * pause_target / max(0.05, 1.0 - pause_target)
    scale = float(np.clip(want_pause / max(1, n_pause), 0.25, 3.0))
    Qs, movs, edges = [], [], []
    for s in segs:
        if s['kind'] == 'walk':
            Qs.append(s['Q']); movs.append(np.full(len(s['Q']), 1.0, np.float32))
            edges.append(s['edge'])
        else:
            Qp, mp = _stand_chunk(tpl, max(0.3, s['dur'] * scale), s['tx'], s['tz'], s['yaw'], rng)
            Qs.append(Qp); movs.append(mp.astype(np.float32)); edges.append(np.zeros(len(Qp), np.float32))
    Q = np.vstack(Qs)
    moving = np.concatenate(movs)
    edge = np.concatenate(edges)
    if wb == 'non-weight-bearing':
        Q = _held_right_leg(tpl, Q)
    K.set_knee_translations(Q, tpl['idx'], tpl['info'])
    # measured speed and pause from the generated motion (net forward displacement, not path length)
    txv, tzv = Q[:, tpl['idx']['pelvis_tx']], Q[:, tpl['idx']['pelvis_tz']]
    dist = float(np.hypot(txv[-1] - txv[0], tzv[-1] - tzv[0]))
    dur = len(Q) / fs
    v_avg = dist / dur
    move_s = float(moving.sum()) / fs
    pause_share = 1.0 - move_s / dur
    v_mov = dist / move_s if move_s > 0 else 0.0
    return Q, moving, edge, dict(v_target=float(v_target), v_avg=float(v_avg), v_moving=float(v_mov),
                                 pause_share=float(pause_share), T_stride=float(T), duration=float(dur))


def _rotate_acc(a, yaw_deg, pitch_deg, roll_deg):
    """Rotate the implant accelerometer into a slightly different mount frame (as the per-person mount in
    kneil_v1.sample_sensor): yaw about z, pitch about y, roll about x."""
    y, p, r = np.radians([yaw_deg, pitch_deg, roll_deg])
    Rz = np.array([[np.cos(y), -np.sin(y), 0], [np.sin(y), np.cos(y), 0], [0, 0, 1]])
    Ry = np.array([[np.cos(p), 0, np.sin(p)], [0, 1, 0], [-np.sin(p), 0, np.cos(p)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(r), -np.sin(r)], [0, np.sin(r), np.cos(r)]])
    return a @ (Rz @ Ry @ Rx).T


def _bands(v):
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= v < hi or (i == len(BANDS) - 1 and v <= hi):
            return BAND_NAMES[i]
    return BAND_NAMES[0] if v < BANDS[0][0] else BAND_NAMES[-1]


def make_persona(tpl, person, spec, index, rng, out_stream, lib, log_path):
    aid, band, wb, step, pause, rest, turn = spec
    lo, hi = BANDS[band]
    v_target = float(rng.uniform(lo + 0.005, hi - 0.005))
    pause_target = float(np.clip(pause + rng.normal(0, 0.03), 0.0, 0.45))
    Q, moving, edge, kin = _build_motion(tpl, spec, rng, v_target, pause_target, rest, turn)
    m = tpl['m']
    rep = CR.replay(m, Q, FS, sensors=('acc_imu', 'gyr_imu'))
    gain = WB_GAIN[wb]
    acc200 = CR.scale_dynamic(rep['acc_imu'], rep['grav_acc_imu'], gain)
    n50 = len(Q) // 4
    acc50 = resample_poly(acc200, 1, 4, axis=0)[:n50].astype(np.float32)
    moving50 = moving[::4][:n50]
    edge50 = edge[::4][:n50]
    Q50 = Q[::4][:n50]
    acc50 += rng.normal(0.0, 0.010, acc50.shape).astype(np.float32)   # sensor noise floor, as in real still
    rough = rng.normal(0.0, ROUGH.get(aid, 0.02), acc50.shape)
    rough = sosfilt(butter(2, [2.0, 8.0], btype='band', fs=FS_OUT, output='sos'), rough, axis=0)
    acc50 += (rough * moving50[:, None]).astype(np.float32)           # soft-tissue roughness only while moving
    mount_yaw = float(np.clip(rng.normal(0, 7), -15, 15))
    mount_pitch = float(np.clip(rng.normal(9 if aid == 'pick-up walker' else 0, 5), -12, 20))
    mount_roll = float(np.clip(rng.normal(0, 4), -12, 12))
    acc50 = _rotate_acc(acc50, mount_yaw, mount_pitch, mount_roll).astype(np.float32)
    pr, pl = _ankles(m, Q50)
    cr = _clean_contacts(pr, FS_OUT)
    cl = _clean_contacts(pl, FS_OUT)
    contacts = np.sort(np.r_[cr, cl])
    dur = n50 / FS_OUT
    cadence = 60.0 * len(contacts) / dur if dur else 0.0
    t = np.arange(n50) / FS_OUT
    # windows and rule C labels; `usable` skips the walking<->standing transients from training
    a_lp = S3.T.apply_lowpass(acc50.astype(np.float64), FS_OUT, 6.0).astype(np.float32)
    X, y, steps, wmove, wstart, usable, wedge = [], [], [], [], [], [], []
    for s in range(0, n50 - W + 1, H):
        t0, t1 = s / FS_OUT, (s + W) / FS_OUT
        n_steps = int(((contacts >= t0) & (contacts < t1)).sum())
        move = float(moving50[s:s + W].mean())
        edge_share = float(edge50[s:s + W].mean())
        lab = 0 if (n_steps >= 2 and move >= 0.5) else 3
        ok = ((lab == 0 and n_steps >= 2 and move >= 0.50) or
              (lab == 3 and n_steps == 0 and move <= 0.10 and edge_share == 0.0))
        X.append(S3.T.features(lib, a_lp[s:s + W, 0], a_lp[s:s + W, 1], a_lp[s:s + W, 2], FS_OUT))
        y.append(lab); steps.append(n_steps); wmove.append(move); wstart.append(t0)
        usable.append(bool(ok)); wedge.append(edge_share)
    X = np.asarray(X, np.float32).reshape(-1, 20)
    y = np.asarray(y, np.int16); steps = np.asarray(steps, np.int16)
    wmove = np.asarray(wmove, np.float32); wstart = np.asarray(wstart, np.float32)
    usable = np.asarray(usable, bool); wedge = np.asarray(wedge, np.float32)
    pid = f'{person}_p{index:02d}_{aid.replace(" ", "")}_{step}_{wb}'
    meta = dict(persona=pid, grp=person, aid=aid, speed_band=_bands(kin['v_avg']),
                speed_band_target=BAND_NAMES[band], wb=wb, step=step,
                v_target=kin['v_target'], v_avg=kin['v_avg'], v_moving=kin['v_moving'],
                pause_share=kin['pause_share'], T_stride=kin['T_stride'], duration=kin['duration'],
                cadence=cadence, n_steps=len(contacts), n_windows=len(y),
                n_walking=int((y == 0).sum()), n_still=int((y == 3).sum()),
                n_usable=int(usable.sum()), n_usable_walking=int((usable & (y == 0)).sum()),
                n_usable_still=int((usable & (y == 3)).sum()),
                long_rest=bool(rest), turn=bool(turn), gain=gain,
                mount_yaw=mount_yaw, mount_pitch=mount_pitch, mount_roll=mount_roll)
    np.savez_compressed(out_stream, acc=acc50, t=t.astype(np.float32), X=X, y=y, steps=steps,
                        moving_share=wmove, win_start=wstart, usable=usable, edge_share=wedge,
                        contact_r=cr.astype(np.float32), contact_l=cl.astype(np.float32), meta=json.dumps(meta))
    log(f'{pid}: {dur:.1f} s, v_avg {kin["v_avg"]:.2f} m/s, pause {100*kin["pause_share"]:.0f} %, '
        f'{len(contacts)} contacts, windows {len(y)} (walk {int((y == 0).sum())}, still {int((y == 3).sum())}; '
        f'usable {int(usable.sum())})', log_path)
    return meta, X, y, usable


def plot_stream(path, out_png):
    Z = np.load(path, allow_pickle=True)
    meta = json.loads(str(Z['meta']))
    acc, t, y, steps = Z['acc'], Z['t'], Z['y'], Z['steps']
    fig, ax = plt.subplots(3, 1, figsize=(12, 8), sharex=True,
                           gridspec_kw=dict(height_ratios=[2.2, 1.4, 0.9]))
    for k, name in enumerate('xyz'):
        ax[0].plot(t, acc[:, k], lw=0.8, label=f'acc {name} (g)')
    ax[0].plot(t, np.linalg.norm(acc, axis=1), color='k', lw=1.0, label='|a| (g)')
    for s, lab in zip(Z['win_start'], y):
        ax[0].axvspan(s, s + WIN_S, color=('#2e9e44' if lab == 0 else '#2166d6'), alpha=0.10, lw=0)
        ax[1].axvspan(s, s + WIN_S, color=('#2e9e44' if lab == 0 else '#2166d6'), alpha=0.10, lw=0)
    for s, ok in zip(Z['win_start'], Z['usable']):
        if not ok:
            ax[1].axvspan(s, s + WIN_S, color='#999999', alpha=0.18, lw=0)
    ax[0].plot(Z['contact_r'], np.full(len(Z['contact_r']), 1.6), '|', color='#d95f02', ms=10, label='right contact')
    ax[0].plot(Z['contact_l'], np.full(len(Z['contact_l']), 1.6), '|', color='#7570b3', ms=10, label='left contact')
    ax[0].set_ylabel('implant acc (g)'); ax[0].legend(loc='upper right', ncol=3, fontsize=8)
    ax[0].set_title(f'{meta["persona"]} | {meta["aid"]}, {meta["wb"]}, {meta["step"]} | '
                    f'v_avg {meta["v_avg"]:.2f} m/s, pause {100*meta["pause_share"]:.0f} %, '
                    f'{meta["n_walking"]}/{meta["n_windows"]} windows walking (rule C), '
                    f'{meta["n_usable"]} usable')
    ax[1].plot(Z['win_start'] + WIN_S / 2, Z['moving_share'], 'o-', color='#666666', ms=4, label='moving share')
    ax[1].plot(Z['win_start'] + WIN_S / 2, steps / 4.0, 's-', color='#c65102', ms=4,
               label='steps per window / 4')
    ax[1].set_ylim(-0.05, 1.05); ax[1].set_ylabel('share'); ax[1].legend(loc='upper right', fontsize=8)
    ax[2].bar(Z['win_start'] + WIN_S / 2, steps, width=0.8, color='#4d8dff')
    ax[2].set_ylabel('steps / window'); ax[2].set_xlabel('time (s)')
    ax[2].set_yticks(range(0, int(steps.max()) + 2 if len(steps) else 1))
    fig.tight_layout(); fig.savefig(out_png, dpi=110); plt.close(fig)


def combine(out_dir):
    stream_dir = os.path.join(out_dir, 'streams')
    files = sorted(f for f in os.listdir(stream_dir) if f.endswith('.npz'))
    if not files:
        raise RuntimeError('no streams')
    metas, Xs, ys, steps, mov, wst, usable, wedge = [], [], [], [], [], [], [], []
    for f in files:
        Z = np.load(os.path.join(stream_dir, f), allow_pickle=True)
        meta = json.loads(str(Z['meta']))
        metas.append(meta); Xs.append(Z['X']); ys.append(Z['y'])
        steps.append(Z['steps']); mov.append(Z['moving_share']); wst.append(Z['win_start'])
        usable.append(Z['usable']); wedge.append(Z['edge_share'])
    X = np.vstack(Xs); y = np.concatenate(ys)
    R = pd.DataFrame(metas)
    R.to_csv(os.path.join(out_dir, 'aid_personas.csv'), index=False)
    lens = [len(v) for v in ys]

    def expand(key):
        return np.concatenate([np.full(n, m[key], dtype=object) for n, m in zip(lens, metas)])

    steps = np.concatenate(steps); mov = np.concatenate(mov); wst = np.concatenate(wst)
    usable = np.concatenate(usable); wedge = np.concatenate(wedge)
    np.savez_compressed(os.path.join(out_dir, 'aid_windows_W4s.npz'), X=X, y=y, steps=steps, moving_share=mov,
                        win_start=wst, usable=usable, edge_share=wedge, grp=expand('grp'), aid=expand('aid'),
                        speed_band=expand('speed_band'), wb=expand('wb'), step=expand('step'),
                        persona=expand('persona'), src=np.full(len(y), 'aid', dtype=object),
                        ds=np.full(len(y), 'Aid gait', dtype=object), W=np.float64(WIN_S))
    return R, X, y, steps


def _md_table(df):
    head = '| ' + ' | '.join([str(df.index.name or '')] + [str(c) for c in df.columns]) + ' |'
    sep = '|' + '---|' * (len(df.columns) + 1)
    body = ['| ' + ' | '.join([str(i)] + [str(v) for v in r]) + ' |' for i, r in df.iterrows()]
    return '\n'.join([head, sep] + body)


def summary_tables(R, out_dir):
    """Acceptance check 2: counts by aid, speed band, weight bearing and rule-C windows."""
    t = R.copy()
    t['windows_walking'] = t['n_walking']; t['windows_still'] = t['n_still']
    t['windows_usable'] = t['n_usable']; t['usable_walking'] = t['n_usable_walking']
    t['usable_still'] = t['n_usable_still']
    by_aid = t.groupby('aid')[['n_windows', 'windows_walking', 'windows_still', 'windows_usable']].sum()
    by_band = t.groupby('speed_band')[['n_windows', 'windows_walking', 'windows_still', 'windows_usable']].sum()
    by_wb = t.groupby('wb')[['n_windows', 'windows_walking', 'windows_still', 'windows_usable']].sum()
    by_aid_band = pd.crosstab(t['aid'], t['speed_band'], values=t['n_windows'], aggfunc='sum').fillna(0).astype(int)
    lines = ['# Aid-gait personas (step F)', '',
             f'Source people: {t["grp"].nunique()} (Camargo, AB07 excluded). Personas: {len(t)}. '
             f'Windows: {int(t["n_windows"].sum())} (walking by rule C: {int(t["n_walking"].sum())}, '
             f'still: {int(t["n_still"].sum())}); usable for training: {int(t["n_usable"].sum())} '
             f'({int(t["n_usable_walking"].sum())} walking, {int(t["n_usable_still"].sum())} still).', '',
             'Usable = rule C walking (>= 2 steps, >= 50 % moving; start/stop windows included) or a clean pause '
             'for still (no step, <= 10 % moving, no transient).', '',
             '## Personas by aid', '', _md_table(by_aid), '',
             '## Personas by achieved speed band', '', _md_table(by_band), '',
             '## Personas by weight bearing', '', _md_table(by_wb), '',
             '## Persona windows: aid x achieved speed band', '', _md_table(by_aid_band), '']
    path = os.path.join(out_dir, 'AID_summary.md')
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    return path


def main():
    ap = argparse.ArgumentParser(description='KNEIL A1: walking-aid personas from the Camargo replay')
    ap.add_argument('--people', nargs='+', default=None, help='source people (default: all except AB07)')
    ap.add_argument('--max-people', type=int, default=None)
    ap.add_argument('--personas-per-person', type=int, default=len(PERSONA_SPECS))
    ap.add_argument('--max-personas', type=int, default=None)
    ap.add_argument('--out-name', default='aid_gait')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--plot', action='store_true')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    print(VERSION, flush=True)
    out_dir = config.out_dir('stepF', a.out_name)
    log_path = os.path.join(out_dir, 'aid_gait_log.txt')
    with S1.Tee(log_path):
        print(f'{VERSION} | {config.VERSION} | {np.datetime64("now", "s")}')
        print(f'out {out_dir} | people {a.people or "all-AB07"} | max_people {a.max_people} | '
              f'personas/person {a.personas_per_person} | max_personas {a.max_personas}')
        os.makedirs(os.path.join(out_dir, 'streams'), exist_ok=True)
        lib = S3.init_tinyml()
        root = os.path.join(config.CACHE, 'aid', 'camargo')
        people = person_list()
        if a.people:
            people = [p.lower() for p in a.people if p.lower() not in EXCLUDED]
        if a.max_people is not None:
            people = people[:a.max_people]
        tpls = {}
        made = 0
        for person in people:
            tpl = stride_template(root, person, log_path)
            tpls[person] = tpl
            rng = np.random.default_rng(a.seed + 1000 * person_list().index(person))
            for i, spec in enumerate(PERSONA_SPECS[:a.personas_per_person]):
                if a.max_personas is not None and made >= a.max_personas:
                    break
                aid, band, wb, step, _, _, _ = spec
                pid = f'{person}_p{i:02d}_{aid.replace(" ", "")}_{step}_{wb}'
                path = os.path.join(out_dir, 'streams', pid + '.npz')
                if os.path.exists(path) and not a.force:
                    log(f'{pid}: cached', log_path)
                else:
                    make_persona(tpl, person, spec, i, rng, path, lib, log_path)
                made += 1
            if a.max_personas is not None and made >= a.max_personas:
                break
        R, X, y, steps = combine(out_dir)
        log(f'personas {len(R)}, windows {len(y)}, walking {int((y == 0).sum())}, still {int((y == 3).sum())}',
            log_path)
        summary_tables(R, out_dir)
        if a.plot:
            plot_dir = os.path.join(out_dir, 'plots'); os.makedirs(plot_dir, exist_ok=True)
            for _, r in R.iterrows():
                p = os.path.join(out_dir, 'streams', r['persona'] + '.npz')
                plot_stream(p, os.path.join(plot_dir, r['persona'] + '.png'))
                log(f'plot {os.path.join(plot_dir, r["persona"] + ".png")}', log_path)
        log(f'saved {os.path.join(out_dir, "aid_windows_W4s.npz")}', log_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())




