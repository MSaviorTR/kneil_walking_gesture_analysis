"""
KNEIL G3 diagnostic: why the two synthetic aid-gait sources disagree (analysis only).
   diag_aid_gap 1.0, 23 Nov 2026

Compares:
  - Source 1: pipeline/aid_gait.py (462 personas from 21 Camargo subjects, stepF/aid_gait)
  - Source 2: old HTML viewer spacer personas (old_14..old_21, AB07 strides)
  - Real benchmarks: real still + real slow walking (WearGait-PD SlowPace, Caicedo 0.6 m/s,
    Camargo treadmill 0.5 m/s) from stepD/windows_v11/windows_W4s.npz and old viewer.

Analysis only: writes ONLY under cache/g3/ (plots, JSON summary, cached aid1.0 seed-0 forest
for swap tests, log). Never modifies existing code or KNEIL_results.

Usage:
    python pipeline/diag_aid_gap.py
"""
import json
import os
import pickle
import sys
import time
from collections import Counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import butter, sosfilt, welch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE_DIR = os.path.join(REPO_ROOT, 'pipeline')
VIEWER_DIR = os.path.join(REPO_ROOT, 'viewer')
for d in (PIPE_DIR, VIEWER_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import config
import aid_gait as AG
import cv_aid as CVA
import stage3 as S3
import kneil_viewer as KV

VERSION = 'diag_aid_gap 1.0'
OUT_DIR = os.path.join(config.CACHE, 'g3')
LOG_PATH = os.path.join(OUT_DIR, 'diag_aid_gap_log.txt')
BASE_V4 = os.path.join(config.RESULTS, 'v4')
AID_DIR = os.path.join(BASE_V4, 'stepF', 'aid_gait')
CV_AID_DIR = os.path.join(BASE_V4, 'stepF', 'cv_aid')

FEAT_NAMES = CVA.FEAT_NAMES
VIEWER_IDS = CVA.VIEWER_IDS
FS = 50.0
W = 200
H = 50


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def load_or_fit_aid10_seed0():
    """Fit exact A1 aid1.0 final forest (seed 0) once and cache under cache/g3/."""
    pkl = os.path.join(OUT_DIR, 'aid10_seed0.pkl')
    if os.path.exists(pkl):
        log(f'Loading cached aid1.0 seed-0 forest from {pkl}')
        with open(pkl, 'rb') as f:
            return pickle.load(f)
    log('Fitting exact A1 aid1.0 final forest (seed 0) in cache/g3/...')
    t0 = time.time()
    A = CVA.load_base(4, BASE_V4)
    aid = CVA.load_aid('aid_gait')
    gf = CVA.fold_map(2, BASE_V4)
    fold = CVA.C.folds_for(A, gf, log=lambda *x: None)
    fold_aid = CVA.aid_folds(aid, gf)
    y = CVA.C.y_for(A, 8)
    model = CVA.fit_variant(A, aid, fold, fold_aid, 'aid1.0', 0, y, final=True)
    with open(pkl, 'wb') as f:
        pickle.dump(model, f)
    log(f'Fitted and cached aid1.0 seed-0 forest ({S3.T.n_nodes(model)} nodes) in {time.time() - t0:.1f} s')
    return model


def predict_rule06(model, X):
    p = model.predict_proba(np.asarray(X, np.float32))
    pred = np.argmax(p, axis=1).astype(np.int8)
    return CVA.rule06(pred, p), p


def features_from_acc50(acc50, lib):
    a_lp = S3.T.apply_lowpass(np.asarray(acc50, np.float64), FS, 6.0).astype(np.float32)
    X = [S3.T.features(lib, a_lp[s:s + W, 0], a_lp[s:s + W, 1], a_lp[s:s + W, 2], FS)
         for s in range(0, len(a_lp) - W + 1, H)]
    return np.asarray(X, np.float32).reshape(-1, 20), a_lp


def cohens_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    sa, sb = np.std(a, ddof=1), np.std(b, ddof=1)
    sp = np.sqrt(0.5 * (sa * sa + sb * sb) + 1e-12)
    return float((np.mean(a) - np.mean(b)) / sp)


def cliffs_delta(a, b, max_n=2000):
    rng = np.random.default_rng(0)
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) > max_n:
        a = rng.choice(a, max_n, replace=False)
    if len(b) > max_n:
        b = rng.choice(b, max_n, replace=False)
    diff = a[:, None] - b[None, :]
    return float((np.sum(diff > 0) - np.sum(diff < 0)) / (len(a) * len(b)))


def trace_tree_paths(model, X):
    """Count how often each feature appears on decision paths and at root splits for X."""
    root_counts = Counter()
    path_counts = Counter()
    still_thresh = {}
    for est in model.estimators_:
        tree = est.tree_
        rf = int(tree.feature[0])
        rt = float(tree.threshold[0])
        root_counts[(FEAT_NAMES[rf], round(rt, 3))] += 1
        node_ind = est.decision_path(X)
        preds = est.predict(X)
        for i in range(len(X)):
            nodes = node_ind.indices[node_ind.indptr[i]:node_ind.indptr[i + 1]]
            for nd in nodes[:-1]:
                fi = int(tree.feature[nd])
                if fi >= 0:
                    fn = FEAT_NAMES[fi]
                    path_counts[fn] += 1
                    if int(preds[i]) == 3:
                        still_thresh.setdefault(fn, []).append((float(X[i, fi]), float(tree.threshold[nd])))
    return root_counts, path_counts, still_thresh


def inspect_pause_and_signal_stats(acc50, moving_mask):
    """Measure noise floor during pauses, static gravity magnitude & tilt, and dynamic RMS."""
    acc = np.asarray(acc50, float)
    mov = np.asarray(moving_mask, bool)
    st = ~mov
    out = {}
    if st.sum() >= 25:
        a_st = acc[st]
        m_st = np.linalg.norm(a_st, axis=1)
        out['pause_n'] = int(st.sum())
        out['pause_mean_xyz'] = [round(float(x), 4) for x in a_st.mean(0)]
        out['pause_mean_m'] = round(float(m_st.mean()), 4)
        out['pause_std_xyz'] = [round(float(x), 4) for x in a_st.std(0)]
        out['pause_std_m'] = round(float(m_st.std()), 4)
        out['pause_tilt_sag_deg'] = round(float(np.degrees(np.arctan2(-a_st[:, 0].mean(), a_st[:, 2].mean()))), 2)
        out['pause_tilt_cor_deg'] = round(float(np.degrees(np.arctan2(a_st[:, 1].mean(), a_st[:, 2].mean()))), 2)
    if mov.sum() >= 25:
        a_mv = acc[mov]
        m_mv = np.linalg.norm(a_mv, axis=1)
        out['move_n'] = int(mov.sum())
        out['move_mean_m'] = round(float(m_mv.mean()), 4)
        out['move_std_m'] = round(float(m_mv.std()), 4)
        out['move_std_xyz'] = [round(float(x), 4) for x in a_mv.std(0)]
        out['move_ptp_m'] = round(float(np.ptp(m_mv)), 4)
    # Pause run lengths
    runs = []
    cur = 0
    for v in st:
        if v:
            cur += 1
        elif cur > 0:
            runs.append(cur / FS)
            cur = 0
    if cur > 0:
        runs.append(cur / FS)
    out['n_pauses'] = len(runs)
    out['pause_dur_s'] = [round(r, 2) for r in runs[:12]]
    out['pause_dur_med_s'] = round(float(np.median(runs)), 2) if runs else 0.0
    return out


def plot_matched_pair(name, s1_acc, s1_mov, s1_title, s2_acc, s2_mov, s2_title, out_png):
    """Plot 20 s of LP x/y/z, magnitude Welch spectrum, and single-stride overlay for a matched pair."""
    s1_lp = S3.T.apply_lowpass(s1_acc.astype(np.float64), FS, 6.0)
    s2_lp = S3.T.apply_lowpass(s2_acc.astype(np.float64), FS, 6.0)
    n20 = min(int(20 * FS), len(s1_lp), len(s2_lp))
    t20 = np.arange(n20) / FS

    fig = plt.figure(figsize=(14, 10))
    gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 1, 1.35], hspace=0.40, wspace=0.22)
    axes_lbl = ['x anterior (g)', 'y left (g)', 'z superior (g)']
    for k in range(3):
        ax = fig.add_subplot(gs[k, :])
        ax.plot(t20, s1_lp[:n20, k], lw=1.0, color='#1f77b4', label=f'Source 1 (aid_gait): {s1_title}')
        ax.plot(t20, s2_lp[:n20, k], lw=1.0, color='#d62728', alpha=0.85, label=f'Source 2 (old viewer): {s2_title}')
        # Shade Source 2 pauses lightly
        st2 = ~s2_mov[:n20].astype(bool)
        if st2.any():
            ax.fill_between(t20, ax.get_ylim()[0], ax.get_ylim()[1], where=st2,
                            color='#d62728', alpha=0.07, label='Source 2 pause' if k == 0 else None)
        ax.set_ylabel(axes_lbl[k], fontsize=9)
        ax.grid(True, alpha=0.25)
        if k == 0:
            ax.legend(loc='upper right', fontsize=8, ncol=2)
            ax.set_title(f'Matched pair: {name} (20 s at 50 Hz after 6 Hz chip low-pass)', fontsize=11, fontweight='bold')
        if k == 2:
            ax.set_xlabel('Time (s)', fontsize=9)

    # Welch PSD of |a| - mean(|a|) during moving samples
    ax_psd = fig.add_subplot(gs[3, 0])
    for sig, mov, col, lbl in ((s1_lp, s1_mov, '#1f77b4', 'Source 1 (aid_gait)'),
                               (s2_lp, s2_mov, '#d62728', 'Source 2 (old viewer)')):
        m = np.linalg.norm(sig, axis=1)
        m_mv = m[mov.astype(bool)] if mov.sum() >= 256 else m
        f, Pxx = welch(m_mv - m_mv.mean(), fs=FS, nperseg=min(256, len(m_mv)))
        ax_psd.semilogy(f, np.sqrt(Pxx) + 1e-6, lw=1.3, color=col, label=lbl)
    ax_psd.axvspan(2.0, 6.0, color='#ff7f0e', alpha=0.14, label='2-6 Hz roughness passband')
    ax_psd.axvline(6.0, color='k', ls='--', lw=0.8, label='6 Hz chip LP')
    ax_psd.set_xlim(0, 14)
    ax_psd.set_xlabel('Frequency (Hz)', fontsize=9)
    ax_psd.set_ylabel('ASD of |a| (g / sqrt(Hz))', fontsize=9)
    ax_psd.set_title('Magnitude spectrum (moving samples, after 6 Hz LP)', fontsize=10)
    ax_psd.grid(True, alpha=0.25)
    ax_psd.legend(loc='upper right', fontsize=7.5)

    # Single stride overlay aligned at peak |a| during steady interior walking (skip t < 4.5 s transition spike)
    ax_str = fig.add_subplot(gs[3, 1])
    for sig, mov, col, lbl in ((s1_lp, s1_mov, '#1f77b4', 'Source 1 |a|'),
                               (s2_lp, s2_mov, '#d62728', 'Source 2 |a|')):
        m = np.linalg.norm(sig, axis=1)
        i_lo = min(int(5.0 * FS), len(m) // 3)
        i_hi = max(i_lo + 10, min(int(18.0 * FS), len(m) - int(2.0 * FS)))
        cand = np.where(mov[i_lo:i_hi].astype(bool))[0] + i_lo
        if len(cand):
            pk = cand[int(np.argmax(m[cand]))]
        else:
            pk = (i_lo + i_hi) // 2
        seg = m[pk - int(1.0 * FS):pk + int(1.5 * FS)]
        ts = (np.arange(len(seg)) - int(1.0 * FS)) / FS
        ax_str.plot(ts, seg, lw=1.4, color=col, label=lbl)
    ax_str.axvline(0.0, color='k', ls=':', lw=0.8)
    ax_str.set_xlabel('Time relative to peak |a| (s)', fontsize=9)
    ax_str.set_ylabel('|a| (g)', fontsize=9)
    ax_str.set_title('Single steady stride overlay (t in 5-18 s, aligned at peak |a|)', fontsize=10)
    ax_str.grid(True, alpha=0.25)
    ax_str.legend(loc='upper right', fontsize=8)

    fig.savefig(out_png, dpi=130, bbox_inches='tight')
    plt.close(fig)


def plot_20_features_boxplots(groups_dict, out_png):
    """4x5 boxplot grid of all 20 chip features across the comparison groups."""
    fig, axes = plt.subplots(4, 5, figsize=(18, 12))
    labels = list(groups_dict.keys())
    colors = ['#1f77b4', '#d62728', '#ff7f0e', '#2ca02c', '#7f7f7f'][:len(labels)]
    for idx, fname in enumerate(FEAT_NAMES):
        ax = axes[idx // 5, idx % 5]
        vals = [groups_dict[k][:, idx] for k in labels]
        bp = ax.boxplot(vals, tick_labels=[str(i + 1) for i in range(len(labels))],
                        showfliers=False, patch_artist=True, widths=0.6)
        for patch, c in zip(bp['boxes'], colors):
            patch.set_facecolor(c)
            patch.set_alpha(0.55)
        for med in bp['medians']:
            med.set_color('black')
            med.set_linewidth(1.3)
        ax.set_title(fname, fontsize=9, fontweight='bold')
        ax.grid(True, axis='y', alpha=0.25)
        ax.tick_params(labelsize=8)
    legend_handles = [plt.Line2D([0], [0], color=c, lw=8, alpha=0.65, label=f'{i+1}: {lbl}')
                      for i, (lbl, c) in enumerate(zip(labels, colors))]
    fig.legend(handles=legend_handles, loc='upper center', bbox_to_anchor=(0.5, 0.965),
               ncol=len(labels), fontsize=9, frameon=True)
    fig.suptitle('All 20 chip features: Source 1 vs Source 2 vs Real slow walking vs Real still',
                 fontsize=13, fontweight='bold', y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out_png, dpi=130, bbox_inches='tight')
    plt.close(fig)


def plot_swap_results(fwd_rows, rev_rows, out_png):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))
    # Forward swaps on old_14, old_18, old_20
    names = [r['swap'] for r in fwd_rows]
    y = np.arange(len(names))
    h = 0.26
    ax1.barh(y - h, [r['old_14'] for r in fwd_rows], height=h, color='#d62728', label='old_14 (early walker)')
    ax1.barh(y,     [r['old_18'] for r in fwd_rows], height=h, color='#ff7f0e', label='old_18 (toe-touch walker)')
    ax1.barh(y + h, [r['old_20'] for r in fwd_rows], height=h, color='#9467bd', label='old_20 (static-spacer walker)')
    ax1.set_yticks(y)
    ax1.set_yticklabels(names, fontsize=8.5)
    ax1.invert_yaxis()
    ax1.set_xlim(0, 108)
    ax1.set_xlabel('aid1.0 walking recall (%)')
    ax1.set_title('Forward swap test: Source 2 -> Source 1 steps', fontsize=10.5, fontweight='bold')
    ax1.grid(True, axis='x', alpha=0.3)
    ax1.legend(loc='lower right', fontsize=8)

    # Reverse swaps on Source 1 slow pick-up walker streams
    rnames = [r['swap'] for r in rev_rows]
    ry = np.arange(len(rnames))
    ax2.barh(ry, [r['walk_recall_pct'] for r in rev_rows], height=0.55, color='#1f77b4')
    for i, r in enumerate(rev_rows):
        ax2.text(r['walk_recall_pct'] + 1.2, i, f'{r["walk_recall_pct"]:.1f}%', va='center', fontsize=8.5)
    ax2.set_yticks(ry)
    ax2.set_yticklabels(rnames, fontsize=8.5)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 112)
    ax2.set_xlabel('aid1.0 walking recall (%)')
    ax2.set_title('Reverse swap test: Source 1 (slow pick-up walker) strips', fontsize=10.5, fontweight='bold')
    ax2.grid(True, axis='x', alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_png, dpi=130, bbox_inches='tight')
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    print(VERSION, flush=True)
    log(f'{VERSION} | out={OUT_DIR}')

    lib = S3.init_tinyml()
    model = load_or_fit_aid10_seed0()

    # --- Load Source 1 (aid_gait) ---
    aid_win = np.load(os.path.join(AID_DIR, 'aid_windows_W4s.npz'), allow_pickle=True)
    aid_df = pd.read_csv(os.path.join(AID_DIR, 'aid_personas.csv'))
    log(f'Loaded Source 1 (aid_gait): {len(aid_df)} personas, {len(aid_win["y"])} windows')

    # --- Load Source 2 (old_14..old_21 from kneil_viewer) + old_00 (AB07 0.5 m/s) + old_06 (Caicedo 0.6 m/s) ---
    catalog = KV.build_catalog()
    s2_data = {}
    for mid in VIEWER_IDS:
        e = KV.resolve_motion_id(mid, catalog)
        d = KV.load_motion(e)
        X, y, steps, share = CVA.viewer_rule_c(e, d, OUT_DIR)
        pred, proba = predict_rule06(model, X)
        s2_data[mid] = dict(entry=e, data=d, X=X, y=y, steps=steps, share=share, pred=pred, proba=proba)
        wa = (y == 0)
        rec = 100.0 * float((pred[wa] == 0).mean()) if wa.any() else float('nan')
        log(f'  Verify aid1.0 seed0 on {mid[:22]}: {int(wa.sum())} walk win -> {rec:.1f}% called walking')

    # Also load real slow walking from windows_W4s.npz + old_00/old_06
    A = CVA.load_base(4, BASE_V4)
    src = A['src'].astype(str)
    ds = A['ds'].astype(str)
    rec_col = A['rec'].astype(str)
    y_base = CVA.C.y_for(A, 8)
    X_real_still = A['X'][(src == 'real') & (y_base == 3)]
    X_wg_self = A['X'][(ds == 'WearGait-PD') & (rec_col == 'SelfPace') & (y_base == 0)]
    q25_stdm = float(np.percentile(X_wg_self[:, FEAT_NAMES.index('std_m')], 25))
    X_wg_slow = X_wg_self[X_wg_self[:, FEAT_NAMES.index('std_m')] <= q25_stdm]
    X_wg_all = A['X'][(ds == 'WearGait-PD') & (y_base == 0)]

    # old_00 (AB07 treadmill 0.5 m/s) and old_06 (Caicedo 0.6 m/s)
    e_ab07_05 = KV.resolve_motion_id('old_00', catalog)
    d_ab07_05 = KV.load_motion(e_ab07_05)
    X_ab07_05, _ = features_from_acc50(d_ab07_05['acc'], lib)
    e_caic_06 = KV.resolve_motion_id('old_06', catalog)
    d_caic_06 = KV.load_motion(e_caic_06)
    X_caic_06, _ = features_from_acc50(d_caic_06['acc'], lib)
    log(f'Real benchmarks: real_still={len(X_real_still)}, WearGait-PD SlowPace={len(X_wg_slow)}, '
        f'Camargo 0.5={len(X_ab07_05)}, Caicedo 0.6={len(X_caic_06)}')

    # Check aid1.0 recall on WearGait-PD SlowPace
    p_wg_slow, _ = predict_rule06(model, X_wg_slow)
    log(f'aid1.0 seed0 on WearGait-PD SlowPace (n={len(X_wg_slow)}): {100*(p_wg_slow==0).mean():.1f}% walking, '
        f'{100*(p_wg_slow==3).mean():.1f}% still')

    # --- Part 1 & 2: Matched pairs ---
    # Pair A: old_14 (pick-up walker, v_avg=0.20, pause=41%, full/WBAT) vs closest A1 pick-up walker full
    cand_w = aid_df[(aid_df['aid'] == 'pick-up walker') & (aid_df['wb'] == 'full')].copy()
    cand_w['dist'] = np.abs(cand_w['v_avg'] - 0.20) + 0.5 * np.abs(cand_w['pause_share'] - 0.40)
    best_w = cand_w.sort_values('dist').iloc[0]
    s1_w = np.load(os.path.join(AID_DIR, 'streams', best_w['persona'] + '.npz'), allow_pickle=True)
    s1_w_meta = json.loads(str(s1_w['meta']))
    # Reconstruct sample-level moving mask for s1_w from contact/moving_share (approx) or window moving_share
    s1_w_mov = np.zeros(len(s1_w['acc']), dtype=bool)
    for ws, ms in zip(s1_w['win_start'], s1_w['moving_share']):
        if ms >= 0.5:
            i0, i1 = int(round(ws * FS)), min(len(s1_w_mov), int(round((ws + 4.0) * FS)))
            s1_w_mov[i0:i1] = True

    s2_w_d = s2_data['old_14_your_protocol_early_wa']['data']
    s2_w_mov = (s2_w_d['true_lbl'] == 0)

    # Pair B: old_15 (crutches, v_avg=0.44, pause=20%, full) vs closest A1 crutches
    cand_c = aid_df[(aid_df['aid'] == 'crutches') & (aid_df['wb'].isin(['full', 'partial']))].copy()
    cand_c['dist'] = np.abs(cand_c['v_avg'] - 0.44) + 0.5 * np.abs(cand_c['pause_share'] - 0.20)
    best_c = cand_c.sort_values('dist').iloc[0]
    s1_c = np.load(os.path.join(AID_DIR, 'streams', best_c['persona'] + '.npz'), allow_pickle=True)
    s1_c_meta = json.loads(str(s1_c['meta']))
    s1_c_mov = np.zeros(len(s1_c['acc']), dtype=bool)
    for ws, ms in zip(s1_c['win_start'], s1_c['moving_share']):
        if ms >= 0.5:
            i0, i1 = int(round(ws * FS)), min(len(s1_c_mov), int(round((ws + 4.0) * FS)))
            s1_c_mov[i0:i1] = True

    s2_c_d = s2_data['old_15_your_protocol_crutches']['data']
    s2_c_mov = (s2_c_d['true_lbl'] == 0)

    log(f'Matched Pair A (walker): S1={best_w["persona"]} (v={best_w["v_avg"]:.2f}, pause={100*best_w["pause_share"]:.0f}%) vs S2=old_14')
    log(f'Matched Pair B (crutches): S1={best_c["persona"]} (v={best_c["v_avg"]:.2f}, pause={100*best_c["pause_share"]:.0f}%) vs S2=old_15')

    plot_matched_pair(
        'Pick-up walker (~0.20 m/s, ~40% pause)',
        s1_w['acc'], s1_w_mov, f'{best_w["persona"]} (v={best_w["v_avg"]:.2f})',
        s2_w_d['acc'], s2_w_mov, 'old_14 early walker (v=0.20)',
        os.path.join(OUT_DIR, 'plot1_signals_walker.png'),
    )
    plot_matched_pair(
        'Crutches (~0.44 m/s, ~20% pause)',
        s1_c['acc'], s1_c_mov, f'{best_c["persona"]} (v={best_c["v_avg"]:.2f})',
        s2_c_d['acc'], s2_c_mov, 'old_15 crutches (v=0.44)',
        os.path.join(OUT_DIR, 'plot2_signals_crutches.png'),
    )

    sig_stats = {
        'S1_walker': inspect_pause_and_signal_stats(s1_w['acc'], s1_w_mov),
        'S2_old14': inspect_pause_and_signal_stats(s2_w_d['acc'], s2_w_mov),
        'S2_old20': inspect_pause_and_signal_stats(
            s2_data['old_20_static_spacer_partial']['data']['acc'],
            s2_data['old_20_static_spacer_partial']['data']['true_lbl'] == 0),
        'S1_crutches': inspect_pause_and_signal_stats(s1_c['acc'], s1_c_mov),
        'S2_old15': inspect_pause_and_signal_stats(s2_c_d['acc'], s2_c_mov),
    }
    log('Signal stats (pause & move): ' + json.dumps(sig_stats))

    # --- Part 3: 20 features + effect sizes + tree path trace ---
    m_s1_slow_w = (aid_win['y'] == 0) & (aid_win['aid'].astype(str) == 'pick-up walker') & (aid_win['speed_band'].astype(str) == '0.15-0.25')
    X_s1_slow_w = aid_win['X'][m_s1_slow_w]
    X_s2_walkers = np.vstack([
        s2_data['old_14_your_protocol_early_wa']['X'][s2_data['old_14_your_protocol_early_wa']['y'] == 0],
        s2_data['old_18_toe_touch_walker']['X'][s2_data['old_18_toe_touch_walker']['y'] == 0],
        s2_data['old_20_static_spacer_partial']['X'][s2_data['old_20_static_spacer_partial']['y'] == 0],
    ])
    X_s2_14_20 = np.vstack([
        s2_data['old_14_your_protocol_early_wa']['X'][s2_data['old_14_your_protocol_early_wa']['y'] == 0],
        s2_data['old_20_static_spacer_partial']['X'][s2_data['old_20_static_spacer_partial']['y'] == 0],
    ])
    X_real_slow_all = np.vstack([X_wg_slow, X_ab07_05, X_caic_06])

    effect_rows = []
    for i, fn in enumerate(FEAT_NAMES):
        d_val = cohens_d(X_s1_slow_w[:, i], X_s2_14_20[:, i])
        cd_val = cliffs_delta(X_s1_slow_w[:, i], X_s2_14_20[:, i])
        effect_rows.append(dict(
            feature=fn,
            s1_med=round(float(np.median(X_s1_slow_w[:, i])), 4),
            s2_14_20_med=round(float(np.median(X_s2_14_20[:, i])), 4),
            s2_allw_med=round(float(np.median(X_s2_walkers[:, i])), 4),
            wg_slow_med=round(float(np.median(X_wg_slow[:, i])), 4),
            ab07_05_med=round(float(np.median(X_ab07_05[:, i])), 4),
            caic_06_med=round(float(np.median(X_caic_06[:, i])), 4),
            real_still_med=round(float(np.median(X_real_still[:, i])), 4),
            cohens_d=round(d_val, 3),
            cliffs_delta=round(cd_val, 3),
        ))
    effect_rows.sort(key=lambda r: abs(r['cohens_d']), reverse=True)
    log('Top 10 features separating Source 1 (slow pick-up walker) vs Source 2 (old_14+old_20):')
    for r in effect_rows[:10]:
        log(f'  {r["feature"]:13s} | d={r["cohens_d"]:+6.2f} delta={r["cliffs_delta"]:+5.2f} | '
            f'S1={r["s1_med"]:.4f}  S2(14/20)={r["s2_14_20_med"]:.4f}  WG_slow={r["wg_slow_med"]:.4f}  '
            f'AB07_0.5={r["ab07_05_med"]:.4f}  Caic_0.6={r["caic_06_med"]:.4f}  still={r["real_still_med"]:.4f}')

    root_c, path_c, still_th = trace_tree_paths(model, X_s2_14_20)
    log('aid1.0 seed-0 root splits: ' + str(root_c.most_common(10)))
    log('aid1.0 seed-0 path feature counts on old_14+old_20: ' + str(path_c.most_common(12)))

    plot_20_features_boxplots({
        'S1 A1 walker (0.15-0.25)': X_s1_slow_w,
        'S2 old_14/18/20 walker': X_s2_walkers,
        'Real WearGait SlowPace': X_wg_slow,
        'Caicedo 0.6 + AB07 0.5': np.vstack([X_caic_06, X_ab07_05]),
        'Real still': X_real_still,
    }, os.path.join(OUT_DIR, 'plot3_feature_boxplots.png'))

    # --- Part 4A: Forward swap test (Source 2 -> Source 1 steps, one at a time) ---
    rng = np.random.default_rng(42)
    bp_rough = butter(2, [2.0, 8.0], btype='band', fs=FS, output='sos')

    def eval_swap_on_s2(swap_name, transform_fn):
        res = {'swap': swap_name}
        for short, mid in (('old_14', 'old_14_your_protocol_early_wa'),
                           ('old_18', 'old_18_toe_touch_walker'),
                           ('old_20', 'old_20_static_spacer_partial'),
                           ('old_15', 'old_15_your_protocol_crutches')):
            d = s2_data[mid]['data']
            y_true = s2_data[mid]['y']
            mov = (d['true_lbl'] == 0)
            acc_mod = transform_fn(d['acc'].copy(), mov, d)
            X_mod, _ = features_from_acc50(acc_mod, lib)
            n_use = min(len(X_mod), len(y_true))
            pred, _ = predict_rule06(model, X_mod[:n_use])
            wa = (y_true[:n_use] == 0) if len(X_mod) == len(y_true) else np.ones(len(X_mod), bool)
            res[short] = round(100.0 * float((pred[wa] == 0).mean()), 1) if wa.any() else 0.0
        log(f'  Forward swap {swap_name:30s}: old_14={res["old_14"]:5.1f}%  old_18={res["old_18"]:5.1f}%  '
            f'old_20={res["old_20"]:5.1f}%  old_15={res["old_15"]:5.1f}%')
        return res

    def _add_noise(a, mov, d, sd=0.010):
        r = np.random.default_rng(101)
        return a + r.normal(0.0, sd, a.shape).astype(np.float32)

    def _add_rough(a, mov, d, sd=0.030):
        r = np.random.default_rng(202)
        nf = sosfilt(bp_rough, r.normal(0.0, sd, a.shape), axis=0)
        return a + (nf * mov[:, None]).astype(np.float32)

    def _add_noise_and_rough(a, mov, d):
        return _add_rough(_add_noise(a, mov, d, 0.010), mov, d, 0.030)

    def _rot_pitch(a, mov, d, pitch_deg=9.0):
        return AG._rotate_acc(a, 0.0, pitch_deg, 0.0).astype(np.float32)

    def _norm_static_grav(a, mov, d):
        st = ~mov
        if st.sum() >= 20:
            g_mag = float(np.mean(np.linalg.norm(a[st], axis=1)))
            if g_mag > 0.5:
                return (a / g_mag).astype(np.float32)
        return a

    def _remove_pauses(a, mov, d):
        return a[mov]

    def _scale_dyn(a, mov, d, k=1.5):
        st = ~mov
        g_vec = a[st].mean(0) if st.sum() >= 20 else np.array([0.0, 0.0, 1.0])
        return (g_vec[None, :] + k * (a - g_vec[None, :])).astype(np.float32)

    def _rough_and_pitch(a, mov, d):
        return _rot_pitch(_add_rough(a, mov, d, 0.030), mov, d, 9.0)

    def _noise_rough_pitch_nobias(a, mov, d):
        a1 = _norm_static_grav(a, mov, d)
        a2 = _add_noise_and_rough(a1, mov, d)
        return _rot_pitch(a2, mov, d, 9.0)

    m_ab07, _ = AG.CR.model_for('ab07')

    def _replay_q(a, mov, d):
        return AG.CR.replay(m_ab07, d['Q'], FS, sensors=('acc_imu',))['acc_imu'].astype(np.float32)

    fwd_rows = [
        eval_swap_on_s2('S0: baseline (Source 2)', lambda a, m, d: a),
        eval_swap_on_s2('S1: +0.010g white noise', _add_noise),
        eval_swap_on_s2('S2: +0.030g 2-8Hz roughness', _add_rough),
        eval_swap_on_s2('S3: +white noise + roughness', _add_noise_and_rough),
        eval_swap_on_s2('S4: +9 deg mount pitch', _rot_pitch),
        eval_swap_on_s2('S5: normalize static |g|=1', _norm_static_grav),
        eval_swap_on_s2('S6: remove pauses (continuous)', _remove_pauses),
        eval_swap_on_s2('S7: scale dyn acc x1.5', lambda a, m, d: _scale_dyn(a, m, d, 1.5)),
        eval_swap_on_s2('S7b: scale dyn acc x2.0', lambda a, m, d: _scale_dyn(a, m, d, 2.0)),
        eval_swap_on_s2('S8: +roughness +9deg pitch', _rough_and_pitch),
        eval_swap_on_s2('S9: noise+rough+pitch+norm|g|', _noise_rough_pitch_nobias),
        eval_swap_on_s2('S10: CR.replay(Q) (no bias/imp)', _replay_q),
    ]

    # --- Part 4B: Reverse swap test on Source 1 (regenerate 6 slow pick-up walker streams with strips) ---
    log('Running reverse swap test on Source 1 (3 Camargo subjects x 2 slow pick-up walker specs)...')
    root_cam = os.path.join(config.CACHE, 'aid', 'camargo')
    rev_people = ['ab06', 'ab08', 'ab10']
    rev_specs = AG.PERSONA_SPECS[:2]  # pick-up walker, band 0 (0.15-0.25), full & partial
    tpls = {p: AG.stride_template(root_cam, p, LOG_PATH) for p in rev_people}

    def run_s1_variant(name, add_white=True, add_rough=True, add_pitch=True, force_stride_pause=False):
        Xs_w = []
        for pi, person in enumerate(rev_people):
            tpl = tpls[person]
            for si, spec in enumerate(rev_specs):
                r = np.random.default_rng(700 + 100 * pi + si)
                aid, band, wb, step, pause, rest, turn = spec
                lo, hi = AG.BANDS[band]
                v_target = float(r.uniform(lo + 0.005, hi - 0.005))
                pause_target = float(np.clip(pause + r.normal(0, 0.03), 0.0, 0.45))
                Q, moving, edge, kin = AG._build_motion(tpl, spec, r, v_target, pause_target, rest, turn)
                rep = AG.CR.replay(tpl['m'], Q, AG.FS, sensors=('acc_imu', 'gyr_imu'))
                acc200 = AG.CR.scale_dynamic(rep['acc_imu'], rep['grav_acc_imu'], AG.WB_GAIN[wb])
                n50 = len(Q) // 4
                acc50 = AG.resample_poly(acc200, 1, 4, axis=0)[:n50].astype(np.float32)
                mov50 = moving[::4][:n50]
                Q50 = Q[::4][:n50]
                if add_white:
                    acc50 = acc50 + r.normal(0.0, 0.010, acc50.shape).astype(np.float32)
                if add_rough:
                    rf = sosfilt(bp_rough, r.normal(0.0, AG.ROUGH[aid], acc50.shape), axis=0)
                    acc50 = acc50 + (rf * mov50[:, None]).astype(np.float32)
                if add_pitch:
                    my = float(np.clip(r.normal(0, 7), -15, 15))
                    mp = float(np.clip(r.normal(9, 5), -12, 20))
                    mr = float(np.clip(r.normal(0, 4), -12, 12))
                    acc50 = AG._rotate_acc(acc50, my, mp, mr).astype(np.float32)
                if force_stride_pause:
                    # Insert 1.0 s static pause after every 1.6 s of walking (mimicking old_14 cadence)
                    chunks = []
                    st_val = np.array([0.0, 0.0, 1.0], np.float32)
                    i = 0
                    while i < len(acc50):
                        chunks.append(acc50[i:i + 80])
                        chunks.append(np.tile(st_val, (50, 1)))
                        i += 80
                    acc50 = np.vstack(chunks)
                    mov50 = np.ones(len(acc50), np.float32)
                X_v, _ = features_from_acc50(acc50, lib)
                pr, pl = AG._ankles(tpl['m'], Q50)
                contacts = np.sort(np.r_[AG._clean_contacts(pr, FS), AG._clean_contacts(pl, FS)])
                for wi, s in enumerate(range(0, len(acc50) - W + 1, H)):
                    if force_stride_pause:
                        Xs_w.append(X_v[wi])
                    else:
                        t0, t1 = s / FS, (s + W) / FS
                        nst = int(((contacts >= t0) & (contacts < t1)).sum())
                        if nst >= 2 and float(mov50[s:s + W].mean()) >= 0.5:
                            Xs_w.append(X_v[wi])
        X_all = np.asarray(Xs_w, np.float32)
        pred, _ = predict_rule06(model, X_all)
        rec = 100.0 * float((pred == 0).mean())
        med_hf = float(np.median(X_all[:, FEAT_NAMES.index('hf_ratio')]))
        med_stdm = float(np.median(X_all[:, FEAT_NAMES.index('std_m')]))
        med_jerk = float(np.median(X_all[:, FEAT_NAMES.index('jerk_m')]))
        log(f'  Reverse swap {name:30s}: walk_recall={rec:5.1f}% (n={len(X_all)}) | '
            f'med hf_ratio={med_hf:.4f}, std_m={med_stdm:.4f}, jerk_m={med_jerk:.4f}')
        return dict(swap=name, walk_recall_pct=round(rec, 1), n=len(X_all),
                    med_hf_ratio=round(med_hf, 4), med_std_m=round(med_stdm, 4), med_jerk_m=round(med_jerk, 4))

    rev_rows = [
        run_s1_variant('R0: full Source 1', True, True, True, False),
        run_s1_variant('R1: no 2-8Hz roughness', True, False, True, False),
        run_s1_variant('R2: no white noise', False, True, True, False),
        run_s1_variant('R3: no mount rotation', True, True, False, False),
        run_s1_variant('R4: no noise & no roughness', False, False, True, False),
        run_s1_variant('R5: clean replay (none)', False, False, False, False),
    ]

    plot_swap_results(fwd_rows, rev_rows, os.path.join(OUT_DIR, 'plot4_swap_test.png'))

    # Save full JSON summary
    summary = dict(
        version=VERSION,
        signal_stats=sig_stats,
        effect_sizes=effect_rows,
        root_splits=[{'feature': k[0], 'thresh': k[1], 'count': v} for k, v in root_c.most_common(12)],
        path_counts=dict(path_c.most_common(15)),
        forward_swaps=fwd_rows,
        reverse_swaps=rev_rows,
        wg_slow_recall_pct=round(100.0 * float((p_wg_slow == 0).mean()), 1),
    )
    with open(os.path.join(OUT_DIR, 'g3_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    log(f'Done! Saved summary and 4 plots under {OUT_DIR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
