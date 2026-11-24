"""
KNEIL R1: Gait recovery score from the 50 Hz tibial-insert accelerometer,
after Ghaffari et al. (J Orthop Res 2025;43:2165-2177, doi:10.1002/jor.70058).
   gait_score 1.0, 24 Nov 2026

Analysis only: no chip, library or protocol change.
Outputs under cache/r1/ (plots, JSON, log) and KNEIL_results/v4/stepI/ (tables, owner_summary.md).

Usage:
    python pipeline/gait_score.py
    python pipeline/gait_score.py --max-people 10   # quick test
"""
import argparse
import glob
import json
import os
import sys
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import spm1d
from scipy.signal import butter, find_peaks, sosfiltfilt

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE_DIR = os.path.join(REPO_ROOT, 'pipeline')
if PIPE_DIR not in sys.path:
    sys.path.insert(0, PIPE_DIR)

import config

VERSION = 'gait_score 1.0'
FS = 50.0
N_NORM = 101
N_HARM = 10
STAGE2_DIR = os.path.join(config.RESULTS, 'virtual_implant', 'stage2')
STAGE2_IDX = os.path.join(config.RESULTS, 'virtual_implant', 'stage2_index_all.csv')
AID_STREAMS = os.path.join(config.RESULTS, 'v4', 'stepF', 'aid_gait', 'streams')
CACHE_R1 = os.path.join(config.CACHE, 'r1')


def log_msg(msg, path):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def lp_filt(x, fc=6.0, fs=FS, order=4):
    if len(x) < 20:
        return np.asarray(x, np.float64)
    sos = butter(order, fc, fs=fs, output='sos')
    return sosfiltfilt(sos, np.asarray(x, np.float64), axis=0)


# =============================================================================
# Part 1: Stride extraction (sagittal a_x vs magnitude |a|) & quality rules
# =============================================================================
def extract_strides(acc50, method='sagittal', max_T=2.20):
    """Extract time-normalised (101-pt) strides from a 50 Hz walking bout (Nx3, g).
    method='sagittal': 2.5 Hz LP on a_x -> swing peak -> refine to nearest |a| peak within [0, +0.25s].
    method='mag': Ghaffari-style peaks on 6 Hz LP |a|.
    Returns dict with strides_xyz (K,101,3), strides_m (K,101), T_arr (K,), duty_arr (K,),
    n_raw_intervals, n_valid."""
    if len(acc50) < int(4.5 * FS):
        return None
    # Trim 0.4 s edges to remove bout start/stop transients
    trim = int(0.4 * FS)
    a = np.asarray(acc50[trim:-trim], np.float64)
    if len(a) < int(3.5 * FS):
        return None

    a6 = lp_filt(a, fc=6.0, fs=FS, order=4)
    mag6 = np.linalg.norm(a6, axis=1)
    min_dist = int(0.65 * FS)

    if method == 'sagittal':
        ax25 = lp_filt(a[:, 0], fc=2.5, fs=FS, order=4)
        pks, _ = find_peaks(ax25, distance=min_dist, prominence=0.12)
        # Refine each sagittal peak to nearest local |a| heel-strike peak in [0, +0.25 s]
        ref = []
        win_r = int(0.25 * FS)
        for p in pks:
            hi = min(len(mag6), p + win_r + 1)
            if hi > p:
                ref.append(p + int(np.argmax(mag6[p:hi])))
        pks = np.array(sorted(set(ref)), int)
    else:
        pks, _ = find_peaks(mag6, distance=min_dist, prominence=0.12)

    if len(pks) < 4:
        return None

    raw_T = np.diff(pks) / FS
    n_raw = len(raw_T)
    med_T = float(np.median(raw_T))
    t_grid = np.linspace(0.0, 1.0, N_NORM)

    s_xyz, s_m, Ts, duties = [], [], [], []
    for k in range(n_raw):
        i0, i1 = int(pks[k]), int(pks[k + 1])
        T = (i1 - i0) / FS
        # Quality rules
        if not (0.70 <= T <= max_T):
            continue
        if abs(T - med_T) > 0.35 * med_T:
            continue
        seg_xyz = a6[i0:i1 + 1]
        seg_m = mag6[i0:i1 + 1]
        if not (0.75 <= float(seg_m.mean()) <= 1.60 and float(np.ptp(seg_m)) >= 0.12):
            continue
        u = np.linspace(0.0, 1.0, len(seg_m))
        norm_xyz = np.column_stack([np.interp(t_grid, u, seg_xyz[:, j]) for j in range(3)])
        norm_m = np.interp(t_grid, u, seg_m)
        # Accelerometer-only duty factor estimate: minimum of a_x in 45-75% cycle (toe-off / swing initiation)
        to_idx = 45 + int(np.argmin(norm_xyz[45:76, 0]))
        s_xyz.append(norm_xyz)
        s_m.append(norm_m)
        Ts.append(T)
        duties.append(to_idx / 100.0)

    if len(Ts) < 3:
        return None
    return dict(
        strides_xyz=np.asarray(s_xyz, np.float32),
        strides_m=np.asarray(s_m, np.float32),
        T_arr=np.asarray(Ts, np.float32),
        duty_arr=np.asarray(duties, np.float32),
        n_raw=int(n_raw),
        n_valid=int(len(Ts)),
    )


def bout_features(st):
    """Part 2: Mean stride waveforms, FFT harmonic powers H1..H10 (per axis & |a|), stride time, duty, variability."""
    sm = st['strides_m']       # (K, 101)
    sxyz = st['strides_xyz']   # (K, 101, 3)
    mean_m = sm.mean(axis=0)
    mean_xyz = sxyz.mean(axis=0)
    wave_sd = float(sm.std(axis=0).mean())
    T_mean = float(st['T_arr'].mean())
    T_cv = float(st['T_arr'].std(ddof=1) / max(T_mean, 1e-6)) if len(st['T_arr']) > 1 else 0.0
    duty = float(st['duty_arr'].mean())

    def harm_power(sig_101):
        # 100-point periodic cycle (drop duplicate endpoint 100 == 0)
        x = sig_101[:100] - float(sig_101[:100].mean())
        F = np.fft.rfft(x) / 100.0
        P = (np.abs(F[1:N_HARM + 1]) ** 2).astype(np.float32)
        return P

    Hm = harm_power(mean_m)
    Hx = harm_power(mean_xyz[:, 0])
    Hy = harm_power(mean_xyz[:, 1])
    Hz = harm_power(mean_xyz[:, 2])
    return dict(
        mean_m=mean_m.astype(np.float32),
        mean_xyz=mean_xyz.astype(np.float32),
        Hm=Hm, Hx=Hx, Hy=Hy, Hz=Hz,
        H1_5_m=float(Hm[:5].sum()),
        H6_10_m=float(Hm[5:10].sum()),
        T_mean=T_mean,
        T_cv=T_cv,
        duty=duty,
        wave_sd=wave_sd,
        n_strides=int(st['n_valid']),
        yield_pct=100.0 * st['n_valid'] / max(st['n_raw'], 1),
    )


def walking_runs(labels, walk_code=1, min_len=250):
    m = (np.asarray(labels) == walk_code).astype(np.int8)
    d = np.diff(np.r_[0, m, 0])
    return [(int(a), int(b)) for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)) if (b - a) >= min_len]


def load_all_bouts(log, max_people=None):
    """Extract stride features across WearGait-PD, KneE-PAD, Marpino, CeTI, and A1 aid_gait."""
    cache_p = os.path.join(CACHE_R1, 'bouts_cache.npz')
    if os.path.exists(cache_p) and max_people is None:
        log(f'Loading cached bouts from {cache_p}')
        Z = np.load(cache_p, allow_pickle=True)
        return {k: Z[k] for k in Z.files}

    idx_df = pd.read_csv(STAGE2_IDX)
    records = []
    trig_cmp = {'sag_cv': [], 'mag_cv': [], 'sag_yield': [], 'mag_yield': []}

    def add_bout(ds, group, person, task, side, acc50, max_T=2.20, do_cmp=False):
        st = extract_strides(acc50, method='sagittal', max_T=max_T)
        if st is None:
            return
        bf = bout_features(st)
        bf.update(ds=ds, group=group, person=person, task=task, side=side)
        records.append(bf)
        if do_cmp:
            st_m = extract_strides(acc50, method='mag', max_T=max_T)
            if st_m is not None:
                bf_m = bout_features(st_m)
                trig_cmp['sag_cv'].append(bf['T_cv'])
                trig_cmp['mag_cv'].append(bf_m['T_cv'])
                trig_cmp['sag_yield'].append(bf['yield_pct'])
                trig_cmp['mag_yield'].append(bf_m['yield_pct'])

    # 1. Stage-2 real datasets: WearGait-PD, KneE-PAD, Marpino, CeTI
    for dname in ('WearGait-PD', 'KneE-PAD', 'Marpino', 'CeTI'):
        sub = idx_df[idx_df['dataset'] == dname]
        files = sorted(sub['file'].unique())
        if max_people is not None:
            files = files[:max_people]
        # Map file -> (person, group)
        fmeta = sub.groupby('file')[['person', 'group']].first().to_dict('index')
        n_before = len(records)
        for fn in files:
            fp = os.path.join(STAGE2_DIR, dname, fn)
            if not os.path.exists(fp):
                continue
            person = str(fmeta[fn]['person'])
            grp = str(fmeta[fn]['group'])
            try:
                Z = np.load(fp, allow_pickle=True)
                tasks = sorted(set(k.split('|')[0] for k in Z.files if k.endswith('|labels')))
                for tname in tasks:
                    # Prefer Right leg (consistent with KNEIL right-knee standard), fallback Left
                    side = 'R' if f'{tname}|R|implant' in Z.files else ('L' if f'{tname}|L|implant' in Z.files else None)
                    if side is None:
                        continue
                    labs = Z[f'{tname}|labels']
                    acc = Z[f'{tname}|{side}|implant']
                    runs = walking_runs(labs, walk_code=1, min_len=int(5.0 * FS))
                    for ri, (a0, b0) in enumerate(runs[:3]):  # up to 3 longest/first bouts per task
                        add_bout(dname, grp, f'{dname}:{person}', f'{tname}_b{ri}', side, acc[a0:b0],
                                 do_cmp=(dname == 'WearGait-PD' and tname == 'SelfPace' and ri == 0))
            except Exception:
                pass
        log(f'  {dname:12s}: extracted {len(records) - n_before:4d} walking bouts from {len(files)} files')

    # 2. A1 walking-aid personas (pick-up walker, rollator, crutches; 21 Camargo people)
    if os.path.isdir(AID_STREAMS):
        sfiles = sorted(glob.glob(os.path.join(AID_STREAMS, '*_pick-upwalker_*_full.npz')))
        if max_people is not None:
            sfiles = sfiles[:max_people]
        n_before = len(records)
        for sf in sfiles:
            Z = np.load(sf, allow_pickle=True)
            meta = json.loads(str(Z['meta']))
            # Use walking windows (y == 0) segments
            acc = Z['acc']
            mov = np.zeros(len(acc), np.int8)
            for ws, yv in zip(Z['win_start'], Z['y']):
                if int(yv) == 0:
                    i0, i1 = int(round(ws * FS)), min(len(acc), int(round((ws + 4.0) * FS)))
                    mov[i0:i1] = 1
            for ri, (a0, b0) in enumerate(walking_runs(mov, walk_code=1, min_len=int(5.0 * FS))[:2]):
                add_bout('Aid-walker', meta['aid'], f'aid:{meta["grp"]}', f'{meta["persona"]}_b{ri}', 'R',
                         acc[a0:b0], max_T=3.20)
        log(f'  Aid-walker  : extracted {len(records) - n_before:4d} walking bouts from {len(sfiles)} personas')

    out = dict(
        ds=np.array([r['ds'] for r in records], dtype=object),
        group=np.array([r['group'] for r in records], dtype=object),
        person=np.array([r['person'] for r in records], dtype=object),
        task=np.array([r['task'] for r in records], dtype=object),
        mean_m=np.stack([r['mean_m'] for r in records]),
        mean_xyz=np.stack([r['mean_xyz'] for r in records]),
        Hm=np.stack([r['Hm'] for r in records]),
        Hx=np.stack([r['Hx'] for r in records]),
        Hy=np.stack([r['Hy'] for r in records]),
        Hz=np.stack([r['Hz'] for r in records]),
        H1_5_m=np.array([r['H1_5_m'] for r in records], np.float32),
        H6_10_m=np.array([r['H6_10_m'] for r in records], np.float32),
        T_mean=np.array([r['T_mean'] for r in records], np.float32),
        T_cv=np.array([r['T_cv'] for r in records], np.float32),
        duty=np.array([r['duty'] for r in records], np.float32),
        wave_sd=np.array([r['wave_sd'] for r in records], np.float32),
        n_strides=np.array([r['n_strides'] for r in records], np.int32),
        trig_cmp_json=json.dumps({k: round(float(np.median(v)), 4) if v else None for k, v in trig_cmp.items()}),
    )
    if max_people is None:
        np.savez_compressed(cache_p, **out)
    return out


def person_means(B, mask):
    """Aggregate bout-level data to one mean row per unique person (avoids pseudoreplication)."""
    idx = np.flatnonzero(mask)
    ps = B['person'][idx].astype(str)
    uniq = sorted(set(ps))
    rows = []
    for p in uniq:
        ii = idx[ps == p]
        rows.append(dict(
            person=p,
            mean_m=B['mean_m'][ii].mean(0),
            mean_xyz=B['mean_xyz'][ii].mean(0),
            Hm=B['Hm'][ii].mean(0),
            Hx=B['Hx'][ii].mean(0),
            Hy=B['Hy'][ii].mean(0),
            Hz=B['Hz'][ii].mean(0),
            H1_5_m=float(B['H1_5_m'][ii].mean()),
            H6_10_m=float(B['H6_10_m'][ii].mean()),
            T_mean=float(B['T_mean'][ii].mean()),
            T_cv=float(B['T_cv'][ii].mean()),
            duty=float(B['duty'][ii].mean()),
            wave_sd=float(B['wave_sd'][ii].mean()),
            n_bouts=len(ii),
        ))
    return rows


def run_spm(YA, YB, paired=False):
    """Run spm1d two-sample or paired t-test (alpha=0.05) on (N, 101) waveforms."""
    if paired:
        t = spm1d.stats.ttest_paired(YA, YB)
    else:
        t = spm1d.stats.ttest2(YA, YB, equal_var=False)
    ti = t.inference(alpha=0.05, two_tailed=True)
    clusters = []
    for c in ti.clusters:
        ep = c.endpoints
        clusters.append(dict(start_pct=round(float(ep[0]), 1), end_pct=round(float(ep[1]), 1), p=round(float(c.P), 4)))
    return dict(z=ti.z.tolist(), zstar=float(ti.zstar), h0reject=bool(ti.h0reject), clusters=clusters)


def cohens_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    sp = np.sqrt(0.5 * (np.var(a, ddof=1) + np.var(b, ddof=1)) + 1e-12)
    return float((np.mean(a) - np.mean(b)) / sp)


# =============================================================================
# Part 5 & 6: 0-100 Gait Similarity Score & 68-byte on-chip compressed score
# =============================================================================
def _log_h(H):
    return np.log10(np.maximum(H, 1e-6))


def build_healthy_ref(ctrl_rows):
    M = np.stack([r['mean_m'] for r in ctrl_rows])
    H = _log_h(np.stack([r['Hm'] for r in ctrl_rows]))
    T = np.array([r['T_mean'] for r in ctrl_rows])
    D = np.array([r['duty'] for r in ctrl_rows])
    return dict(
        m_mean=M.mean(0), m_sd=np.maximum(M.std(0, ddof=1), 0.04),
        h_mean=H.mean(0), h_sd=np.maximum(H.std(0, ddof=1), 0.20),
        T_mean=float(T.mean()), T_sd=max(float(T.std(ddof=1)), 0.05),
        D_mean=float(D.mean()), D_sd=max(float(D.std(ddof=1)), 0.03),
    )


def gait_similarity_score(mean_m, Hm, T_mean, duty, ref, s0=1.8):
    """0-100 score vs healthy reference band (waveform + log10-harmonics + stride time + duty)."""
    z_w = float(np.sqrt(np.mean(((mean_m - ref['m_mean']) / ref['m_sd']) ** 2)))
    z_h = float(np.sqrt(np.mean(((_log_h(Hm) - ref['h_mean']) / ref['h_sd']) ** 2)))
    z_t = abs(T_mean - ref['T_mean']) / ref['T_sd']
    z_d = abs(duty - ref['D_mean']) / ref['D_sd']
    d_comb = np.sqrt(0.40 * z_w * z_w + 0.40 * z_h * z_h + 0.15 * z_t * z_t + 0.05 * z_d * z_d)
    return float(100.0 * np.exp(-0.5 * (d_comb / s0) ** 2))


def compress_and_score(mean_m, Hm, T_mean, duty, ref):
    """Simulate 68-byte on-chip daily summary quantisation and recompute the 0-100 score."""
    # 32-pt uint8 template (0.01 g step, 0..2.55 g)
    idx32 = np.linspace(0, 100, 32)
    m32_q = np.clip(np.round(np.interp(idx32, np.arange(101), mean_m) * 100.0), 0, 255).astype(np.uint8)
    m101_rec = np.interp(np.arange(101), idx32, m32_q.astype(np.float32) / 100.0)
    # 10 log10-quantised uint8 harmonics (log10(H) in [-6, 0] -> 0..255)
    lh = _log_h(Hm)
    h_q = np.clip(np.round((lh + 6.0) / 6.0 * 255.0), 0, 255).astype(np.uint8)
    H_rec = np.power(10.0, (h_q.astype(np.float32) / 255.0) * 6.0 - 6.0)
    # T_mean uint16 ms, duty uint8 (0.5% step)
    T_rec = float(np.clip(round(T_mean * 1000.0), 0, 65535)) / 1000.0
    D_rec = float(np.clip(round(duty * 200.0), 0, 200)) / 200.0
    return gait_similarity_score(m101_rec, H_rec, T_rec, D_rec, ref)


def main():
    ap = argparse.ArgumentParser(description='KNEIL R1: gait recovery score (after Ghaffari et al. 2025)')
    ap.add_argument('--max-people', type=int, default=None)
    args = ap.parse_args()

    os.makedirs(CACHE_R1, exist_ok=True)
    step_i = config.out_dir('stepI', 'gait_score')
    log_path = os.path.join(CACHE_R1, 'gait_score_log.txt')
    if os.path.exists(log_path):
        os.remove(log_path)
    log = lambda m: log_msg(m, log_path)
    print(VERSION, flush=True)
    log(f'{VERSION} | cache={CACHE_R1} | stepI={step_i}')

    B = load_all_bouts(log, max_people=args.max_people)
    log(f'Trigger comparison (WearGait SelfPace): {B["trig_cmp_json"]}')

    ds = B['ds'].astype(str)
    grp = B['group'].astype(str)
    task = B['task'].astype(str)
    is_self = np.array([t.startswith('SelfPace_') or t.startswith('SelfPace_b') for t in task])
    is_self_only = np.array([t.startswith('SelfPace_b') for t in task])
    is_hur = np.array([t.startswith('HurriedPace_') for t in task])

    # Build person-level groups
    g_ctrl = person_means(B, (ds == 'WearGait-PD') & (grp == 'control') & is_self_only)
    g_pd = person_means(B, (ds == 'WearGait-PD') & (grp == 'parkinson') & is_self_only)
    g_knee = person_means(B, (ds == 'KneE-PAD'))
    g_marp_e = person_means(B, (ds == 'Marpino') & np.isin(grp, ('Elderly', 'Disability')))
    g_ceti = person_means(B, (ds == 'CeTI'))
    g_aid = person_means(B, (ds == 'Aid-walker'))

    # Paired SelfPace vs HurriedPace in the exact same WearGait-PD people
    g_self_all = {r['person']: r for r in person_means(B, (ds == 'WearGait-PD') & is_self_only)}
    g_hur_all = {r['person']: r for r in person_means(B, (ds == 'WearGait-PD') & is_hur)}
    paired_p = sorted(set(g_self_all.keys()) & set(g_hur_all.keys()))
    p_self = [g_self_all[p] for p in paired_p]
    p_hur = [g_hur_all[p] for p in paired_p]

    # Speed-matched PD vs Control (T_mean in [1.05, 1.25] s)
    g_ctrl_sm = [r for r in g_ctrl if 1.05 <= r['T_mean'] <= 1.25]
    g_pd_sm = [r for r in g_pd if 1.05 <= r['T_mean'] <= 1.25]

    log(f'Person counts: WG-Control={len(g_ctrl)}, WG-PD={len(g_pd)}, KneE-PAD={len(g_knee)}, '
        f'Marpino(E/D)={len(g_marp_e)}, CeTI={len(g_ceti)}, Aid-walker={len(g_aid)}, '
        f'Paired(Self/Hur)={len(paired_p)}, SpeedMatched(Ctrl/PD)={len(g_ctrl_sm)}/{len(g_pd_sm)}')

    # Part 3: SPM1D comparisons
    spm_res = {
        'KneE-PAD vs WG-Control': run_spm(np.stack([r['mean_m'] for r in g_knee]),
                                          np.stack([r['mean_m'] for r in g_ctrl])),
        'WG-PD vs WG-Control': run_spm(np.stack([r['mean_m'] for r in g_pd]),
                                       np.stack([r['mean_m'] for r in g_ctrl])),
        'Aid-walker vs WG-Control': run_spm(np.stack([r['mean_m'] for r in g_aid]),
                                            np.stack([r['mean_m'] for r in g_ctrl])),
        'Paired SelfPace vs HurriedPace': run_spm(np.stack([r['mean_m'] for r in p_self]),
                                                  np.stack([r['mean_m'] for r in p_hur]), paired=True),
        'Speed-matched PD vs Control': run_spm(np.stack([r['mean_m'] for r in g_pd_sm]),
                                               np.stack([r['mean_m'] for r in g_ctrl_sm])) if len(g_pd_sm) >= 5 else None,
    }
    for k, v in spm_res.items():
        if v:
            log(f'  SPM {k:32s}: reject={v["h0reject"]} | clusters={v["clusters"]}')

    # Effect sizes on harmonics H1..H5, H6..H10, T_mean, duty, wave_sd
    def group_eff(A_rows, B_rows):
        return dict(
            H1_5_d=round(cohens_d([r['H1_5_m'] for r in A_rows], [r['H1_5_m'] for r in B_rows]), 2),
            H6_10_d=round(cohens_d([r['H6_10_m'] for r in A_rows], [r['H6_10_m'] for r in B_rows]), 2),
            T_mean_d=round(cohens_d([r['T_mean'] for r in A_rows], [r['T_mean'] for r in B_rows]), 2),
            duty_d=round(cohens_d([r['duty'] for r in A_rows], [r['duty'] for r in B_rows]), 2),
            wave_sd_d=round(cohens_d([r['wave_sd'] for r in A_rows], [r['wave_sd'] for r in B_rows]), 2),
        )

    eff_tbl = {
        'KneE-PAD vs Control': group_eff(g_knee, g_ctrl),
        'WG-PD vs Control': group_eff(g_pd, g_ctrl),
        'Aid-walker vs Control': group_eff(g_aid, g_ctrl),
        'SelfPace vs HurriedPace': group_eff(p_self, p_hur),
        'Speed-matched PD vs Ctrl': group_eff(g_pd_sm, g_ctrl_sm) if len(g_pd_sm) >= 5 else {},
    }
    log('Effect sizes (Cohen d): ' + json.dumps(eff_tbl))

    # Part 5 & 6: 0-100 Gait Similarity Score (full vs 68-byte compressed)
    ref = build_healthy_ref(g_ctrl)
    groups_map = [
        ('WG-Control (Self)', g_ctrl),
        ('WG-Control (Hurried)', [g_hur_all[r['person']] for r in g_ctrl if r['person'] in g_hur_all]),
        ('CeTI (Healthy)', g_ceti),
        ('WG-PD (Self)', g_pd),
        ('KneE-PAD (Knee)', g_knee),
        ('Marpino (Eld/Dis)', g_marp_e),
        ('Aid-walker (A1)', g_aid),
    ]
    score_summary = {}
    all_full, all_comp = [], []
    for gname, rows in groups_map:
        sf = [gait_similarity_score(r['mean_m'], r['Hm'], r['T_mean'], r['duty'], ref) for r in rows]
        sc = [compress_and_score(r['mean_m'], r['Hm'], r['T_mean'], r['duty'], ref) for r in rows]
        all_full.extend(sf); all_comp.extend(sc)
        score_summary[gname] = dict(
            n=len(sf),
            med=round(float(np.median(sf)), 1),
            iqr=round(float(np.percentile(sf, 75) - np.percentile(sf, 25)), 1),
            mean=round(float(np.mean(sf)), 1),
            sd=round(float(np.std(sf, ddof=1)), 1) if len(sf) > 1 else 0.0,
        )
        log(f'  Score {gname:22s} (n={len(sf):3d}): med={score_summary[gname]["med"]:5.1f} '
            f'(IQR {score_summary[gname]["iqr"]:4.1f}, mean {score_summary[gname]["mean"]:5.1f} +- {score_summary[gname]["sd"]:4.1f})')

    all_full, all_comp = np.asarray(all_full), np.asarray(all_comp)
    comp_r = float(np.corrcoef(all_full, all_comp)[0, 1])
    comp_mae = float(np.mean(np.abs(all_full - all_comp)))
    comp_max = float(np.max(np.abs(all_full - all_comp)))
    log(f'Compression fidelity (68-byte vs full float32, n={len(all_full)}): r={comp_r:.5f}, MAE={comp_mae:.2f} pts, max={comp_max:.2f} pts')

    # Within-person speed shift on score (SelfPace -> HurriedPace in same people)
    spd_d = [gait_similarity_score(r2['mean_m'], r2['Hm'], r2['T_mean'], r2['duty'], ref) -
             gait_similarity_score(r1['mean_m'], r1['Hm'], r1['T_mean'], r1['duty'], ref)
             for r1, r2 in zip(p_self, p_hur)]
    log(f'Within-person speed shift (SelfPace -> HurriedPace, n={len(spd_d)}): median delta={np.median(spd_d):+.1f} pts (IQR {np.percentile(spd_d,75)-np.percentile(spd_d,25):.1f})')

    # (b) Person's own baseline (self-similarity: bout k vs bout 0 using healthy ref SD scale)
    self_same, self_speed = [], []
    for r1, r2 in zip(p_self, p_hur):
        ref_p = dict(ref, m_mean=r1['mean_m'], h_mean=_log_h(r1['Hm']), T_mean=r1['T_mean'], D_mean=r1['duty'])
        self_speed.append(gait_similarity_score(r2['mean_m'], r2['Hm'], r2['T_mean'], r2['duty'], ref_p))
    wg_idx = np.flatnonzero((ds == 'WearGait-PD') & is_self)
    for p in sorted(set(B['person'][wg_idx].astype(str))):
        ii = wg_idx[B['person'][wg_idx].astype(str) == p]
        if len(ii) >= 2:
            i0, i1 = ii[0], ii[1]
            ref_p = dict(ref, m_mean=B['mean_m'][i0], h_mean=_log_h(B['Hm'][i0]),
                         T_mean=float(B['T_mean'][i0]), D_mean=float(B['duty'][i0]))
            self_same.append(gait_similarity_score(B['mean_m'][i1], B['Hm'][i1],
                                                   float(B['T_mean'][i1]), float(B['duty'][i1]), ref_p))
    log(f'Self-baseline score (own bout 0): same-speed repeat med={np.median(self_same):.1f} (n={len(self_same)}) '
        f'| SelfPace->HurriedPace med={np.median(self_speed):.1f} (n={len(self_speed)})')

    # Part 4: Repeatability (MDC95) within-person between-bout & between-session
    # Compute bout-level scores for all bouts
    bout_scores = np.array([
        gait_similarity_score(B['mean_m'][i], B['Hm'][i], float(B['T_mean'][i]), float(B['duty'][i]), ref)
        for i in range(len(B['T_mean']))
    ], np.float32)

    def calc_mdc(mask, label):
        idx = np.flatnonzero(mask)
        df_r = pd.DataFrame(dict(
            person=B['person'][idx].astype(str),
            T_mean=B['T_mean'][idx],
            duty=B['duty'][idx] * 100.0,
            H1_5=B['H1_5_m'][idx],
            H6_10=B['H6_10_m'][idx],
            wave_sd=B['wave_sd'][idx],
            score=bout_scores[idx],
        ))
        out = {}
        for col in ('T_mean', 'duty', 'H1_5', 'H6_10', 'wave_sd', 'score'):
            sds = [float(g[col].std(ddof=1)) for _, g in df_r.groupby('person') if len(g) >= 2]
            if len(sds) >= 5:
                sdw = float(np.sqrt(np.mean(np.square(sds))))
                out[col] = dict(n_people=len(sds), sd_within=round(sdw, 4), mdc95=round(1.96 * np.sqrt(2.0) * sdw, 3))
        log(f'  Repeatability ({label}): ' + json.dumps(out))
        return out

    rep_res = {
        'WearGait-PD between-bout (SelfPace vs matTURN)': calc_mdc((ds == 'WearGait-PD') & is_self, 'WG-Self'),
        'CeTI between-bout/session': calc_mdc((ds == 'CeTI'), 'CeTI'),
        'KneE-PAD between-bout': calc_mdc((ds == 'KneE-PAD'), 'KneE-PAD'),
    }

    # --- Plots ---
    # Plot 1: 2x2 SPM1D curves
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9.0))
    panels = [
        (axes[0, 0], g_knee, g_ctrl, 'KneE-PAD (knee)', 'WG-Control', 'KneE-PAD vs WG-Control'),
        (axes[0, 1], g_pd, g_ctrl, 'WG-PD (Parkinson)', 'WG-Control', 'WG-PD vs WG-Control'),
        (axes[1, 0], g_aid, g_ctrl, 'Aid-walker (A1)', 'WG-Control', 'Aid-walker vs WG-Control'),
        (axes[1, 1], p_self, p_hur, 'SelfPace (same people)', 'HurriedPace', 'Paired SelfPace vs HurriedPace'),
    ]
    pct = np.arange(N_NORM)
    for ax, rA, rB, lA, lB, key in panels:
        YA = np.stack([r['mean_m'] for r in rA])
        YB = np.stack([r['mean_m'] for r in rB])
        ax.plot(pct, YA.mean(0), color='#d62728', lw=1.8, label=f'{lA} (n={len(rA)})')
        ax.fill_between(pct, YA.mean(0) - YA.std(0), YA.mean(0) + YA.std(0), color='#d62728', alpha=0.16)
        ax.plot(pct, YB.mean(0), color='#1f77b4', lw=1.8, label=f'{lB} (n={len(rB)})')
        ax.fill_between(pct, YB.mean(0) - YB.std(0), YB.mean(0) + YB.std(0), color='#1f77b4', alpha=0.16)
        sp = spm_res[key]
        for cl in sp['clusters']:
            ax.axvspan(cl['start_pct'], cl['end_pct'], color='#ffbf00', alpha=0.25,
                       label=f'SPM p={cl["p"]:.3f}' if cl == sp['clusters'][0] else None)
        ax.set_title(f'{key} ({len(sp["clusters"])} sig. SPM regions)', fontsize=10, fontweight='bold')
        ax.set_xlabel('Gait cycle (%)')
        ax.set_ylabel('|a| (g, 6 Hz LP)')
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8, loc='upper right')
    fig.suptitle('SPM1D two-sample & paired t-tests on 101-point mean |a| stride waveforms (alpha=0.05)',
                 fontsize=12, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(os.path.join(CACHE_R1, 'plot1_spm_curves.png'), dpi=130)
    plt.close(fig)

    # Plot 2: Harmonic powers H1..H10 per group
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 4.8))
    hs = np.arange(1, N_HARM + 1)
    for gname, rows, col in (('WG-Control', g_ctrl, '#1f77b4'), ('WG-PD', g_pd, '#ff7f0e'),
                             ('KneE-PAD', g_knee, '#d62728'), ('Aid-walker', g_aid, '#9467bd'),
                             ('WG-Hurried', p_hur, '#2ca02c')):
        H = np.stack([r['Hm'] for r in rows])
        ax1.semilogy(hs, np.median(H, axis=0) + 1e-6, 'o-', lw=1.6, color=col, label=f'{gname} (n={len(rows)})')
    ax1.axvline(5.5, color='k', ls='--', lw=0.9, label='Ghaffari 12.5 Hz limit (H5)')
    ax1.set_xticks(hs)
    ax1.set_xlabel('FFT Harmonic number (H1..H10)')
    ax1.set_ylabel('Median harmonic power of |a| (g^2)')
    ax1.set_title('Stride |a| harmonic power spectrum (50 Hz tibia)', fontsize=10.5)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=8)

    # Boxplot of H1..H5 sum across groups
    h5_data = [[r['H1_5_m'] for r in rows] for _, rows in groups_map]
    ax2.boxplot(h5_data, tick_labels=[g.split(' ')[0] + '\n' + (g.split(' ')[1] if ' ' in g else '')
                                      for g, _ in groups_map], showfliers=False)
    ax2.set_ylabel('Sum of H1..H5 power of |a| (g^2)')
    ax2.set_title('Harmonic power H1..H5 across groups', fontsize=10.5)
    ax2.grid(True, axis='y', alpha=0.3)
    ax2.tick_params(axis='x', labelsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(CACHE_R1, 'plot2_harmonics_and_speed.png'), dpi=130)
    plt.close(fig)

    # Plot 3: 0-100 Gait Similarity Score per group + 68-byte compression scatter
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 4.8))
    sc_data = [[gait_similarity_score(r['mean_m'], r['Hm'], r['T_mean'], r['duty'], ref) for r in rows]
               for _, rows in groups_map]
    ax1.boxplot(sc_data, tick_labels=[g.replace(' ', '\n') for g, _ in groups_map], showfliers=False)
    ax1.set_ylim(0, 105)
    ax1.set_ylabel('Gait Similarity Score (0-100)')
    ax1.set_title('0-100 Gait Similarity Score vs healthy control reference', fontsize=10.5)
    ax1.grid(True, axis='y', alpha=0.3)
    ax1.tick_params(axis='x', labelsize=7.5)

    ax2.scatter(all_full, all_comp, s=16, alpha=0.65, color='#1f77b4')
    ax2.plot([0, 100], [0, 100], 'k--', lw=1.0)
    ax2.set_xlabel('Full float32 score (101-pt waveform + float harmonics)')
    ax2.set_ylabel('68-byte on-chip compressed score (32-pt uint8 + uint8 harm)')
    ax2.set_title(f'Compression fidelity: r={comp_r:.4f}, MAE={comp_mae:.2f} pts (max {comp_max:.2f})', fontsize=10)
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(CACHE_R1, 'plot3_gait_score_and_compression.png'), dpi=130)
    plt.close(fig)

    summary = dict(
        version=VERSION,
        trigger_cmp=json.loads(str(B['trig_cmp_json'])),
        spm={k: {'h0reject': v['h0reject'], 'zstar': round(v['zstar'], 2), 'clusters': v['clusters']}
             for k, v in spm_res.items() if v is not None},
        effect_sizes=eff_tbl,
        scores=score_summary,
        compression=dict(r=round(comp_r, 5), mae=round(comp_mae, 3), max_err=round(comp_max, 3), n=int(len(all_full))),
        speed_shift_med=round(float(np.median(spd_d)), 2),
        repeatability=rep_res,
    )
    for outp in (os.path.join(CACHE_R1, 'r1_summary.json'), os.path.join(step_i, 'r1_summary.json')):
        with open(outp, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
    log(f'Done! Saved 3 plots in {CACHE_R1} and r1_summary.json in {step_i}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
