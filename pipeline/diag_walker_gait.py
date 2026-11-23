"""
Task G2 (Step 1 of docs/PLAN_walker_gait.md): diagnose why walker / crutch gait
personas are classified as "still" by the V4 forest.
   diag_walker_gait 1.0, 23 Nov 2026

Analysis only: no model training, no change to existing code or results.
Outputs: cache/g2/ (log, JSON summary, and 3 diagnostic PNG plots).

Usage:
    python pipeline/diag_walker_gait.py
"""
import datetime
import json
import os
import sys
import time
from collections import Counter

import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_DIR = os.path.join(REPO_ROOT, 'pipeline')
VIEWER_DIR = os.path.join(REPO_ROOT, 'viewer')
for d in (PIPELINE_DIR, VIEWER_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import config
import camargo_replay as CR
import stage3 as S3
import kneil_viewer as KV

VERSION = 'diag_walker_gait 1.0'
OUT_DIR = os.path.join(config.CACHE, 'g2')
LOG_PATH = os.path.join(OUT_DIR, 'diag_walker_gait_log.txt')

FEAT_NAMES = [
    'mean_x', 'mean_y', 'mean_z', 'std_x', 'std_y', 'std_z', 'std_m', 'mean_m',
    'ptp_m', 'max_m', 'jerk_m', 'tilt_sag_deg', 'tilt_cor_deg', 'ac_m_05s',
    'ac_m_10s', 'zcr_z_hz', 'trend_x', 'trend_z', 'corr_xz', 'hf_ratio',
]
CLASSES8 = list(KV.CLASS_NAMES_V2)

PERSONA_IDS = [
    'old_14_your_protocol_early_wa',
    'old_15_your_protocol_crutches',
    'old_16_your_protocol_later_no',
    'old_17_partial_weight_bearing',
    'old_18_toe_touch_walker',
    'old_19_non_weight_bearing_wal',
    'old_20_static_spacer_partial',
    'old_21_static_spacer_as_toler',
]
CONTRAST_IDS = [
    'old_00_treadmill_walking_0_50',
    'old_06_older_adult_0_60_m_s_s',
]


def log(msg):
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def analyze_motion_kinematics(entry, data):
    """Compute speed, cadence, steps per 4 s window, pause share, and right-leg stance/swing."""
    meta = data['meta']
    Q = data['Q']
    t = data['t']
    dur = float(t[-1])
    fs = float(meta['fs'])

    # Ankle trajectories (both legs)
    pr, pl = KV._compute_ankle_trajs(Q, meta['geom'])

    # Pelvis horizontal speed (m/s)
    px, pz = Q[:, 0], Q[:, 2]
    vx = np.gradient(px, 1.0 / fs)
    vz = np.gradient(pz, 1.0 / fs)
    v_pel = np.hypot(vx, vz)

    # For treadmill (old_00), pelvis stays in place -> use relative speed over stance foot
    is_tm = (meta.get('env', {}).get('type') == 'treadmill')
    if is_tm:
        v_mean = float(meta['env'].get('v', 0.50))
        v_moving = v_mean
    else:
        v_mean = float(np.mean(v_pel))
        moving_mask = (data['true_lbl'] == 0)
        v_moving = float(np.mean(v_pel[moving_mask])) if moving_mask.sum() > 10 else v_mean

    # Pause share from embedded labels ('standing' -> v2 class 3) and from kinematics (v_pel < 0.05)
    pause_label_pct = 100.0 * float((data['true_lbl'] == 3).mean())
    pause_kin_pct = 0.0 if is_tm else 100.0 * float((v_pel < 0.05).mean())

    # Foot contacts of both legs (right = implant leg, left = contralateral)
    # Apply 0.45 s refractory period per leg to prevent double-counting ankle bounce
    def _clean_contacts(ankle_xyz):
        raw_ev = CR.foot_contacts(ankle_xyz, fs=fs, v_swing=-0.18, v_contact=-0.04)
        out = []
        for idx in raw_ev:
            t_ev = idx / fs
            if not out or (t_ev - out[-1]) >= 0.45:
                out.append(t_ev)
        return np.array(out, float)

    t_ev_r = _clean_contacts(pr)
    t_ev_l = _clean_contacts(pl)

    # Also cross-check HTML viewer embedded heel-strike timestamps (device leg) if available
    hs_html = []
    if entry['kind'] == 'old':
        tr = KV._load_old_html_trials()[entry['index']]
        hs_html = [float(x) for x in tr.get('hs', [])]

    # Prefer HTML hs for right leg when present (exact generator events), else ankle contacts
    t_hs_r = np.array(hs_html, float) if len(hs_html) > 0 else t_ev_r
    t_hs_l = t_ev_l
    t_steps_all = np.sort(np.concatenate([t_hs_r, t_hs_l]))

    # Cadence (steps/min, both legs)
    cadence_all = 60.0 * len(t_steps_all) / max(dur, 1e-6)
    moving_s = dur * (1.0 - pause_label_pct / 100.0)
    cadence_moving = 60.0 * len(t_steps_all) / max(moving_s, 1e-6) if moving_s > 0.5 else 0.0

    # Right-leg (implant) stance vs swing during moving samples
    vy_r = np.abs(np.gradient(pr[:, 1], 1.0 / fs))
    y_floor_r = float(np.percentile(pr[:, 1], 5))
    r_stance = (pr[:, 1] <= y_floor_r + 0.045) & (vy_r < 0.12)
    mov = (data['true_lbl'] == 0)
    if mov.sum() > 20:
        stance_r_pct = 100.0 * float(r_stance[mov].mean())
    else:
        stance_r_pct = 100.0 * float(r_stance.mean())
    swing_r_pct = 100.0 - stance_r_pct

    # Per 4 s window (1 s hop, matching V4)
    wt = data['win_t']
    steps_per_win = []
    r_steps_per_win = []
    walk_share_per_win = []
    for te in wt:
        ts0 = float(te) - 4.0
        n_all = int(((t_steps_all >= ts0) & (t_steps_all < te)).sum())
        n_r = int(((t_hs_r >= ts0) & (t_hs_r < te)).sum())
        i0 = max(0, int(round(ts0 * fs)))
        i1 = min(len(data['true_lbl']), int(round(float(te) * fs)))
        wshare = float((data['true_lbl'][i0:i1] == 0).mean()) if i1 > i0 else 0.0
        steps_per_win.append(n_all)
        r_steps_per_win.append(n_r)
        walk_share_per_win.append(wshare)

    return dict(
        id=entry['id'], name=meta['name'], dur=round(dur, 1),
        v_mean=round(v_mean, 3), v_moving=round(v_moving, 3),
        pause_label_pct=round(pause_label_pct, 1), pause_kin_pct=round(pause_kin_pct, 1),
        n_hs_r=int(len(t_hs_r)), n_hs_l=int(len(t_hs_l)),
        cadence_all=round(cadence_all, 1), cadence_moving=round(cadence_moving, 1),
        stance_r_pct=round(stance_r_pct, 1), swing_r_pct=round(swing_r_pct, 1),
        n_windows=len(wt),
        steps_win_mean=round(float(np.mean(steps_per_win)), 2) if steps_per_win else 0.0,
        steps_win_min=int(np.min(steps_per_win)) if steps_per_win else 0,
        steps_win_max=int(np.max(steps_per_win)) if steps_per_win else 0,
        steps_per_win=steps_per_win,
        r_steps_per_win=r_steps_per_win,
        walk_share_per_win=walk_share_per_win,
    )


def compute_chip_features(acc_50hz):
    """Exact 20 chip features per 4 s window (1 s hop) after 6 Hz causal low-pass."""
    b = S3.T.apply_lowpass(np.asarray(acc_50hz, np.float64), 50.0, 6.0).astype(np.float32)
    Wn = 200
    X = np.array(
        [S3.T.features(S3.T_lib(), b[s:s + Wn, 0], b[s:s + Wn, 1], b[s:s + Wn, 2], 50.0)
         for s in range(0, len(b) - Wn + 1, 50)],
        dtype=np.float32,
    ).reshape(-1, 20)
    return X


def tree_decision_analysis(model, X_walker_still):
    """Inspect decision paths of the 20 trees on walker windows predicted as 'still'.
    Returns counts of (feature_name, threshold, direction) on paths leading to leaf class STILL (3)."""
    feat_counts = Counter()
    split_details = Counter()
    root_splits = Counter()
    for est in model.estimators_:
        tree = est.tree_
        root_f = int(tree.feature[0])
        root_t = round(float(tree.threshold[0]), 3)
        root_splits[(FEAT_NAMES[root_f], root_t)] += 1

        node_indicator = est.decision_path(X_walker_still)
        preds = est.predict(X_walker_still).astype(int)
        for i in range(len(X_walker_still)):
            if preds[i] != 3:  # only trace trees voting STILL
                continue
            nodes = node_indicator.indices[node_indicator.indptr[i]:node_indicator.indptr[i + 1]]
            for nid in nodes[:-1]:  # exclude leaf
                f = int(tree.feature[nid])
                thr = float(tree.threshold[nid])
                val = float(X_walker_still[i, f])
                side = '<=' if val <= thr else '>'
                feat_counts[FEAT_NAMES[f]] += 1
                split_details[(FEAT_NAMES[f], side, round(thr, 3))] += 1
    return feat_counts, split_details, root_splits


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    log(f'{VERSION} | {config.VERSION} | {datetime.datetime.now().isoformat(timespec="seconds")}')

    catalog = KV.build_catalog()
    model_path = os.path.join(config.V4_OUT, 'tinyml_final_v4_lp6', 'model_forest.joblib')
    model = joblib.load(model_path)
    log(f'Loaded V4 forest: {model_path} ({len(model.estimators_)} trees)')

    # Load real still windows from windows_W4s.npz (real datasets, y in {3, 4} -> 8-class still)
    wpath = os.path.join(config.V4_OUT, 'stepD', 'windows_v11', 'windows_W4s.npz')
    Z = np.load(wpath, allow_pickle=True)
    m_real_still = (Z['src'] == 'real') & np.isin(Z['y'], [3, 4])
    X_real_still = Z['X'][m_real_still].astype(np.float32)
    m_real_walk = (Z['src'] == 'real') & (Z['y'] == 0)
    X_real_walk = Z['X'][m_real_walk].astype(np.float32)
    log(f'Loaded windows_W4s.npz: real still={len(X_real_still)}, real walking={len(X_real_walk)}')

    # Analyze all 8 personas + 2 slow healthy walking contrasts
    results = {}
    X_by_id = {}
    votes_by_id = {}
    for mid in PERSONA_IDS + CONTRAST_IDS:
        entry = KV.resolve_motion_id(mid, catalog)
        data = KV.load_motion(entry)
        kin = analyze_motion_kinematics(entry, data)
        X = compute_chip_features(data['acc'])
        # Per-tree votes (20 trees)
        tpreds = np.column_stack([est.predict(X).astype(int) for est in model.estimators_])
        votes = np.zeros((len(X), 8), dtype=int)
        for c in range(8):
            votes[:, c] = (tpreds == c).sum(axis=1)
        mean_votes = votes.mean(axis=0)
        rc = data['rule_cls']
        still_pct = 100.0 * float((rc == 3).mean()) if len(rc) else 0.0
        walk_pct = 100.0 * float((rc == 0).mean()) if len(rc) else 0.0

        # Candidate label rules (for 4 s windows)
        spw = np.array(kin['steps_per_win'])
        wsh = np.array(kin['walk_share_per_win'])
        n_w = len(spw)
        r_a = int((spw >= 1).sum())                         # Rule A: >= 1 step in 4 s window
        r_b = int((spw >= 2).sum())                         # Rule B: >= 2 steps (1 stride) in 4 s window
        r_c = int(((spw >= 2) & (wsh >= 0.50)).sum())       # Rule C: >= 2 steps AND >= 50% moving
        r_lbl50 = int((wsh >= 0.50).sum())                  # HTML label majority (>= 50% walking)
        r_lbl60 = int((wsh >= 0.60).sum())                  # stage3_v4 default (min_share = 60%)

        kin.update(
            v4_still_pct=round(still_pct, 1),
            v4_walk_pct=round(walk_pct, 1),
            mean_votes={CLASSES8[c]: round(float(mean_votes[c]), 2) for c in range(8) if mean_votes[c] >= 0.05},
            rule_A_walk=r_a, rule_B_walk=r_b, rule_C_walk=r_c,
            lbl50_walk=r_lbl50, lbl60_walk=r_lbl60,
        )
        results[mid] = kin
        X_by_id[mid] = X
        votes_by_id[mid] = votes

    # Print Motion & Vote summary table
    log('\n=== 1. MOTIONS & V4 DECISIONS ===')
    log(f'{"ID":30s} | {"v_avg":5s} | {"v_mov":5s} | {"pause":5s} | {"cad":5s} | {"stp/4s":6s} | {"stR%":4s} | {"V4 still":8s} | {"V4 walk":7s} | Mean votes (of 20)')
    for mid in PERSONA_IDS + CONTRAST_IDS:
        r = results[mid]
        vstr = ', '.join(f'{k}:{v:.1f}' for k, v in sorted(r['mean_votes'].items(), key=lambda kv: -kv[1])[:3])
        log(f'{mid:30s} | {r["v_mean"]:5.2f} | {r["v_moving"]:5.2f} | {r["pause_label_pct"]:4.0f}% | '
            f'{r["cadence_all"]:5.1f} | {r["steps_win_mean"]:6.2f} | {r["stance_r_pct"]:4.0f} | '
            f'{r["v4_still_pct"]:7.1f}% | {r["v4_walk_pct"]:6.1f}% | {vstr}')

    # Print Label Rule table
    log('\n=== 4. CANDIDATE LABEL RULES (walking windows / total windows) ===')
    log(f'{"ID":30s} | {"Win":3s} | {"lbl>=60%":8s} | {"lbl>=50%":8s} | {"Rule A (>=1st)":14s} | {"Rule B (>=2st)":14s} | {"Rule C (>=2st&50%)":18s}')
    for mid in PERSONA_IDS:
        r = results[mid]
        nw = r['n_windows']
        log(f'{mid:30s} | {nw:3d} | {r["lbl60_walk"]:2d}/{nw:<2d}    | {r["lbl50_walk"]:2d}/{nw:<2d}    | '
            f'{r["rule_A_walk"]:2d}/{nw:<2d} ({100*r["rule_A_walk"]/nw:4.0f}%)  | '
            f'{r["rule_B_walk"]:2d}/{nw:<2d} ({100*r["rule_B_walk"]/nw:4.0f}%)  | '
            f'{r["rule_C_walk"]:2d}/{nw:<2d} ({100*r["rule_C_walk"]/nw:4.0f}%)')

    # Group features: Walker (called still), Crutches/No-aid (called walking), Slow healthy, Real still
    walker_ids = [
        'old_14_your_protocol_early_wa', 'old_18_toe_touch_walker',
        'old_19_non_weight_bearing_wal', 'old_20_static_spacer_partial',
    ]
    crutch_ids = [
        'old_15_your_protocol_crutches', 'old_16_your_protocol_later_no',
        'old_17_partial_weight_bearing', 'old_21_static_spacer_as_toler',
    ]
    X_walker = np.vstack([X_by_id[m] for m in walker_ids])
    X_crutch = np.vstack([X_by_id[m] for m in crutch_ids])
    X_slow = np.vstack([X_by_id[m] for m in CONTRAST_IDS])

    # Tree decision-path analysis on walker windows predicted STILL
    feat_counts, split_details, root_splits = tree_decision_analysis(model, X_walker)
    log('\n=== 2. TREE DECISION PATHS ON WALKER WINDOWS (N=%d) ===' % len(X_walker))
    log('Root splits across 20 trees: ' + str(root_splits.most_common(6)))
    log('Top 10 features on STILL decision paths: ' + str(feat_counts.most_common(10)))
    log('Top 12 (feature, side, threshold) splits: ' + str(split_details.most_common(12)))

    # Feature comparison table (median [IQR] across 4 groups)
    log('\n=== 2b. FEATURE MEDIANS: Real Still vs Walker vs Crutches vs Slow Healthy ===')
    log(f'{"Feature":14s} | {"Real Still":14s} | {"Walker (still)":14s} | {"Crutch (walk)":14s} | {"Slow Walk":14s} | {"Real Walk":14s} | TreePath#')
    feat_table = []
    for fi, fn in enumerate(FEAT_NAMES):
        ms = float(np.median(X_real_still[:, fi]))
        mw = float(np.median(X_walker[:, fi]))
        mc = float(np.median(X_crutch[:, fi]))
        msl = float(np.median(X_slow[:, fi]))
        mrw = float(np.median(X_real_walk[:, fi]))
        cnt = int(feat_counts.get(fn, 0))
        log(f'{fn:14s} | {ms:14.4f} | {mw:14.4f} | {mc:14.4f} | {msl:14.4f} | {mrw:14.4f} | {cnt:9d}')
        feat_table.append(dict(
            feature=fn, real_still=round(ms, 4), walker=round(mw, 4),
            crutch=round(mc, 4), slow_walk=round(msl, 4), real_walk=round(mrw, 4),
            still_path_count=cnt,
        ))

    # ------------------------------------------------------------------ PLOTS
    rng = np.random.default_rng(0)
    idx_rs = rng.choice(len(X_real_still), min(2500, len(X_real_still)), replace=False)
    idx_rw = rng.choice(len(X_real_walk), min(2500, len(X_real_walk)), replace=False)
    X_rs_sub = X_real_still[idx_rs]
    X_rw_sub = X_real_walk[idx_rw]

    # Plot 1: 2D scatter of std_m vs ptp_m (and std_x vs jerk_m) with forest split thresholds
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.5), dpi=130)
    pairs = [
        ('std_m', 'ptp_m', 'Magnitude std (std_m, g)', 'Magnitude peak-to-peak (ptp_m, g)'),
        ('jerk_m', 'std_x', 'Magnitude jerk (jerk_m, g/s)', 'Anterior std (std_x, g)'),
    ]
    for ax, (f1, f2, l1, l2) in zip(axes, pairs):
        i1, i2 = FEAT_NAMES.index(f1), FEAT_NAMES.index(f2)
        ax.scatter(X_rs_sub[:, i1], X_rs_sub[:, i2], s=8, alpha=0.22, color='#2166d6', label=f'Real still (n={len(X_rs_sub)})')
        ax.scatter(X_rw_sub[:, i1], X_rw_sub[:, i2], s=8, alpha=0.14, color='#a1d99b', label=f'Real walking (n={len(X_rw_sub)})')
        ax.scatter(X_slow[:, i1], X_slow[:, i2], s=42, marker='^', color='#2e9e44', edgecolor='k', lw=0.5, label=f'Slow healthy 0.5-0.6 m/s (n={len(X_slow)})')
        ax.scatter(X_crutch[:, i1], X_crutch[:, i2], s=36, marker='s', color='#ff9a1f', edgecolor='k', lw=0.4, label=f'Crutch / no-aid personas (n={len(X_crutch)})')
        ax.scatter(X_walker[:, i1], X_walker[:, i2], s=42, marker='o', color='#d62728', edgecolor='k', lw=0.5, label=f'Walker personas (called still, n={len(X_walker)})')
        # Overlay most common forest split thresholds for f1 / f2
        for (fn, side, thr), cnt in split_details.most_common(12):
            if fn == f1 and cnt >= 200:
                ax.axvline(thr, color='#444444', ls='--', lw=1.1, alpha=0.75)
                ax.text(thr, ax.get_ylim()[1] * 0.92, f' {f1}<={thr:.3f}', fontsize=8, color='#222222')
                break
        for (fn, side, thr), cnt in split_details.most_common(12):
            if fn == f2 and cnt >= 200:
                ax.axhline(thr, color='#444444', ls=':', lw=1.1, alpha=0.75)
                break
        ax.set_xlabel(l1, fontsize=10)
        ax.set_ylabel(l2, fontsize=10)
        ax.set_xlim(left=-0.01, right=np.percentile(X_rw_sub[:, i1], 95))
        ax.set_ylim(bottom=-0.02, top=np.percentile(X_rw_sub[:, i2], 95))
        ax.grid(True, alpha=0.25)
    axes[0].legend(loc='upper left', fontsize=8.5, frameon=True)
    fig.suptitle('G2 Plot 1: Walker persona windows vs Real still and Slow walking (decisive V4 features)', fontsize=12, fontweight='bold')
    fig.tight_layout()
    p1 = os.path.join(OUT_DIR, 'plot1_feature_scatter.png')
    fig.savefig(p1, dpi=130)
    plt.close(fig)

    # Plot 2: Boxplots of top 6 separating features across the 4 groups
    top6 = ['std_m', 'ptp_m', 'jerk_m', 'std_x', 'std_z', 'max_m']
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.2), dpi=130)
    groups_data = [
        ('Real\nstill', X_rs_sub, '#2166d6'),
        ('Walker\n(0.3 m/s)', X_walker, '#d62728'),
        ('Crutch\n(0.5 m/s)', X_crutch, '#ff9a1f'),
        ('Slow\n0.5-0.6', X_slow, '#2e9e44'),
        ('Real\nwalk', X_rw_sub, '#74c476'),
    ]
    for ax, fn in zip(axes.ravel(), top6):
        fi = FEAT_NAMES.index(fn)
        vals = [g[1][:, fi] for g in groups_data]
        bp = ax.boxplot(vals, tick_labels=[g[0] for g in groups_data], showfliers=False, patch_artist=True,
                        medianprops=dict(color='black', lw=1.6))
        for patch, (_, _, col) in zip(bp['boxes'], groups_data):
            patch.set_facecolor(col)
            patch.set_alpha(0.65)
        ax.set_title(fn, fontsize=11, fontweight='bold')
        ax.grid(True, axis='y', alpha=0.25)
        ax.tick_params(labelsize=8.5)
    fig.suptitle('G2 Plot 2: Top 6 movement-intensity features — walker personas sit well above real still, below slow walking', fontsize=11.5, fontweight='bold')
    fig.tight_layout()
    p2 = os.path.join(OUT_DIR, 'plot2_feature_profiles.png')
    fig.savefig(p2, dpi=130)
    plt.close(fig)

    # Plot 3: Per-persona V4 forest vote share (still vs walking) + candidate label rule shares
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.4), dpi=130)
    short_names = [
        '14: early walker', '15: crutches', '16: later no-aid', '17: PWB crutches',
        '18: toe-touch walker', '19: NWB walker', '20: static walker', '21: static crutches',
    ]
    y_pos = np.arange(len(PERSONA_IDS))
    v_still = [results[m]['mean_votes'].get('still', 0.0) / 20.0 * 100.0 for m in PERSONA_IDS]
    v_walk = [results[m]['mean_votes'].get('walking', 0.0) / 20.0 * 100.0 for m in PERSONA_IDS]
    v_other = [max(0.0, 100.0 - s - w) for s, w in zip(v_still, v_walk)]

    ax1.barh(y_pos, v_still, color='#2166d6', label='V4 vote: still')
    ax1.barh(y_pos, v_walk, left=v_still, color='#2e9e44', label='V4 vote: walking')
    ax1.barh(y_pos, v_other, left=np.array(v_still) + np.array(v_walk), color='#bbbbbb', label='V4 vote: other')
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(short_names, fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlim(0, 100)
    ax1.set_xlabel('Mean tree vote share (%) across 20 trees', fontsize=9.5)
    ax1.set_title('V4 Forest Votes per Persona', fontsize=11, fontweight='bold')
    ax1.legend(loc='upper center', bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8.5, frameon=True)
    ax1.grid(True, axis='x', alpha=0.25)

    w = 0.25
    ra_pct = [100.0 * results[m]['rule_A_walk'] / results[m]['n_windows'] for m in PERSONA_IDS]
    rb_pct = [100.0 * results[m]['rule_B_walk'] / results[m]['n_windows'] for m in PERSONA_IDS]
    rc_pct = [100.0 * results[m]['rule_C_walk'] / results[m]['n_windows'] for m in PERSONA_IDS]
    ax2.barh(y_pos - w, ra_pct, height=w, color='#1b9e77', label='Rule A: >=1 step in 4 s')
    ax2.barh(y_pos, rb_pct, height=w, color='#d95f02', label='Rule B: >=2 steps in 4 s')
    ax2.barh(y_pos + w, rc_pct, height=w, color='#7570b3', label='Rule C: >=2 steps & >=50% moving')
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(['' for _ in short_names])
    ax2.invert_yaxis()
    ax2.set_xlim(0, 105)
    ax2.set_xlabel('Windows labelled "walking" (%)', fontsize=9.5)
    ax2.set_title('Candidate Label Rules on the 8 Personas', fontsize=11, fontweight='bold')
    ax2.legend(loc='upper center', bbox_to_anchor=(0.5, -0.14), ncol=2, fontsize=8.5, frameon=True)
    ax2.grid(True, axis='x', alpha=0.25)
    fig.suptitle('G2 Plot 3: V4 forest decisions vs candidate walking-with-aid label rules', fontsize=12, fontweight='bold')
    fig.subplots_adjust(bottom=0.22, top=0.88, left=0.16, right=0.98, wspace=0.08)
    p3 = os.path.join(OUT_DIR, 'plot3_persona_votes_and_rules.png')
    fig.savefig(p3, dpi=130)
    plt.close(fig)

    summary = dict(
        version=VERSION,
        motions=results,
        feature_medians=feat_table,
        root_splits=[[list(k), v] for k, v in root_splits.most_common(10)],
        top_still_path_features=feat_counts.most_common(10),
        top_still_splits=[[list(k), v] for k, v in split_details.most_common(15)],
        plots=[p1, p2, p3],
    )
    jpath = os.path.join(OUT_DIR, 'g2_summary.json')
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    log(f'Saved summary JSON -> {jpath}')
    log(f'Saved 3 plots -> {p1}, {p2}, {p3}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
