"""
KNEIL L1: Feasibility of knee flexion and spacer-loosening monitoring from the
50 Hz 3-axis tibial-insert accelerometer (no gyroscope, no thigh sensor).
   diag_flexion 1.0, 24 Nov 2026

Analysis only: no chip, library or protocol change.
Outputs under cache/l1/ (plots, JSON, log) and KNEIL_results/v4/stepH/ (summary tables).

Usage:
    python pipeline/diag_flexion.py
    python pipeline/diag_flexion.py --max-people 3   # quick test
"""
import argparse
import json
import os
import sys
import tempfile
import time
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mujoco
import numpy as np
import pandas as pd
from scipy.signal import butter, resample_poly, sosfilt, sosfilt_zi

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE_DIR = os.path.join(REPO_ROOT, 'pipeline')
VIEWER_DIR = os.path.join(REPO_ROOT, 'viewer')
for d in (PIPE_DIR, VIEWER_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import config
import camargo_replay as CR
import cv_v4 as C
import kneil_v1 as K
import vimp as V

VERSION = 'diag_flexion 1.0'
FS_SIM = 200.0
FS_CHIP = 50.0
CACHE_L1 = os.path.join(config.CACHE, 'l1')
BASE_V4 = os.path.join(config.RESULTS, 'v4')
CAMARGO_DATA = os.path.join(config.DATA_ROOT, 'Camargo et. al. 2021', 'Data')

FEAT_NAMES = ['mean_x', 'mean_y', 'mean_z', 'std_x', 'std_y', 'std_z', 'std_m', 'mean_m',
              'ptp_m', 'max_m', 'jerk_m', 'tilt_sag_deg', 'tilt_cor_deg', 'ac_m_05s',
              'ac_m_10s', 'zcr_z_hz', 'trend_x', 'trend_z', 'corr_xz', 'hf_ratio']


def log_msg(msg, path):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def causal_lp(x, fc, fs=FS_CHIP, order=2):
    sos = butter(order, fc, fs=fs, output='sos')
    zi_u = sosfilt_zi(sos)
    out = np.empty_like(x, dtype=np.float64)
    for k in range(x.shape[1]):
        out[:, k], _ = sosfilt(sos, x[:, k], zi=zi_u * x[0, k])
    return out


# =============================================================================
# Part A.1: Seated knee angle simulation in MuJoCo (kneil_v1.py)
# =============================================================================
def simulate_seated_sweep(osim, speed_deg_s=30.0, thigh_slope_deg=0.0, mount=(0.0, 0.0, 0.0)):
    """Simulate seated knee extension (90 -> 0 deg) and flexion (90 -> 120 deg) in MuJoCo.
    Returns t50, phi_true_deg (knee flexion 0..120), acc50 (g, shape Nx3, with 0.010 g MEMS noise)."""
    m, info = K.build_model(osim, imu_side='r', imu_pos=(0.005, -0.025, 0.0), mount=mount)
    idx = K.qidx(m)

    # Piecewise minimum-jerk trajectory: hold 90 (1.5s) -> 0 (ext) -> hold 0 (1.5s) -> 90 -> 120 (flex) -> hold 120 (1.5s)
    def ramp(a0, a1, spd):
        dur = max(0.3, abs(a1 - a0) / float(spd))
        n = max(4, int(round(dur * FS_SIM)))
        u = np.linspace(0.0, 1.0, n)
        s = u * u * u * (u * (u * 6.0 - 15.0) + 10.0)
        return a0 + (a1 - a0) * s

    hold = lambda val, sec: np.full(int(round(sec * FS_SIM)), val)
    phi_deg = np.concatenate([
        hold(90.0, 1.5),
        ramp(90.0, 0.0, speed_deg_s),
        hold(0.0, 1.5),
        ramp(0.0, 90.0, speed_deg_s),
        hold(90.0, 0.8),
        ramp(90.0, 120.0, speed_deg_s),
        hold(120.0, 1.5),
    ])
    n = len(phi_deg)
    Q = np.zeros((n, m.nq), dtype=np.float64)
    Q[:, idx['pelvis_ty']] = 0.85
    # Seated: thigh horizontal + upward thigh slope (positive hip_flexion_r lifts thigh)
    Q[:, idx['hip_flexion_r']] = np.radians(90.0 + thigh_slope_deg)
    Q[:, idx['hip_flexion_l']] = np.radians(90.0 + thigh_slope_deg)
    # OpenSim Gait2354: knee_angle_r is negative in flexion
    Q[:, idx['knee_angle_r']] = -np.radians(phi_deg)
    Q[:, idx['knee_angle_l']] = -np.radians(90.0)
    K.set_knee_translations(Q, idx, info)

    rep = CR.replay(m, Q, FS_SIM, sensors=('acc_imu',))
    n50 = n // 4
    acc50 = resample_poly(rep['acc_imu'], 1, 4, axis=0)[:n50]
    phi50 = phi_deg[::4][:n50]
    t50 = np.arange(n50) / FS_CHIP
    return t50, phi50, acc50


def eval_seated_calibration(phi_true, acc50, fc=2.0, gate_g=0.05):
    """Evaluate no-cal, 1-point (90 deg foot-flat), and 2-point (90 + 0 deg) seated angle errors."""
    a_lp = causal_lp(acc50, fc=fc, fs=FS_CHIP, order=2)
    # In device frame (x anterior, z superior):
    #   at knee=90 (tibia vertical): a_x ~ 0, a_z ~ +1 -> atan2(a_x, a_z) ~ 0 deg
    #   at knee=0 (leg straight horizontal forward): tibia superior (+z) points forward -> gravity (+up) projects onto -x?
    # Let's compute theta = atan2(a_x, a_z) and auto-verify sign at 0 deg vs 90 deg from the nominal static curve!
    theta = np.degrees(np.arctan2(a_lp[:, 0], a_lp[:, 2]))
    mag_err = np.abs(np.linalg.norm(a_lp, axis=1) - 1.0)
    ok = mag_err <= gate_g

    # Calibration holds: first hold is 90 deg (samples 25..65), second hold is 0 deg (find phi_true == 0)
    i90 = np.where(np.abs(phi_true - 90.0) < 0.05)[0]
    i90 = i90[i90 < 75]
    th90 = float(np.median(theta[i90[15:]])) if len(i90) > 20 else float(theta[0])
    i0 = np.where(np.abs(phi_true - 0.0) < 0.05)[0]
    th0 = float(np.median(theta[i0[20:-5]])) if len(i0) > 25 else th90 + 90.0

    # Sign: when extending 90 -> 0 deg, does theta increase (+90) or decrease (-90)?
    sgn = 1.0 if (th0 - th90) > 0 else -1.0

    # No calibration: assume nominal th90 = 0
    phi_nocal = 90.0 - sgn * theta
    # 1-point calibration (foot flat ~ 90 deg)
    phi_1pt = 90.0 - sgn * (theta - th90)
    # 2-point calibration (foot flat 90 deg + leg straight 0 deg)
    span = (th0 - th90) if abs(th0 - th90) > 10.0 else (sgn * 90.0)
    phi_2pt = 90.0 - 90.0 * (theta - th90) / span

    def stats(pred):
        e = np.abs(pred[ok] - phi_true[ok]) if ok.any() else np.abs(pred - phi_true)
        return dict(rmse=float(np.sqrt(np.mean(e * e))), p95=float(np.percentile(e, 95)),
                    max=float(np.max(e)), keep_pct=100.0 * float(ok.mean()))

    return dict(nocal=stats(phi_nocal), cal1=stats(phi_1pt), cal2=stats(phi_2pt),
                th90=th90, th0=th0, sgn=sgn)


def run_part_a1(osim, log):
    log('--- Part A.1: Seated knee angle simulation in MuJoCo ---')
    # Verify static device gravity vector at knee=90, 0, 120 deg
    t0, phi0, acc0 = simulate_seated_sweep(osim, speed_deg_s=20.0, thigh_slope_deg=0.0, mount=(0, 0, 0))
    for ang in (90.0, 0.0, 120.0):
        ii = np.where(np.abs(phi0 - ang) < 0.05)[0]
        v = acc0[ii[len(ii) // 2]]
        th = float(np.degrees(np.arctan2(v[0], v[2])))
        log(f'  Static check knee={ang:5.1f} deg: acc=({v[0]:+.3f}, {v[1]:+.3f}, {v[2]:+.3f}) g | atan2(ax,az)={th:+.2f} deg')

    # 1. Speed x filter cut-off x |a| gate sweep (nominal mount, thigh slope 0)
    grid_rows = []
    for spd in (10.0, 20.0, 30.0, 45.0, 60.0):
        _, phi, acc = simulate_seated_sweep(osim, speed_deg_s=spd, thigh_slope_deg=0.0, mount=(0, 0, 0))
        rng = np.random.default_rng(100 + int(spd))
        acc_n = acc + rng.normal(0.0, 0.010, acc.shape)
        for fc in (0.5, 1.0, 2.0, 4.0, 6.0):
            for gate in (0.02, 0.05, 0.10, 0.20, 99.0):
                r = eval_seated_calibration(phi, acc_n, fc=fc, gate_g=gate)
                grid_rows.append(dict(
                    speed=spd, fc=fc, gate=gate,
                    rmse_1pt=round(r['cal1']['rmse'], 2), p95_1pt=round(r['cal1']['p95'], 2),
                    max_1pt=round(r['cal1']['max'], 2), keep_pct=round(r['cal1']['keep_pct'], 1),
                ))

    # 2. Thigh slope sweep (0, 5, 10, 15 deg) at 30 deg/s, fc=2.0 Hz, gate=0.05 g
    slope_rows = []
    for sl in (0.0, 5.0, 10.0, 15.0):
        _, phi, acc = simulate_seated_sweep(osim, speed_deg_s=30.0, thigh_slope_deg=sl, mount=(0, 0, 0))
        rng = np.random.default_rng(200 + int(sl))
        acc_n = acc + rng.normal(0.0, 0.010, acc.shape)
        r = eval_seated_calibration(phi, acc_n, fc=2.0, gate_g=0.05)
        slope_rows.append(dict(
            thigh_slope=sl,
            nocal_rmse=round(r['nocal']['rmse'], 2), nocal_max=round(r['nocal']['max'], 2),
            cal1_rmse=round(r['cal1']['rmse'], 2), cal1_max=round(r['cal1']['max'], 2),
            cal2_rmse=round(r['cal2']['rmse'], 2), cal2_max=round(r['cal2']['max'], 2),
        ))
        log(f'  Thigh slope {sl:4.1f} deg: nocal RMSE={r["nocal"]["rmse"]:5.2f}, '
            f'1pt RMSE={r["cal1"]["rmse"]:5.2f} (max {r["cal1"]["max"]:5.2f}), '
            f'2pt RMSE={r["cal2"]["rmse"]:5.2f} (max {r["cal2"]["max"]:5.2f})')

    # 3. Mount error Monte Carlo (+-10 deg on yaw, pitch, roll; 60 random mounts + thigh slope U(0,15) + speed U(10,60))
    rng = np.random.default_rng(303)
    mc_rows = []
    for k in range(60):
        my, mp, mr = rng.uniform(-10.0, 10.0, 3)
        sl = float(rng.uniform(0.0, 15.0))
        spd = float(rng.choice([10.0, 20.0, 30.0, 45.0, 60.0]))
        _, phi, acc = simulate_seated_sweep(osim, speed_deg_s=spd, thigh_slope_deg=sl, mount=(my, mp, mr))
        acc_n = acc + rng.normal(0.0, 0.010, acc.shape)
        r = eval_seated_calibration(phi, acc_n, fc=2.0, gate_g=0.05)
        mc_rows.append(dict(
            yaw=my, pitch=mp, roll=mr, slope=sl, speed=spd,
            nocal_rmse=r['nocal']['rmse'], cal1_rmse=r['cal1']['rmse'], cal2_rmse=r['cal2']['rmse'],
            nocal_p95=r['nocal']['p95'], cal1_p95=r['cal1']['p95'], cal2_p95=r['cal2']['p95'],
            cal1_max=r['cal1']['max'], cal2_max=r['cal2']['max'],
        ))
    mc_df = pd.DataFrame(mc_rows)
    log(f'  Monte Carlo (n=60, mount +-10 deg, thigh 0-15 deg, speed 10-60 deg/s, fc=2Hz, gate=0.05g):')
    for mode in ('nocal', 'cal1', 'cal2'):
        log(f'    {mode:5s}: median RMSE={mc_df[mode+"_rmse"].median():.2f} deg, '
            f'95th pct RMSE={mc_df[mode+"_rmse"].quantile(0.95):.2f} deg, '
            f'median P95 err={mc_df[mode+"_p95"].median():.2f} deg')

    return dict(grid=grid_rows, slope=slope_rows, mc=mc_rows)


# =============================================================================
# Part A.2: Daily-life knee flexion from Camargo (22 people) + sit-to-stand
# =============================================================================
def run_part_a2(log, max_people=None):
    log('--- Part A.2: Daily-life flexion from tibia-only acc (Camargo 2021) ---')
    cache_p = os.path.join(CACHE_L1, 'camargo_flexion.csv')
    if os.path.exists(cache_p) and max_people is None:
        df = pd.read_csv(cache_p)
        log(f'Loaded cached {cache_p} ({len(df)} trial rows, {df["person"].nunique()} people)')
    else:
        people = sorted(CR.HEIGHT.keys())
        if max_people is not None:
            people = people[:max_people]
        rows = []
        for person in people:
            zp = os.path.join(CAMARGO_DATA, person.upper() + '.zip')
            if not os.path.exists(zp):
                continue
            m, info = CR.model_for(person)
            idx = K.qidx(m)
            with zipfile.ZipFile(zp) as zf, tempfile.TemporaryDirectory() as td:
                names = zf.namelist()
                lg = sorted(n for n in names if '/levelground/ik/' in n and n.endswith('.mat'))[:3]
                st = sorted(n for n in names if '/stair/ik/' in n and n.endswith('.mat'))[:3]
                picks = [('levelground', n) for n in lg] + [('stair', n) for n in st]
                cal_rec = []
                for _, ik_n in picks[:4]:
                    imu_n = ik_n.replace('/ik/', '/imu/')
                    if imu_n in names:
                        df_i = CR.load_table(zf.extract(imu_n, td))
                        if 'shank_Accel_X' in df_i.columns and len(df_i) >= 400:
                            cal_rec.append((
                                df_i[['shank_Accel_X', 'shank_Accel_Y', 'shank_Accel_Z']].values.astype(float),
                                df_i[['shank_Gyro_X', 'shank_Gyro_Y', 'shank_Gyro_Z']].values.astype(float),
                            ))
                T_p, _ = V.person_frame(cal_rec, cal_rec, FS_SIM) if cal_rec else (None, 'none')

                for mode, ik_n in picks:
                    imu_n = ik_n.replace('/ik/', '/imu/')
                    if imu_n not in names:
                        continue
                    try:
                        ik = CR.load_table(zf.extract(ik_n, td))
                        _, Q = CR.ik_to_Q(m, info, ik, fs_out=FS_SIM)
                        knee_deg = -np.degrees(Q[:, idx['knee_angle_r']])
                        df_i = CR.load_table(zf.extract(imu_n, td))
                        if 'shank_Accel_X' not in df_i.columns or len(df_i) < 400:
                            continue
                        f_s = df_i[['shank_Accel_X', 'shank_Accel_Y', 'shank_Accel_Z']].values.astype(float)
                        w_s = df_i[['shank_Gyro_X', 'shank_Gyro_Y', 'shank_Gyro_Z']].values.astype(float)
                        acc_v200, _ = V.virtual_implant(f_s, w_s, FS_SIM, distance=0.22, anterior=-0.02,
                                                        side='R', T=T_p)
                        n50 = min(len(Q) // 4, len(acc_v200) // 4)
                        acc50 = resample_poly(acc_v200, 1, 4, axis=0)[:n50]
                        k50 = knee_deg[::4][:n50]
                        a_lp = causal_lp(acc50, fc=2.0, fs=FS_CHIP, order=2)
                        th = np.degrees(np.arctan2(-a_lp[:, 0], a_lp[:, 2]))
                        # Exclude first/last 0.5 s transients
                        sl = slice(25, max(26, n50 - 25))
                        rows.append(dict(
                            person=person, mode=mode, trial=os.path.basename(ik_n),
                            knee_max=float(np.percentile(k50[sl], 99)),
                            knee_rng=float(np.percentile(k50[sl], 99) - np.percentile(k50[sl], 5)),
                            shank_rng=float(np.percentile(th[sl], 99) - np.percentile(th[sl], 1)),
                            shank_max=float(np.percentile(th[sl], 99)),
                            shank_min=float(np.percentile(th[sl], 1)),
                        ))
                    except Exception:
                        pass
        df = pd.DataFrame(rows)
        if max_people is None:
            df.to_csv(cache_p, index=False)
        log(f'Extracted Camargo flexion table: {len(df)} trials from {df["person"].nunique()} people')

    # Leave-one-person-out linear regression: knee_max ~ shank_rng (and knee_rng ~ shank_rng)
    def lopo_fit(sub, xcol, ycol):
        preds = np.zeros(len(sub))
        for p in sub['person'].unique():
            tr = sub['person'] != p
            te = ~tr
            coef = np.polyfit(sub.loc[tr, xcol].values, sub.loc[tr, ycol].values, 1)
            preds[te] = np.polyval(coef, sub.loc[te, xcol].values)
        err = np.abs(preds - sub[ycol].values)
        r = float(np.corrcoef(sub[xcol].values, sub[ycol].values)[0, 1])
        per_p = sub.assign(err=err).groupby('person')['err'].mean()
        return dict(r=round(r, 3), r2=round(r * r, 3), mae=round(float(err.mean()), 2),
                    rmse=round(float(np.sqrt(np.mean(err * err))), 2),
                    p95=round(float(np.percentile(err, 95)), 2),
                    per_person_mae_med=round(float(per_p.median()), 2),
                    per_person_mae_max=round(float(per_p.max()), 2),
                    n_people=int(sub['person'].nunique()), n_trials=int(len(sub)))

    res_walk = lopo_fit(df[df['mode'] == 'levelground'], 'shank_rng', 'knee_max')
    res_all = lopo_fit(df, 'shank_rng', 'knee_max')
    res_rng = lopo_fit(df, 'shank_rng', 'knee_rng')
    log(f'  Camargo gait peak flexion (levelground): r={res_walk["r"]}, R2={res_walk["r2"]}, LOPO MAE={res_walk["mae"]} deg (max person {res_walk["per_person_mae_max"]} deg)')
    log(f'  Camargo daily peak flexion (walk+stair): r={res_all["r"]}, R2={res_all["r2"]}, LOPO MAE={res_all["mae"]} deg (max person {res_all["per_person_mae_max"]} deg)')

    # Sit-to-stand identifiability check (old_23_sitstand_healthy)
    import kneil_viewer as KV
    cat = KV.build_catalog()
    d_sts = KV.load_motion(KV.resolve_motion_id('sit_to_stand', cat))
    k_sts = np.degrees(d_sts['Q'][:, 6])
    a_sts = causal_lp(d_sts['acc'].astype(float), fc=2.0, fs=FS_CHIP, order=2)
    th_sts = np.degrees(np.arctan2(-a_sts[:, 0], a_sts[:, 2]))
    sts_info = dict(
        knee_min=round(float(k_sts.min()), 1), knee_max=round(float(k_sts.max()), 1),
        knee_rng=round(float(k_sts.max() - k_sts.min()), 1),
        shank_rng=round(float(th_sts.max() - th_sts.min()), 1),
    )
    log(f'  Sit-to-stand check (old_23): true knee range={sts_info["knee_rng"]} deg ({sts_info["knee_min"]}..{sts_info["knee_max"]}), '
        f'tibia pitch range only {sts_info["shank_rng"]} deg')
    return dict(df=df, walk=res_walk, all=res_all, rng=res_rng, sts=sts_info)


# =============================================================================
# Part B.4: Standing tilt drift & walking shock / ML sway repeatability
# =============================================================================
def run_part_b4(log):
    log('--- Part B.4: Within-person between-recording repeatability (windows_W4s.npz) ---')
    Z = np.load(os.path.join(BASE_V4, 'stepD', 'windows_v11', 'windows_W4s.npz'), allow_pickle=True)
    ds = Z['ds'].astype(str)
    src = Z['src'].astype(str)
    grp = Z['grp'].astype(str)
    rec = Z['rec'].astype(str)
    y = C.y_for({k: Z[k] for k in Z.files if k in C.COLS}, 8)
    X = Z['X']

    idx_sag = FEAT_NAMES.index('tilt_sag_deg')
    idx_cor = FEAT_NAMES.index('tilt_cor_deg')
    idx_mz = FEAT_NAMES.index('mean_z')
    idx_maxm = FEAT_NAMES.index('max_m')
    idx_jerk = FEAT_NAMES.index('jerk_m')
    idx_stdy = FEAT_NAMES.index('std_y')

    def within_person_mdc(mask, col_idx, name):
        sub_df = pd.DataFrame(dict(ds=ds[mask], grp=grp[mask], rec=rec[mask], val=X[mask, col_idx]))
        # Median per (dataset, person, recording)
        rm = sub_df.groupby(['ds', 'grp', 'rec'])['val'].median().reset_index()
        out = {}
        for dname, g in rm.groupby('ds'):
            sds, means = [], []
            for p, gp in g.groupby('grp'):
                if len(gp) >= 2:
                    sds.append(float(gp['val'].std(ddof=1)))
                    means.append(float(gp['val'].mean()))
            if len(sds) >= 5:
                sd_w = float(np.sqrt(np.mean(np.square(sds))))
                mdc95 = 1.96 * np.sqrt(2.0) * sd_w
                med_val = float(np.median(means))
                out[dname] = dict(
                    n_people=len(sds), med_val=round(med_val, 3),
                    sd_within=round(sd_w, 3), mdc95=round(mdc95, 3),
                    cv_pct=round(100.0 * sd_w / max(abs(med_val), 1e-6), 1) if abs(med_val) > 0.05 else None,
                )
        log(f'  {name}: ' + json.dumps(out))
        return out

    m_stand = (src == 'real') & (y == 3) & (X[:, idx_mz] > 0.85)
    m_walk = (src == 'real') & (y == 0)

    rep = dict(
        stand_tilt_sag=within_person_mdc(m_stand, idx_sag, 'Standing sagittal tilt (deg)'),
        stand_tilt_cor=within_person_mdc(m_stand, idx_cor, 'Standing coronal tilt (deg)'),
        walk_max_m=within_person_mdc(m_walk, idx_maxm, 'Walking peak |a| max_m (g)'),
        walk_jerk_m=within_person_mdc(m_walk, idx_jerk, 'Walking jerk_m (g/s)'),
        walk_std_y=within_person_mdc(m_walk, idx_stdy, 'Walking ML sway std_y (g)'),
    )
    return rep


# =============================================================================
# Plots
# =============================================================================
def make_plots(res_a1, res_a2, res_b4):
    # Plot 1: Seated knee angle error (calibration comparison + speed/filter/gate heatmap)
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 4.8))
    mc = pd.DataFrame(res_a1['mc'])
    ax1.boxplot([mc['nocal_rmse'], mc['cal1_rmse'], mc['cal2_rmse']],
                tick_labels=['No cal', '1-pt (90 deg)', '2-pt (90+0 deg)'], showfliers=False)
    ax1.axhline(5.0, color='r', ls='--', lw=1.2, label='5 deg target')
    ax1.set_ylabel('RMSE (deg)')
    ax1.set_title('Seated angle RMSE (mount +-10 deg,\nthigh slope 0-15 deg, 10-60 deg/s)', fontsize=10)
    ax1.grid(True, axis='y', alpha=0.3)
    ax1.legend(fontsize=8)

    gd = pd.DataFrame(res_a1['grid'])
    g_gate = gd[(gd['gate'] == 0.05)]
    for fc, sub in g_gate.groupby('fc'):
        ax2.plot(sub['speed'], sub['rmse_1pt'], 'o-', label=f'LP {fc:g} Hz')
    ax2.axhline(5.0, color='r', ls='--', lw=1.0)
    ax2.set_xlabel('Angular speed (deg/s)')
    ax2.set_ylabel('1-pt RMSE (deg)')
    ax2.set_title('Speed vs LP cut-off (gate ||a|-1|<=0.05g)', fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=8)

    g_fc = gd[(gd['fc'] == 2.0)]
    for gate, sub in g_fc.groupby('gate'):
        lbl = 'no gate' if gate > 10 else f'gate {gate:.2f}g'
        ax3.plot(sub['speed'], sub['p95_1pt'], 's-', label=lbl)
    ax3.axhline(5.0, color='r', ls='--', lw=1.0)
    ax3.set_xlabel('Angular speed (deg/s)')
    ax3.set_ylabel('1-pt 95th-pct error (deg)')
    ax3.set_title('Speed vs |a| gate (LP 2.0 Hz)', fontsize=10)
    ax3.grid(True, alpha=0.3)
    ax3.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(CACHE_L1, 'plot1_seated_angle_error.png'), dpi=130)
    plt.close(fig)

    # Plot 2: Daily-life flexion from Camargo (shank pitch range vs true knee flexion)
    df2 = res_a2['df']
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.0))
    for mode, col, lbl in (('levelground', '#1f77b4', 'Level walking'), ('stair', '#d62728', 'Stairs up/down')):
        sub = df2[df2['mode'] == mode]
        ax1.scatter(sub['shank_rng'], sub['knee_max'], c=col, alpha=0.6, s=28, label=lbl)
    xs = np.linspace(df2['shank_rng'].min(), df2['shank_rng'].max(), 50)
    c_fit = np.polyfit(df2['shank_rng'], df2['knee_max'], 1)
    ax1.plot(xs, np.polyval(c_fit, xs), 'k--', lw=1.5,
             label=f'Linear fit (R2={res_a2["all"]["r2"]:.2f}, LOPO MAE={res_a2["all"]["mae"]:.1f} deg)')
    ax1.set_xlabel('Implant shank pitch range (deg, 2 Hz LP)')
    ax1.set_ylabel('True peak knee flexion (deg, OpenSim IK)')
    ax1.set_title(f'Camargo ({df2["person"].nunique()} people): shank pitch vs peak knee flexion', fontsize=10.5)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=8.5)

    # Per-person mean peak flexion (walk vs stairs)
    pm = df2.groupby(['person', 'mode'])['knee_max'].mean().unstack()
    if 'levelground' in pm.columns and 'stair' in pm.columns:
        pm = pm.dropna()
        x = np.arange(len(pm))
        ax2.bar(x - 0.18, pm['levelground'], width=0.35, color='#1f77b4', label='Level walking')
        ax2.bar(x + 0.18, pm['stair'], width=0.35, color='#d62728', label='Stairs')
        ax2.set_xticks(x)
        ax2.set_xticklabels(pm.index, rotation=45, fontsize=7.5)
        ax2.set_ylabel('True peak knee flexion (deg)')
        ax2.set_title('True peak knee flexion per Camargo person', fontsize=10.5)
        ax2.grid(True, axis='y', alpha=0.3)
        ax2.legend(fontsize=8.5)
    fig.tight_layout()
    fig.savefig(os.path.join(CACHE_L1, 'plot2_daily_flexion_camargo.png'), dpi=130)
    plt.close(fig)

    # Plot 3: Within-person MDC95 repeatability for standing tilt and walking shock / ML sway
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.6))
    ds_st = sorted(res_b4['stand_tilt_sag'].keys())
    x = np.arange(len(ds_st))
    ax1.bar(x - 0.18, [res_b4['stand_tilt_sag'][d]['mdc95'] for d in ds_st], width=0.35, label='Sagittal tilt MDC95')
    ax1.bar(x + 0.18, [res_b4['stand_tilt_cor'][d]['mdc95'] for d in ds_st], width=0.35, label='Coronal tilt MDC95')
    ax1.set_xticks(x); ax1.set_xticklabels(ds_st, fontsize=9)
    ax1.set_ylabel('MDC95 (deg)')
    ax1.set_title('Standing tilt repeatability (within-person MDC95)', fontsize=10.5)
    ax1.grid(True, axis='y', alpha=0.3)
    ax1.legend(fontsize=8.5)

    ds_wk = sorted(res_b4['walk_max_m'].keys())
    x2 = np.arange(len(ds_wk))
    ax2.bar(x2 - 0.25, [res_b4['walk_max_m'][d]['cv_pct'] for d in ds_wk], width=0.25, label='Peak |a| max_m CV%')
    ax2.bar(x2,        [res_b4['walk_jerk_m'][d]['cv_pct'] for d in ds_wk], width=0.25, label='Jerk_m CV%')
    ax2.bar(x2 + 0.25, [res_b4['walk_std_y'][d]['cv_pct'] for d in ds_wk], width=0.25, label='ML sway std_y CV%')
    ax2.set_xticks(x2); ax2.set_xticklabels(ds_wk, rotation=15, fontsize=8.5)
    ax2.set_ylabel('Within-person between-bout CV (%)')
    ax2.set_title('Walking shock & ML sway repeatability', fontsize=10.5)
    ax2.grid(True, axis='y', alpha=0.3)
    ax2.legend(fontsize=8.5)
    fig.tight_layout()
    fig.savefig(os.path.join(CACHE_L1, 'plot3_loosening_repeatability.png'), dpi=130)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description='KNEIL L1: knee flexion & spacer loosening feasibility')
    ap.add_argument('--max-people', type=int, default=None)
    args = ap.parse_args()

    os.makedirs(CACHE_L1, exist_ok=True)
    step_h = config.out_dir('stepH', 'diag_flexion')
    log_path = os.path.join(CACHE_L1, 'diag_flexion_log.txt')
    if os.path.exists(log_path):
        os.remove(log_path)
    log = lambda m: log_msg(m, log_path)
    print(VERSION, flush=True)
    log(f'{VERSION} | cache={CACHE_L1} | stepH={step_h}')

    osim = K.read_osim(K.fetch('osim', folder=config.OPENSIM_DIR))
    res_a1 = run_part_a1(osim, log)
    res_a2 = run_part_a2(log, max_people=args.max_people)
    res_b4 = run_part_b4(log)
    make_plots(res_a1, res_a2, res_b4)

    summary = dict(
        version=VERSION,
        part_a1_slope=res_a1['slope'],
        part_a1_mc_summary={
            m: dict(
                med_rmse=round(float(pd.DataFrame(res_a1['mc'])[m + '_rmse'].median()), 2),
                p95_rmse=round(float(pd.DataFrame(res_a1['mc'])[m + '_rmse'].quantile(0.95)), 2),
                med_p95=round(float(pd.DataFrame(res_a1['mc'])[m + '_p95'].median()), 2),
            ) for m in ('nocal', 'cal1', 'cal2')
        },
        part_a1_grid=res_a1['grid'],
        part_a2={k: v for k, v in res_a2.items() if k != 'df'},
        part_b4=res_b4,
    )
    for out_p in (os.path.join(CACHE_L1, 'l1_summary.json'), os.path.join(step_h, 'l1_summary.json')):
        with open(out_p, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
    log(f'Done! Saved 3 plots in {CACHE_L1} and l1_summary.json in {step_h}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
