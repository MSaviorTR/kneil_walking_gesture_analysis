"""
KNEIL S1: Merge stairs and ramps into "going up" / "going down"? (experiment only).
   cv_updown 1.0, 24 Nov 2026

5-fold cross-validation by person, 3 seeds, W = 4 s, hop 1 s, 8 classes, V4half settings.
Outputs strictly under config.out_dir('stepG') (KNEIL_results/v4/stepG/).
No export, no chip/library/protocol change.

Variants:
  1. V4half    : baseline today (ramps unseen in training; evaluated on ramps)
  2. R-walk    : all ramp windows labelled walking (class 0)
  3. M-all     : classes 1/2 = stairs + all ramps (Camargo real+sim + Luo SlpU/SlpD)
  4. M-steep8  : Camargo ramps >= 8 deg -> up/down (1/2), < 8 deg -> walking (0); Luo slopes evaluated only
  5. M-steep10 : Camargo ramps >= 10 deg -> up/down (1/2), < 10 deg -> walking (0); Luo slopes evaluated only
Vote-share rule sweep: theta in (0.5, 0.6, 0.7, 0.8) for merged variants (0.6 default).

Usage:
  python pipeline/cv_updown.py --max-people 2 --seeds 0 --variants V4half M-all
  python pipeline/cv_updown.py
"""
import argparse
import os
import re
import sys
import tempfile
import time
import zipfile

import numpy as np
import pandas as pd
from scipy.signal import resample_poly

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE_DIR = os.path.join(REPO_ROOT, 'pipeline')
if PIPE_DIR not in sys.path:
    sys.path.insert(0, PIPE_DIR)

import config
import camargo_replay as CR
import cv_v4 as C
import stage01 as S1
import stage3 as S3
import transition_events as TE
import vimp as V

VERSION = 'cv_updown 1.0'
FS_IN = 200.0
FS_OUT = 50.0
WIN = 4
W = int(WIN * FS_OUT)
H = int(1.0 * FS_OUT)
CLASSES8 = C.CLASSES8
VARIANTS = ('V4half', 'R-walk', 'M-all', 'M-steep8', 'M-steep10')
THETAS = (0.50, 0.60, 0.70, 0.80)
CAMARGO_DATA = os.path.join(config.DATA_ROOT, 'Camargo et. al. 2021', 'Data')
BASE_V4 = os.path.join(config.RESULTS, 'v4')

# Exact surveyed Camargo ramp inclinations (degrees) from conditions/ramp_<k>_*.mat
RAMP_ANGLES = {1: 5.2, 2: 7.8, 3: 9.2, 4: 11.0, 5: 12.4, 6: 18.0}


def log_msg(msg, path):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def rule_theta(pred, proba, theta):
    """Evidence rule: up/down (classes 1, 2) stay only with vote share >= theta; else walking (0)."""
    out = np.asarray(pred).copy()
    p = np.asarray(proba)
    pa = np.zeros(len(out), np.float32)
    ok = out >= 0
    pa[ok] = p[np.flatnonzero(ok), out[ok]]
    ud = np.isin(out, (1, 2))
    out[ud & (pa < theta)] = 0
    return out


def chip_windows(acc50, labels50, lib, min_share=0.60):
    """Compute 4 s / 1 s hop 20-feature chip windows after 6 Hz causal LP; return (X, y_maj)."""
    if len(acc50) < W:
        return np.empty((0, 20), np.float32), np.empty((0,), np.int16)
    a_lp = S3.T.apply_lowpass(np.asarray(acc50, np.float64), FS_OUT, 6.0).astype(np.float32)
    Xs, ys = [], []
    for s in range(0, len(a_lp) - W + 1, H):
        lw = labels50[s:s + W]
        vals, cnts = np.unique(lw, return_counts=True)
        bi = int(np.argmax(cnts))
        if cnts[bi] / float(W) < min_share:
            continue
        Xs.append(S3.T.features(lib, a_lp[s:s + W, 0], a_lp[s:s + W, 1], a_lp[s:s + W, 2], FS_OUT))
        ys.append(int(vals[bi]))
    if not Xs:
        return np.empty((0, 20), np.float32), np.empty((0,), np.int16)
    return np.asarray(Xs, np.float32).reshape(-1, 20), np.asarray(ys, np.int16)


def _extract_shank_imu(df):
    f = df[['shank_Accel_X', 'shank_Accel_Y', 'shank_Accel_Z']].values.astype(np.float64)
    w = df[['shank_Gyro_X', 'shank_Gyro_Y', 'shank_Gyro_Z']].values.astype(np.float64)
    return f, w


def extract_camargo_person(person, lib, cache_dir, log, max_trials_per_incline=4):
    """Extract Camargo ramp (real vimp + sim replay) and treadmill >= 1.4 m/s windows for one person."""
    out_p = os.path.join(cache_dir, f'{person}.npz')
    if os.path.exists(out_p):
        Z = np.load(out_p, allow_pickle=True)
        return {k: Z[k] for k in Z.files}

    zp = os.path.join(CAMARGO_DATA, person.upper() + '.zip')
    if not os.path.exists(zp):
        raise FileNotFoundError(zp)

    t0 = time.time()
    m, info = CR.model_for(person)
    idx = CR.K.qidx(m)

    rows_X, rows_y, rows_src, rows_ds, rows_grp, rows_slope = [], [], [], [], [], []
    tm_X, tm_src, tm_ds, tm_grp = [], [], [], []

    with zipfile.ZipFile(zp) as zf, tempfile.TemporaryDirectory() as td:
        names = zf.namelist()
        # Select ramp trials: up to max_trials_per_incline per incline (1..6), balanced l/r
        ramp_ik = sorted(n for n in names if '/ramp/ik/' in n and n.endswith('.mat'))
        by_inc = {k: [] for k in range(1, 7)}
        for n in ramp_ik:
            mm = re.search(r'ramp_(\d)_', os.path.basename(n))
            if mm:
                inc = int(mm.group(1))
                if inc in by_inc:
                    by_inc[inc].append(n)

        selected_ramps = []
        for inc in range(1, 7):
            ls = [n for n in by_inc[inc] if '_l_' in os.path.basename(n)]
            rs = [n for n in by_inc[inc] if '_r_' in os.path.basename(n)]
            half = max(1, max_trials_per_incline // 2)
            pick = ls[:half] + rs[:half]
            if len(pick) < max_trials_per_incline:
                rest = [n for n in by_inc[inc] if n not in pick]
                pick += rest[:max_trials_per_incline - len(pick)]
            for n in pick:
                selected_ramps.append((inc, n))

        # Calibrate person_frame T once using first few ramp trials (contain standing + walking)
        cal_rec = []
        for _, ik_n in selected_ramps[:6]:
            imu_n = ik_n.replace('/ik/', '/imu/')
            if imu_n in names:
                df_i = CR.load_table(zf.extract(imu_n, td))
                if 'shank_Accel_X' in df_i.columns and len(df_i) >= 400:
                    cal_rec.append(_extract_shank_imu(df_i))
        T_person, _ = V.person_frame(cal_rec, cal_rec, FS_IN) if cal_rec else (None, 'none')

        # Process selected ramp trials
        for inc, ik_n in selected_ramps:
            angle = RAMP_ANGLES[inc]
            imu_n = ik_n.replace('/ik/', '/imu/')
            try:
                ik = CR.load_table(zf.extract(ik_n, td))
                _, Q = CR.ik_to_Q(m, info, ik, fs_out=FS_IN)
                rep = CR.replay(m, Q, FS_IN, sensors=('acc_imu',))
                labs200 = CR.kinematic_labels(Q, idx, rep['ankle'], fs=FS_IN, mode='ramp')
                # Keep only ramp_up (4 -> 1) and ramp_down (5 -> 2)
                n50 = len(Q) // 4
                acc_sim50 = resample_poly(rep['acc_imu'], 1, 4, axis=0)[:n50].astype(np.float32)
                labs50 = labs200[::4][:n50]
                Xs, ys = chip_windows(acc_sim50, labs50, lib, min_share=0.60)
                keep = np.isin(ys, (4, 5))
                if keep.any():
                    y_ud = np.where(ys[keep] == 4, 1, 2).astype(np.int16)
                    rows_X.append(Xs[keep])
                    rows_y.append(y_ud)
                    n_k = int(keep.sum())
                    rows_src.append(np.full(n_k, 'sim', dtype=object))
                    rows_ds.append(np.full(n_k, 'Camargo ramp sim', dtype=object))
                    rows_grp.append(np.full(n_k, person, dtype=object))
                    rows_slope.append(np.full(n_k, angle, dtype=np.float32))

                # Real shank IMU through vimp
                if imu_n in names:
                    df_i = CR.load_table(zf.extract(imu_n, td))
                    if 'shank_Accel_X' in df_i.columns and len(df_i) >= W * 4:
                        f_s, w_s = _extract_shank_imu(df_i)
                        acc_v200, _ = V.virtual_implant(f_s, w_s, FS_IN, distance=0.22, anterior=-0.02,
                                                        side='R', T=T_person)
                        n50r = min(len(acc_v200) // 4, len(labs50))
                        acc_real50 = resample_poly(acc_v200, 1, 4, axis=0)[:n50r].astype(np.float32)
                        Xr, yr = chip_windows(acc_real50, labs50[:n50r], lib, min_share=0.60)
                        keepr = np.isin(yr, (4, 5))
                        if keepr.any():
                            y_udr = np.where(yr[keepr] == 4, 1, 2).astype(np.int16)
                            rows_X.append(Xr[keepr])
                            rows_y.append(y_udr)
                            n_kr = int(keepr.sum())
                            rows_src.append(np.full(n_kr, 'real', dtype=object))
                            rows_ds.append(np.full(n_kr, 'Camargo ramp real', dtype=object))
                            rows_grp.append(np.full(n_kr, person, dtype=object))
                            rows_slope.append(np.full(n_kr, angle, dtype=np.float32))
            except Exception as exc:
                log(f'  skip {person}/{os.path.basename(ik_n)}: {exc}')

        # Extract Camargo treadmill >= 1.4 m/s (for fast-walking false-up/down check)
        tm_ik_list = sorted(n for n in names if '/treadmill/ik/' in n and n.endswith('.mat'))
        import matio
        for ik_n in tm_ik_list:
            cond_n = ik_n.replace('/ik/', '/conditions/')
            imu_n = ik_n.replace('/ik/', '/imu/')
            if cond_n not in names:
                continue
            try:
                cd = matio.load_from_mat(zf.extract(cond_n, td))
                spd_df = cd['speed']
                if float(spd_df['Speed'].max()) < 1.4:
                    continue
                ik = CR.load_table(zf.extract(ik_n, td))
                t200, Q = CR.ik_to_Q(m, info, ik, fs_out=FS_IN)
                t_c = spd_df['Header'].values.astype(float)
                t_c = t_c - t_c[0]
                sp200 = np.interp(t200, t_c, spd_df['Speed'].values.astype(float))
                fast50 = (sp200[::4] >= 1.4).astype(np.int16)
                rep = CR.replay(m, Q, FS_IN, sensors=('acc_imu',))
                n50 = min(len(Q) // 4, len(fast50))
                acc_sim50 = resample_poly(rep['acc_imu'], 1, 4, axis=0)[:n50].astype(np.float32)
                Xs, ys = chip_windows(acc_sim50, fast50[:n50], lib, min_share=0.90)
                ks = (ys == 1)
                if ks.any():
                    tm_X.append(Xs[ks])
                    tm_src.append(np.full(int(ks.sum()), 'sim', dtype=object))
                    tm_ds.append(np.full(int(ks.sum()), 'Camargo tm>=1.4 sim', dtype=object))
                    tm_grp.append(np.full(int(ks.sum()), person, dtype=object))
                if imu_n in names:
                    df_i = CR.load_table(zf.extract(imu_n, td))
                    if 'shank_Accel_X' in df_i.columns and len(df_i) >= W * 4:
                        f_s, w_s = _extract_shank_imu(df_i)
                        acc_v200, _ = V.virtual_implant(f_s, w_s, FS_IN, distance=0.22, anterior=-0.02,
                                                        side='R', T=T_person)
                        n50r = min(len(acc_v200) // 4, n50)
                        acc_real50 = resample_poly(acc_v200, 1, 4, axis=0)[:n50r].astype(np.float32)
                        Xr, yr = chip_windows(acc_real50, fast50[:n50r], lib, min_share=0.90)
                        kr = (yr == 1)
                        if kr.any():
                            tm_X.append(Xr[kr])
                            tm_src.append(np.full(int(kr.sum()), 'real', dtype=object))
                            tm_ds.append(np.full(int(kr.sum()), 'Camargo tm>=1.4 real', dtype=object))
                            tm_grp.append(np.full(int(kr.sum()), person, dtype=object))
            except Exception as exc:
                log(f'  skip tm {person}/{os.path.basename(ik_n)}: {exc}')

    out = dict(
        X=np.vstack(rows_X) if rows_X else np.empty((0, 20), np.float32),
        y=np.concatenate(rows_y) if rows_y else np.empty((0,), np.int16),
        src=np.concatenate(rows_src) if rows_src else np.empty((0,), dtype=object),
        ds=np.concatenate(rows_ds) if rows_ds else np.empty((0,), dtype=object),
        grp=np.concatenate(rows_grp) if rows_grp else np.empty((0,), dtype=object),
        slope=np.concatenate(rows_slope) if rows_slope else np.empty((0,), np.float32),
        tm_X=np.vstack(tm_X) if tm_X else np.empty((0, 20), np.float32),
        tm_src=np.concatenate(tm_src) if tm_src else np.empty((0,), dtype=object),
        tm_ds=np.concatenate(tm_ds) if tm_ds else np.empty((0,), dtype=object),
        tm_grp=np.concatenate(tm_grp) if tm_grp else np.empty((0,), dtype=object),
    )
    np.savez_compressed(out_p, **out)
    log(f'  {person}: {len(out["y"])} ramp win (real={int((out["src"]=="real").sum())}, '
        f'sim={int((out["src"]=="sim").sum())}), {len(out["tm_X"])} fast tm win ({time.time() - t0:.1f} s)')
    return out


def load_all_ramps(A, lib, out_dir, log, max_people=None):
    """Combine Camargo ramps (real+sim) + Luo SlpU/SlpD (from windows_W4s) + Camargo tm>=1.4."""
    cache_dir = os.path.join(out_dir, 'camargo_cache')
    os.makedirs(cache_dir, exist_ok=True)
    people = sorted(CR.HEIGHT.keys())
    if max_people is not None:
        people = people[:max_people]

    Xs, ys, srcs, dss, grps, slopes = [], [], [], [], [], []
    tm_Xs, tm_srcs, tm_dss, tm_grps = [], [], [], []
    for p in people:
        d = extract_camargo_person(p, lib, cache_dir, log)
        if len(d['y']):
            Xs.append(d['X']); ys.append(d['y']); srcs.append(d['src'])
            dss.append(d['ds']); grps.append(d['grp']); slopes.append(d['slope'])
        if len(d['tm_X']):
            tm_Xs.append(d['tm_X']); tm_srcs.append(d['tm_src'])
            tm_dss.append(d['tm_ds']); tm_grps.append(d['tm_grp'])

    # Add Luo SlpU / SlpD directly from windows_W4s.npz (angle unreported in Luo 2020 -> slope = -1.0)
    ds_a = A['ds'].astype(str)
    lab_a = A['lab'].astype(str)
    m_luo = (ds_a == 'Luo') & np.isin(lab_a, ('slope_up', 'slope_down'))
    if m_luo.any():
        Xs.append(A['X'][m_luo].astype(np.float32))
        ys.append(np.where(lab_a[m_luo] == 'slope_up', 1, 2).astype(np.int16))
        n_l = int(m_luo.sum())
        srcs.append(np.full(n_l, 'real', dtype=object))
        dss.append(np.full(n_l, 'Luo slope', dtype=object))
        grps.append(A['grp'][m_luo].astype(object))
        slopes.append(np.full(n_l, -1.0, dtype=np.float32))

    ramps = dict(
        X=np.vstack(Xs),
        y=np.concatenate(ys),
        src=np.concatenate(srcs),
        ds=np.concatenate(dss),
        grp=np.concatenate(grps),
        slope=np.concatenate(slopes),
    )
    tm_fast = dict(
        X=np.vstack(tm_Xs) if tm_Xs else np.empty((0, 20), np.float32),
        src=np.concatenate(tm_srcs) if tm_srcs else np.empty((0,), dtype=object),
        ds=np.concatenate(tm_dss) if tm_dss else np.empty((0,), dtype=object),
        grp=np.concatenate(tm_grps) if tm_grps else np.empty((0,), dtype=object),
    )
    return ramps, tm_fast


def ramp_train_labels(ramps, variant):
    """Return (use_mask, y_train) for ramp windows under each variant."""
    n = len(ramps['y'])
    if variant == 'V4half':
        return np.zeros(n, bool), ramps['y'].copy()
    if variant == 'R-walk':
        return np.ones(n, bool), np.zeros(n, np.int16)
    if variant == 'M-all':
        return np.ones(n, bool), ramps['y'].copy()
    if variant in ('M-steep8', 'M-steep10'):
        cut = 8.0 if variant == 'M-steep8' else 10.0
        known = ramps['slope'] > 0.0  # Camargo ramps have exact surveyed angles; Luo angle unreported
        yt = np.where(ramps['slope'] >= cut, ramps['y'], 0).astype(np.int16)
        return known, yt
    raise ValueError(variant)


def fit_and_eval_cv(A, y_base, fold_base, ramps, fold_ramp, tm_fast, fold_tm, variant, seed, pred_dir, log):
    path = os.path.join(pred_dir, f'pred_{variant}_seed{seed}.npz')
    if os.path.exists(path):
        log(f'  {variant} seed {seed}: loading cached {os.path.basename(path)}')
        Z = np.load(path)
        return {k: Z[k] for k in Z.files}

    n_b, n_r, n_t = len(y_base), len(ramps['y']), len(tm_fast['X'])
    pred_b = np.full(n_b, -2, np.int8)
    proba_b = np.zeros((n_b, 8), np.float16)
    pred_r = np.full(n_r, -2, np.int8)
    proba_r = np.zeros((n_r, 8), np.float16)
    pred_t = np.full(n_t, -2, np.int8)
    proba_t = np.zeros((n_t, 8), np.float16)
    nodes = -1
    use_r, y_r_tr = ramp_train_labels(ramps, variant)

    t0 = time.time()
    for k in range(C.K):
        Xb, yb, wb = C.training_set_v4(A, fold_base != k, 'V4half', y_base)
        Xs, ys, ws = [Xb], [yb], [wb]
        mr = use_r & (fold_ramp != k)
        if mr.any():
            # Match V4half weighting: real = 1.0, sim = 0.5
            w_r = np.where(ramps['src'][mr].astype(str) == 'real', 1.0, 0.5).astype(np.float64)
            Xs.append(ramps['X'][mr].astype(np.float32))
            ys.append(y_r_tr[mr].astype(int))
            ws.append(w_r)
        clf = S3.make_model('forest 20x d10')
        clf.set_params(random_state=seed)
        clf.fit(np.vstack(Xs), np.concatenate(ys).astype(int), sample_weight=np.concatenate(ws))
        if k == 0:
            nodes = int(S3.T.n_nodes(clf))

        tb = (fold_base == k)
        pb = clf.predict_proba(A['X'][tb])
        proba_b[tb] = pb.astype(np.float16)
        pred_b[tb] = np.argmax(pb, axis=1).astype(np.int8)

        tr = (fold_ramp == k)
        if tr.any():
            pr = clf.predict_proba(ramps['X'][tr])
            proba_r[tr] = pr.astype(np.float16)
            pred_r[tr] = np.argmax(pr, axis=1).astype(np.int8)

        tt = (fold_tm == k)
        if tt.any():
            pt = clf.predict_proba(tm_fast['X'][tt])
            proba_t[tt] = pt.astype(np.float16)
            pred_t[tt] = np.argmax(pt, axis=1).astype(np.int8)

    out = dict(pred_b=pred_b, proba_b=proba_b, pred_r=pred_r, proba_r=proba_r,
               pred_t=pred_t, proba_t=proba_t, nodes=np.int64(nodes))
    np.savez_compressed(path, **out)
    log(f'  {variant} seed {seed}: done in {time.time() - t0:.1f} s (nodes={nodes})')
    return out


def eval_sim_events_from_streams(A, y_base, pb):
    """Stream-level R1 transition event recall (STS=5, S2S=6 on v1.6 synthetic) and false events/h (Camargo sim).
    Matches transition_events.py R1 (run of >=1 or >=2 windows) directly from A['stream'] without re-extracting CSVs."""
    ds = A['ds'].astype(str)
    st = A['stream']
    b = np.r_[0, np.flatnonzero(np.diff(st) != 0) + 1]
    e = np.r_[b[1:], len(st)]

    def _runs(arr, cls):
        m = (arr == cls).astype(np.int8)
        d = np.diff(np.r_[0, m, 0])
        return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))

    n_true, n_match = 0, 0
    cam_false, cam_hours = 0, 0.0
    for a_, b_ in zip(b, e):
        dname = ds[a_]
        if dname == 'v1.6 synthetic':
            yt, yp = y_base[a_:b_], pb[a_:b_]
            for cls in (5, 6):
                tr_runs = _runs(yt, cls)
                pr_runs = [(s, en) for s, en in _runs(yp, cls) if (en - s) >= 2]
                used = set()
                for ts, te in tr_runs:
                    n_true += 1
                    tc = 0.5 * (ts + te)
                    for j, (ps, pe) in enumerate(pr_runs):
                        if j not in used and abs(0.5 * (ps + pe) - tc) <= 4.0:
                            n_match += 1
                            used.add(j)
                            break
        elif dname == 'Camargo simulated':
            yp = pb[a_:b_]
            cam_hours += (b_ - a_) / 3600.0
            for cls in (5, 6):
                cam_false += sum(1 for s, en in _runs(yp, cls) if (en - s) >= 2)
    rec = 100.0 * n_match / n_true if n_true else np.nan
    fph = cam_false / cam_hours if cam_hours > 0 else 0.0
    return rec, fph


def compute_metrics(A, y_base, ramps, tm_fast, res, variant, seed, theta):
    pb = rule_theta(res['pred_b'], res['proba_b'], theta)
    pr = rule_theta(res['pred_r'], res['proba_r'], theta)
    pt = rule_theta(res['pred_t'], res['proba_t'], theta) if len(res['pred_t']) else np.empty((0,), np.int8)

    ds = A['ds'].astype(str)
    src = A['src'].astype(str)
    rec_c = A['rec'].astype(str)
    surf = A['surface'].astype(str)
    spd = A['speed_abs'].astype(str)

    row = dict(variant=variant, seed=seed, theta=theta, nodes=int(res['nodes']))

    # 1. Stairs-only recall (Luo StrU/StrD, PAMAP2, Camargo sim)
    for dname, key in (('Luo', 'luo_st'), ('PAMAP2', 'pamap_st'), ('Camargo simulated', 'cam_st')):
        for c, tag in ((1, 'up'), (2, 'dn')):
            m = (ds == dname) & (y_base == c)
            row[f'{key}_{tag}_rec'] = 100.0 * float((pb[m] == c).mean()) if m.any() else np.nan
            mp = (ds == dname) & (pb == c)
            row[f'{key}_{tag}_prec'] = 100.0 * float((y_base[mp] == c).mean()) if mp.any() else np.nan

    # 2. Ramp recall per slope band (Camargo real, Camargo sim, Luo SlpU/SlpD)
    rds = ramps['ds'].astype(str)
    ry = ramps['y'].astype(int)
    rsl = ramps['slope'].astype(float)
    for ang in (5.2, 7.8, 9.2, 11.0, 12.4, 18.0):
        for rsrc, tag in (('Camargo ramp real', 'cr'), ('Camargo ramp sim', 'cs')):
            m = (rds == rsrc) & (np.abs(rsl - ang) < 0.2)
            row[f'{tag}_{ang:.1f}_rec'] = 100.0 * float((pr[m] == ry[m]).mean()) if m.any() else np.nan
            row[f'{tag}_{ang:.1f}_walk'] = 100.0 * float((pr[m] == 0).mean()) if m.any() else np.nan
    for c, tag in ((1, 'up'), (2, 'dn')):
        m = (rds == 'Luo slope') & (ry == c)
        row[f'luo_slp_{tag}_rec'] = 100.0 * float((pr[m] == c).mean()) if m.any() else np.nan
        row[f'luo_slp_{tag}_walk'] = 100.0 * float((pr[m] == 0).mean()) if m.any() else np.nan

    # 3. Combined real up/down recall & precision (stairs + ramps according to variant definition, plus M-all view)
    m_real_st = (src == 'real') & np.isin(y_base, (1, 2))
    m_real_rp = (ramps['src'].astype(str) == 'real')
    # Under merged target (all real stairs + all real ramps)
    y_ud_all = np.concatenate([y_base[m_real_st], ry[m_real_rp]])
    p_ud_all = np.concatenate([pb[m_real_st], pr[m_real_rp]])
    # Precision denominator includes all real base windows + all real ramp windows
    m_rb = (src == 'real') & (y_base >= 0)
    y_full = np.concatenate([y_base[m_rb], ry[m_real_rp]])
    p_full = np.concatenate([pb[m_rb], pr[m_real_rp]])
    for c, tag in ((1, 'up'), (2, 'dn')):
        row[f'merged_all_{tag}_rec'] = 100.0 * float((p_ud_all[y_ud_all == c] == c).mean())
        mp = (p_full == c)
        row[f'merged_all_{tag}_prec'] = 100.0 * float((y_full[mp] == c).mean()) if mp.any() else np.nan

    # 4. Walking called up/down (%) — overall and fast walking
    ud_b = np.isin(pb, (1, 2))
    m_w_real = (src == 'real') & (y_base == 0)
    row['real_walk_to_ud'] = 100.0 * float(ud_b[m_w_real].mean())
    row['lencioni_fast_to_ud'] = 100.0 * float(ud_b[(ds == 'Lencioni') & (spd == 'fast') & (y_base == 0)].mean())
    row['luo_FE_to_ud'] = 100.0 * float(ud_b[(ds == 'Luo') & (surf == 'FE') & (y_base == 0)].mean())
    row['wg_hurried_to_ud'] = 100.0 * float(ud_b[(ds == 'WearGait-PD') & (rec_c == 'HurriedPace') & (y_base == 0)].mean())
    for tds, key in (('Camargo tm>=1.4 real', 'cam_tm14_real_to_ud'), ('Camargo tm>=1.4 sim', 'cam_tm14_sim_to_ud')):
        mt = (tm_fast['ds'].astype(str) == tds) if len(pt) else np.array([], bool)
        row[key] = 100.0 * float(np.isin(pt[mt], (1, 2)).mean()) if mt.any() else np.nan

    # 5. No-regression: walking recall per real dataset, still, lying, transition events
    for dname in ('WearGait-PD', 'CeTI', 'Luo', 'Lencioni', 'KneE-PAD', 'Marpino', 'PAMAP2', 'MHEALTH'):
        m = (src == 'real') & (ds == dname) & (y_base == 0)
        row[f'walk_{dname}'] = 100.0 * float((pb[m] == 0).mean()) if m.any() else np.nan
    m_st = (src == 'real') & (y_base == 3)
    row['real_still_rec'] = 100.0 * float((pb[m_st] == 3).mean())
    row['real_still_to_walk'] = 100.0 * float((pb[m_st] == 0).mean())
    m_ly = (src == 'real') & (y_base == 4)
    row['real_lying_rec'] = 100.0 * float((pb[m_ly] == 4).mean()) if m_ly.any() else np.nan

    ev_rec, cam_fph = eval_sim_events_from_streams(A, y_base, pb)
    row['sim_trans_rec'] = ev_rec
    row['cam_false_per_h'] = cam_fph

    # 6. 4x4 confusion matrix on real base + real ramps (0=walk, 1=up, 2=down, 3=still)
    cm = np.zeros((4, 4), np.int64)
    for ti, c_true in enumerate((0, 1, 2, 3)):
        mt = (y_full == c_true)
        for pi, c_pred in enumerate((0, 1, 2, 3)):
            cm[ti, pi] = int((p_full[mt] == c_pred).sum())
    return row, cm


def main():
    ap = argparse.ArgumentParser(description='KNEIL S1: stairs + ramps up/down CV experiment')
    ap.add_argument('--max-people', type=int, default=None, help='limit Camargo people for quick test')
    ap.add_argument('--variants', nargs='+', default=list(VARIANTS), choices=list(VARIANTS))
    ap.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    ap.add_argument('--out-name', default='cv_updown')
    a = ap.parse_args()

    print(VERSION, flush=True)
    out_dir = config.out_dir('stepG', a.out_name)
    pred_dir = os.path.join(out_dir, 'preds')
    os.makedirs(pred_dir, exist_ok=True)
    log_path = os.path.join(out_dir, 'cv_updown_log.txt')
    log = lambda m: log_msg(m, log_path)

    log(f'{VERSION} | {C.VERSION} | {config.VERSION} | out={out_dir}')
    log(f'variants={a.variants} | seeds={a.seeds} | max_people={a.max_people}')

    lib = S3.init_tinyml()
    # Load base W=4s windows & exact person folds
    Z4 = np.load(os.path.join(BASE_V4, 'stepD', 'windows_v11', 'windows_W4s.npz'), allow_pickle=True)
    A = {k: Z4[k] for k in Z4.files if k in C.COLS}
    y_base = C.y_for(A, 8)
    Z2 = np.load(os.path.join(BASE_V4, 'stepD', 'windows_v11', 'windows_W2s.npz'), allow_pickle=True)
    A2 = {k: Z2[k] for k in Z2.files if k in C.COLS}
    gf = S3.assign_folds(A2)[1]
    fold_base = C.folds_for(A, gf, log=lambda *x: None)

    ramps, tm_fast = load_all_ramps(A, lib, out_dir, log, max_people=a.max_people)
    fold_ramp = np.array([gf.get(str(g), 0) for g in ramps['grp']], int)
    fold_tm = np.array([gf.get(str(g), 0) for g in tm_fast['grp']], int) if len(tm_fast['X']) else np.empty((0,), int)

    # Save exact dataset & slope-band counts (people and windows)
    import json
    counts = {'base_real': {}, 'ramps': {}, 'ramps_by_slope': {}, 'tm_fast': {}}
    ds_b = A['ds'].astype(str)
    src_b = A['src'].astype(str)
    grp_b = A['grp'].astype(str)
    for dname in sorted(set(ds_b)):
        m = (ds_b == dname) & (y_base >= 0)
        counts['base_real'][dname] = dict(
            windows=int(m.sum()),
            people=int(len(set(grp_b[m]))),
            walking=int((y_base[m] == 0).sum()),
            stairs_up=int((y_base[m] == 1).sum()),
            stairs_down=int((y_base[m] == 2).sum()),
            still=int((y_base[m] == 3).sum()),
        )
    for dname in sorted(set(ramps['ds'].astype(str))):
        m = (ramps['ds'].astype(str) == dname)
        n_p = len(set(ramps['grp'].astype(str)[m]))
        counts['ramps'][dname] = dict(
            windows=int(m.sum()),
            up=int((ramps['y'][m] == 1).sum()),
            down=int((ramps['y'][m] == 2).sum()),
            people=int(n_p),
        )
        log(f'  {dname:20s}: {int(m.sum()):6d} windows ({int((ramps["y"][m]==1).sum())} up, '
            f'{int((ramps["y"][m]==2).sum())} down), {n_p} people')
    for ang in (5.2, 7.8, 9.2, 11.0, 12.4, 18.0):
        for rsrc in ('Camargo ramp real', 'Camargo ramp sim'):
            m = (ramps['ds'].astype(str) == rsrc) & (np.abs(ramps['slope'].astype(float) - ang) < 0.2)
            counts['ramps_by_slope'][f'{rsrc} {ang:.1f}deg'] = dict(
                windows=int(m.sum()),
                up=int((ramps['y'][m] == 1).sum()),
                down=int((ramps['y'][m] == 2).sum()),
                people=int(len(set(ramps['grp'].astype(str)[m]))),
            )
    for dname in sorted(set(tm_fast['ds'].astype(str))):
        m = (tm_fast['ds'].astype(str) == dname)
        n_p = len(set(tm_fast['grp'].astype(str)[m]))
        counts['tm_fast'][dname] = dict(windows=int(m.sum()), people=int(n_p))
        log(f'  {dname:20s}: {int(m.sum()):6d} windows, {n_p} people')
    with open(os.path.join(out_dir, 'dataset_counts.json'), 'w', encoding='utf-8') as f:
        json.dump(counts, f, indent=2)

    rows = []
    cms = {}
    for variant in a.variants:
        thetas = THETAS if variant.startswith('M-') else (0.60,)
        for seed in a.seeds:
            res = fit_and_eval_cv(A, y_base, fold_base, ramps, fold_ramp, tm_fast, fold_tm,
                                  variant, seed, pred_dir, log)
            for th in thetas:
                row, cm = compute_metrics(A, y_base, ramps, tm_fast, res, variant, seed, th)
                rows.append(row)
                if abs(th - 0.60) < 1e-6:
                    cms.setdefault(variant, []).append(cm)

    df = pd.DataFrame(rows)
    csv_path = os.path.join(out_dir, 'cv_updown_results.csv')
    df.to_csv(csv_path, index=False)

    # Save mean confusion matrices (at theta = 0.60)
    cm_out = {v: np.mean(v_list, axis=0).round(1).tolist() for v, v_list in cms.items()}
    import json
    with open(os.path.join(out_dir, 'confusion_matrices_t06.json'), 'w', encoding='utf-8') as f:
        json.dump(cm_out, f, indent=2)

    # Print concise summary at theta = 0.60
    agg = df.groupby(['variant', 'theta']).agg(['mean', 'std'])
    log('--- Summary (mean over seeds) ---')
    key_cols = ['merged_all_up_rec', 'merged_all_up_prec', 'merged_all_dn_rec', 'merged_all_dn_prec',
                'luo_st_up_rec', 'luo_st_dn_rec', 'luo_slp_up_rec', 'luo_slp_dn_rec',
                'lencioni_fast_to_ud', 'luo_FE_to_ud', 'wg_hurried_to_ud', 'cam_tm14_real_to_ud',
                'real_still_to_walk', 'sim_trans_rec', 'nodes']
    for (v, th), sub in df.groupby(['variant', 'theta']):
        parts = [f'{c}={sub[c].mean():.1f}' for c in key_cols if c in sub.columns and np.isfinite(sub[c].mean())]
        log(f'  {v:9s} th={th:.1f} | ' + '  '.join(parts))

    # Write one-screen owner_summary.md (numbers only, no recommendation)
    def fmt_ms(sub, col):
        if col not in sub.columns or not np.isfinite(sub[col]).any():
            return 'n/a'
        m = sub[col].mean()
        s = sub[col].std(ddof=1) if len(sub) > 1 else 0.0
        return f'{m:.1f} ({s:.1f})'

    v_order = [v for v in VARIANTS if v in set(df['variant'])]
    sub06 = {v: df[(df['variant'] == v) & (np.abs(df['theta'] - 0.60) < 1e-6)] for v in v_order}
    owner_lines = [
        '# S1 Owner Summary: Stairs + Ramps -> Going Up / Going Down (5-fold CV, 3 seeds, theta=0.60)',
        '',
        'Mean (sd) over 3 seeds. Numbers only.',
        '',
        '| Metric | ' + ' | '.join(v_order) + ' |',
        '|---|' + '---:|' * len(v_order),
    ]
    metric_specs = [
        ('Merged real up recall (stairs+ramps), %', 'merged_all_up_rec'),
        ('Merged real up precision, %', 'merged_all_up_prec'),
        ('Merged real down recall (stairs+ramps), %', 'merged_all_dn_rec'),
        ('Merged real down precision, %', 'merged_all_dn_prec'),
        ('Luo stairs up / down recall, %', None),
        ('PAMAP2 stairs up / down recall, %', None),
        ('Luo SlpU / SlpD called up/down, %', None),
        ('Camargo real ramp 5.2 / 7.8 / 9.2 deg recall, %', None),
        ('Camargo real ramp 11.0 / 12.4 / 18.0 deg recall, %', None),
        ('Real walking called up/down (all), %', 'real_walk_to_ud'),
        ('Lencioni fast walking called up/down, %', 'lencioni_fast_to_ud'),
        ('Luo FE walking called up/down, %', 'luo_FE_to_ud'),
        ('WearGait HurriedPace called up/down, %', 'wg_hurried_to_ud'),
        ('Camargo tm >= 1.4 m/s real called up/down, %', 'cam_tm14_real_to_ud'),
        ('Real still called walking, %', 'real_still_to_walk'),
        ('Real lying recall, %', 'real_lying_rec'),
        ('Sim transition event recall (STS+S2S), %', 'sim_trans_rec'),
        ('Camargo false events / h', 'cam_false_per_h'),
        ('Forest nodes (fold 0)', 'nodes'),
    ]
    for label, col in metric_specs:
        vals = []
        for v in v_order:
            s = sub06[v]
            if col is not None:
                vals.append(fmt_ms(s, col))
            elif label.startswith('Luo stairs'):
                vals.append(f'{s["luo_st_up_rec"].mean():.1f} / {s["luo_st_dn_rec"].mean():.1f}')
            elif label.startswith('PAMAP2 stairs'):
                vals.append(f'{s["pamap_st_up_rec"].mean():.1f} / {s["pamap_st_dn_rec"].mean():.1f}')
            elif label.startswith('Luo SlpU'):
                vals.append(f'{s["luo_slp_up_rec"].mean():.1f} / {s["luo_slp_dn_rec"].mean():.1f}')
            elif '5.2 / 7.8 / 9.2' in label:
                vals.append(f'{s["cr_5.2_rec"].mean():.1f} / {s["cr_7.8_rec"].mean():.1f} / {s["cr_9.2_rec"].mean():.1f}')
            elif '11.0 / 12.4 / 18.0' in label:
                vals.append(f'{s["cr_11.0_rec"].mean():.1f} / {s["cr_12.4_rec"].mean():.1f} / {s["cr_18.0_rec"].mean():.1f}')
        owner_lines.append(f'| {label} | ' + ' | '.join(vals) + ' |')
    with open(os.path.join(out_dir, 'owner_summary.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(owner_lines) + '\n')

    log(f'Saved results to {csv_path} and owner_summary.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
