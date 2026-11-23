"""
KNEIL A1 part B: the aid-gait cross-validation experiment.   cv_aid 1.0, 23 Nov 2026

5-fold cross-validation by source person (each aid persona folds with its Camargo person), 3 seeds, 4 s
windows, 1 s hop, 8 classes, the chip's stairs rule (vote >= 0.60). Variants: V4half (today) and V4half +
the step-F aid-gait personas at weight 0.25 / 0.5 / 1.0 (weight = per-window sample weight, as the simulated
rows have 1.0).

Metrics: aid walking recall (held-out) by aid, speed band and steps/window; the 8 viewer personas labelled by
rule C (external); real still called walking and still precision; walking recall per real dataset; walking
called stairs; Luo/PAMAP2 stairs; simulated transition events and false events per hour (transition_events.py);
model size. Outputs under config.out_dir('stepF', 'cv_aid').

CLI:
  python pipeline/cv_aid.py --seeds 0 --variants V4half
  python pipeline/cv_aid.py
"""
import argparse
import os
import sys
import time
from collections import Counter

import numpy as np
import pandas as pd

import config
import cv_v4 as C
import stage01 as S1
import stage3 as S3
import transition_events as TE
import camargo_replay as CR

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'viewer'))
import kneil_viewer as KV

VERSION = 'cv_aid 1.0'
WIN = 4
CLASSES8 = C.CLASSES8
VARIANTS = ('V4half', 'aid0.25', 'aid0.5', 'aid1.0')
AID_W = {'V4half': 0.0, 'aid0.25': 0.25, 'aid0.5': 0.5, 'aid1.0': 1.0}
THETA = 0.60
HOLDOUT = set()          # source people not used for training (AB07 for the independent viewer test)
FEAT_NAMES = ['mean_x', 'mean_y', 'mean_z', 'std_x', 'std_y', 'std_z', 'std_m', 'mean_m',
              'ptp_m', 'max_m', 'jerk_m', 'tilt_sag_deg', 'tilt_cor_deg', 'ac_m_05s',
              'ac_m_10s', 'zcr_z_hz', 'trend_x', 'trend_z', 'corr_xz', 'hf_ratio']
G2_CUTOFF = {'ptp_m': 0.315, 'jerk_m': 0.731, 'std_m': 0.062, 'mean_m': 1.015}
VIEWER_IDS = ['old_14_your_protocol_early_wa', 'old_15_your_protocol_crutches',
              'old_16_your_protocol_later_no', 'old_17_partial_weight_bearing',
              'old_18_toe_touch_walker', 'old_19_non_weight_bearing_wal',
              'old_20_static_spacer_partial', 'old_21_static_spacer_as_toler']


def log_msg(msg, path):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def rule06(pred, proba):
    """The chip's stairs evidence rule: stairs stay only with a vote share >= 0.60; else walking."""
    out = np.asarray(pred).copy()
    p = np.asarray(proba)
    pa = np.zeros(len(out), np.float32)
    ok = out >= 0
    pa[ok] = p[np.flatnonzero(ok), out[ok]]
    stair = np.isin(out, (1, 2))
    out[stair & (pa < THETA)] = 0
    return out


def load_base(win, base_v4):
    """The real V4 window cache (input) is independent of KNEIL_V4_OUT, which may point at a test folder."""
    p = os.path.join(base_v4, 'stepD', 'windows_v11', f'windows_W{win:g}s.npz')
    if not os.path.exists(p):
        raise FileNotFoundError(f'{p}: run pipeline/stage3_v4.py first')
    Z = np.load(p, allow_pickle=True)
    return {k: Z[k] for k in Z.files if k in C.COLS}


def fold_map(win2, base_v4):
    A2 = load_base(win2, base_v4)
    return S3.assign_folds(A2)[1]


def load_aid(name):
    p = os.path.join(config.out_dir('stepF', name), 'aid_windows_W4s.npz')
    if not os.path.exists(p):
        raise FileNotFoundError(f'{p}: run pipeline/aid_gait.py first')
    Z = np.load(p, allow_pickle=True)
    return {k: Z[k] for k in Z.files}


def aid_folds(aid, gf):
    f = np.array([gf.get(str(g), -1) for g in aid['grp']], int)
    miss = int((f < 0).sum())
    if miss:
        raise RuntimeError(f'{miss} aid rows have no fold (source person missing from windows_W4s.npz)')
    return f


def fit_variant(A, aid, fold, fold_aid, variant, seed, y, k=None, final=False):
    """Train one forest on the training folds (or all rows when final); returns the model."""
    base_mask = np.ones(len(A['y']), bool) if final else (fold != k)
    if HOLDOUT:
        base_mask &= ~np.isin(A['grp'].astype(str), list(HOLDOUT))
    Xb, yb, wb = C.training_set_v4(A, base_mask, 'V4half', y)
    Xs, ys, ws = [Xb], [yb], [wb]
    w = AID_W[variant]
    if w > 0:
        m = aid['usable'].astype(bool) & (np.ones(len(aid['y']), bool) if final else (fold_aid != k))
        if m.any():
            Xs.append(aid['X'][m].astype(np.float32))
            ys.append(aid['y'][m].astype(int))
            ws.append(np.full(int(m.sum()), w, np.float64))
    m = S3.make_model('forest 20x d10')
    m.set_params(random_state=seed)
    m.fit(np.vstack(Xs), np.concatenate(ys).astype(int), sample_weight=np.concatenate(ws))
    assert np.array_equal(np.asarray(m.classes_, int), np.arange(8))
    return m


def run_one(A, aid, fold, fold_aid, y, variant, seed, pred_dir, log):
    path = os.path.join(pred_dir, f'pred_{variant}_W{WIN}s_8cls_seed{seed}.npz')
    if os.path.exists(path):
        log(f'  {variant} seed {seed}: loading {os.path.basename(path)}')
        Z = np.load(path)
        return dict(pred=Z['pred'], proba=Z['proba'], pred_aid=Z['pred_aid'],
                    proba_aid=Z['proba_aid'], nodes=int(Z['nodes']))
    pred = np.full(len(A['y']), -2, np.int8)
    proba = np.zeros((len(A['y']), 8), np.float16)
    pred_aid = np.full(len(aid['y']), -2, np.int8)
    proba_aid = np.zeros((len(aid['y']), 8), np.float16)
    nodes = -1
    t0 = time.time()
    for k in range(C.K):
        m = fit_variant(A, aid, fold, fold_aid, variant, seed, y, k=k)
        if k == 0:
            nodes = int(S3.T.n_nodes(m))
        te = fold == k
        p = m.predict_proba(A['X'][te])
        proba[te] = p.astype(np.float16)
        pred[te] = np.argmax(p, axis=1).astype(np.int8)
        ta = (fold_aid == k) & aid['usable'].astype(bool)
        if ta.any():
            pa = m.predict_proba(aid['X'][ta].astype(np.float32))
            proba_aid[ta] = pa.astype(np.float16)
            pred_aid[ta] = np.argmax(pa, axis=1).astype(np.int8)
        log(f'  {variant} seed {seed} fold {k + 1}/{C.K}: {len(p)} base + {int(ta.sum())} aid test '
            f'({time.time() - t0:.0f} s)')
    np.savez_compressed(path, pred=pred, proba=proba, pred_aid=pred_aid, proba_aid=proba_aid,
                        fold=fold.astype(np.int8), fold_aid=fold_aid.astype(np.int8), nodes=np.int64(nodes),
                        variant=variant, seed=np.int64(seed), win=np.float64(WIN))
    log(f'  {variant} seed {seed}: done in {(time.time() - t0) / 60:.1f} min -> {path}')
    return dict(pred=pred, proba=proba, pred_aid=pred_aid, proba_aid=proba_aid, nodes=nodes)


def base_metrics(A, y, pred, pred_aid, variant, seed, y_aid, times):
    """Rows of the base-data metrics after the stairs rule; returns (rows, still_overall, aid_overall)."""
    rows = []
    ds, src = A['ds'], A['src']

    def add(table, dataset, key, metric, value, n):
        if (n or metric == 'false_per_hour') and np.isfinite(value):
            rows.append(dict(variant=variant, seed=seed, table=table, dataset=dataset, key=str(key),
                             metric=metric, value=float(value), n=int(n)))

    for d in sorted(set(ds[src == 'real'])):
        m = (src == 'real') & (ds == d) & (y == 0)
        if m.any():
            add('walking', d, 'walking', 'recall_pct', 100.0 * float((pred[m] == 0).mean()), int(m.sum()))
    # walking called stairs on the three requested sets
    called = (y == 0) & np.isin(pred, (1, 2))
    m = (ds == 'WearGait-PD') & (A['rec'] == 'HurriedPace') & (y == 0)
    if m.any():
        add('called', 'WearGait-PD', 'HurriedPace', 'walking_called_stairs_pct',
            100.0 * float(called[m].mean()), int(m.sum()))
    m = (ds == 'Lencioni') & (A['speed_abs'] == 'fast') & (y == 0)
    if m.any():
        add('called', 'Lencioni', 'fast', 'walking_called_stairs_pct', 100.0 * float(called[m].mean()), int(m.sum()))
    m = (ds == 'Luo') & (A['surface'] == 'FE') & (y == 0)
    if m.any():
        add('called', 'Luo', 'FE', 'walking_called_stairs_pct', 100.0 * float(called[m].mean()), int(m.sum()))
    # stairs recall / precision
    for d in ('Luo', 'PAMAP2'):
        for c in (1, 2):
            m = (ds == d) & (y == c)
            if m.any():
                add('stairs', d, CLASSES8[c], 'recall_pct', 100.0 * float((pred[m] == c).mean()), int(m.sum()))
            m = (ds == d) & (pred == c)
            if m.any():
                add('stairs', d, CLASSES8[c], 'precision_pct', 100.0 * float((y[m] == c).mean()), int(m.sum()))
    # real still cost: still -> walking, and still precision, per dataset
    for d in sorted(set(ds[src == 'real'])):
        st = (src == 'real') & (ds == d) & (y == 3)
        if st.any():
            add('still', d, 'still', 'called_walking_pct', 100.0 * float((pred[st] == 0).mean()), int(st.sum()))
        pm = (src == 'real') & (ds == d) & (pred == 3)
        if pm.any():
            add('still', d, 'still', 'precision_pct', 100.0 * float((y[pm] == 3).mean()), int(pm.sum()))
    real_still = (src == 'real') & (y == 3)
    still_overall = 100.0 * float((pred[real_still] == 0).mean()) if real_still.any() else np.nan
    pm = (src == 'real') & (pred == 3)
    still_prec = 100.0 * float((y[pm] == 3).mean()) if pm.any() else np.nan
    add('still', 'real', 'all', 'called_walking_pct', still_overall, int(real_still.sum()))
    add('still', 'real', 'all', 'still_precision_pct', still_prec, int(pm.sum()))
    # transition events on the simulated streams (R1, after the stairs rule)
    ev = TE.evaluate(A, pred, WIN, 'R1', times)['simulation']
    add('events', 'simulation', 'both', 'event_recall_pct',
        100.0 * ev['matched'] / ev['n_true'] if ev['n_true'] else np.nan, ev['n_true'])
    fe = TE.false_events(A, pred, WIN, 'R1', times)
    add('events', 'Camargo', 'no transition', 'false_per_hour', fe['Camargo (no transition)']['per_hour'],
        fe['Camargo (no transition)']['events'])
    # aid metrics (held-out, CV)
    h = np.flatnonzero(pred_aid >= 0)
    if len(h):
        wa = (y_aid[h] == 0)
        aid_overall = 100.0 * float((pred_aid[h][wa] == 0).mean()) if wa.any() else np.nan
        if wa.any():
            add('aid', 'all', 'walking', 'recall_pct', aid_overall, int(wa.sum()))
        st_aid = (y_aid[h] == 3)
        if st_aid.any():
            add('aid', 'all', 'still', 'called_walking_pct',
                100.0 * float((pred_aid[h][st_aid] == 0).mean()), int(st_aid.sum()))
        for key in sorted(set(AID_META['aid'][h])):
            m = wa & (AID_META['aid'][h] == key)
            if m.any():
                add('aid_aid', key, 'walking', 'recall_pct', 100.0 * float((pred_aid[h][m] == 0).mean()),
                    int(m.sum()))
        for key in sorted(set(AID_META['speed_band'][h])):
            m = wa & (AID_META['speed_band'][h] == key)
            if m.any():
                add('aid_band', key, 'walking', 'recall_pct', 100.0 * float((pred_aid[h][m] == 0).mean()),
                    int(m.sum()))
        st = AID_META['steps'][h]
        for lo, hi, name in ((0, 0, '0'), (1, 1, '1'), (2, 2, '2'), (3, 3, '3'), (4, 999, '4+')):
            m = wa & (st >= lo) & (st <= hi)
            if m.any():
                add('aid_steps', name, 'walking', 'recall_pct', 100.0 * float((pred_aid[h][m] == 0).mean()),
                    int(m.sum()))
    else:
        aid_overall = np.nan
    return rows, still_overall, aid_overall


def chip_features(acc50):
    b = S3.T.apply_lowpass(np.asarray(acc50, np.float64), 50.0, 6.0).astype(np.float32)
    Wn = int(4 * 50)
    X = [S3.T.features(S3.T_lib(), b[s:s + Wn, 0], b[s:s + Wn, 1], b[s:s + Wn, 2], 50.0)
         for s in range(0, len(b) - Wn + 1, 50)]
    return np.asarray(X, np.float32).reshape(-1, 20)


def viewer_rule_c(entry, data, cache_dir):
    """4 s windows of one viewer persona, labelled by rule C from the generated foot contacts."""
    Q, true = data['Q'], data['true_lbl']
    pr, pl = KV._compute_ankle_trajs(Q, data['meta']['geom'])
    tr = KV._load_old_html_trials()[entry['index']]
    hs = np.array([float(x) for x in tr.get('hs', [])], float)

    def clean(a):
        raw = CR.foot_contacts(a, fs=50.0, v_swing=-0.18, v_contact=-0.04)
        out = []
        for i in raw:
            t = i / 50.0
            if not out or t - out[-1] >= 0.45:
                out.append(t)
        return np.array(out, float)

    cr = hs if len(hs) else clean(pr)
    cl = clean(pl)
    contacts = np.sort(np.r_[cr, cl])
    X = chip_features(data['acc'])
    y, steps, share = [], [], []
    for te in data['win_t']:
        t0 = float(te) - 4.0
        n = int(((contacts >= t0) & (contacts < te)).sum())
        i0, i1 = max(0, int(round(t0 * 50))), min(len(true), int(round(float(te) * 50)))
        sh = float((true[i0:i1] == 0).mean()) if i1 > i0 else 0.0
        y.append(0 if (n >= 2 and sh >= 0.5) else 3)
        steps.append(n); share.append(sh)
    if len(X) != len(y):
        raise RuntimeError(f'{entry["id"]}: {len(X)} feature windows vs {len(y)} label windows')
    return X, np.asarray(y, np.int16), np.asarray(steps, np.int16), np.asarray(share, np.float32)


def external_set(out_dir, log):
    p = os.path.join(out_dir, 'external_viewer_W4s.npz')
    if os.path.exists(p):
        Z = np.load(p, allow_pickle=True)
        return {k: Z[k] for k in Z.files}
    catalog = KV.build_catalog()
    Xs, ys, ss, shs, names = [], [], [], [], []
    for mid in VIEWER_IDS:
        entry = KV.resolve_motion_id(mid, catalog)
        data = KV.load_motion(entry)
        X, y, steps, share = viewer_rule_c(entry, data, out_dir)
        log(f'  viewer {mid}: {len(y)} windows, walking {int((y == 0).sum())}, '
            f'steps/window median {float(np.median(steps)):.1f}')
        Xs.append(X); ys.append(y); ss.append(steps); shs.append(share)
        names.append(np.full(len(y), mid, dtype=object))
    out = dict(X=np.vstack(Xs), y=np.concatenate(ys), steps=np.concatenate(ss),
               moving_share=np.concatenate(shs), persona=np.concatenate(names))
    np.savez_compressed(p, **out)
    return out


def md_table(df, fmt='{:.1f}'):
    head = '| ' + ' | '.join([str(df.index.name or '')] + [str(c) for c in df.columns]) + ' |'
    sep = '|' + '---|' * (len(df.columns) + 1)
    body = []
    for i, r in df.iterrows():
        body.append('| ' + ' | '.join([str(i)] + [fmt.format(v) if isinstance(v, (float, np.floating)) and
                                                np.isfinite(v) else ('' if pd.isna(v) else str(v)) for v in r]) + ' |')
    return '\n'.join([head, sep] + body)


def write_summary(agg, out_dir, baseline_still, best, g2):
    def get(table, metric, dataset=None, key=None, variant=None):
        d = agg[(agg.table == table) & (agg.metric == metric)]
        if dataset is not None:
            d = d[d.dataset == dataset]
        if key is not None:
            d = d[d.key == key]
        if variant is not None:
            d = d[d.variant == variant]
        return d

    def pivot(table, metric, index=('dataset', 'key')):
        d = agg[(agg.table == table) & (agg.metric == metric)].copy()
        if d.empty:
            return None
        if len(index) == 1:
            d['row'] = d[index[0]]
        else:
            d['row'] = d[index[0]] + d[index[1]].map(lambda k: '' if k in ('', 'all') else ' ' + str(k))
        return d.pivot_table(index='row', columns='variant', values='value', aggfunc='first')

    def sd_pivot(table, metric, index=('dataset', 'key')):
        d = agg[(agg.table == table) & (agg.metric == metric)].copy()
        if d.empty:
            return None
        if len(index) == 1:
            d['row'] = d[index[0]]
        else:
            d['row'] = d[index[0]] + d[index[1]].map(lambda k: '' if k in ('', 'all') else ' ' + str(k))
        return d.pivot_table(index='row', columns='variant', values='sd', aggfunc='first')

    def show(P, Q):
        if P is None:
            return '(no data)'
        out = P.copy().astype(object)
        if Q is not None:
            for c in P.columns:
                if c in Q.columns:
                    out[c] = [f'{v:.1f} ({s:.1f})' if np.isfinite(s) else f'{v:.1f}' for v, s in zip(P[c], Q[c])]
                else:
                    out[c] = [f'{v:.1f}' if np.isfinite(v) else '' for v in P[c]]
        return md_table(out)

    parts = ['# A1: V4half + walking-aid gait, 5-fold CV by source person, 3 seeds', '',
             'Values in percent (`mean (sd)` over seeds), except nodes and events per hour. '
             'Stairs rule 0.60 applied to every prediction. Aid rows are held out with their source person.',
             '']
    parts += ['## Aid-gait walking recall (held-out), %', '',
              show(pivot('aid_aid', 'recall_pct', ('dataset',)), sd_pivot('aid_aid', 'recall_pct', ('dataset',))), '',
              '### by speed band', '',
              show(pivot('aid_band', 'recall_pct', ('dataset',)), sd_pivot('aid_band', 'recall_pct', ('dataset',))), '',
              '### by steps per 4 s window', '',
              show(pivot('aid_steps', 'recall_pct', ('dataset',)), sd_pivot('aid_steps', 'recall_pct', ('dataset',))), '',              '### aid windows called walking: still cost', '',
              show(pivot('aid', 'called_walking_pct', ('dataset', 'key')),
                   sd_pivot('aid', 'called_walking_pct', ('dataset', 'key'))), '',
              '## External viewer personas (rule C labels), walking recall per persona, %', '']
    ext = agg[agg.table == 'external'].pivot_table(index='dataset', columns='variant', values='value',
                                                  aggfunc='mean')
    parts += [md_table(ext) if not ext.empty else '(no data)', '']
    parts += ['## Real still cost per dataset: still called walking, %', '',
              show(pivot('still', 'called_walking_pct', ('dataset',)), sd_pivot('still', 'called_walking_pct', ('dataset',))), '',
              '### still precision, %', '',
              show(pivot('still', 'precision_pct', ('dataset',)), sd_pivot('still', 'precision_pct', ('dataset',))), '',
              '## No regression: walking recall per real dataset, %', '',
              show(pivot('walking', 'recall_pct', ('dataset',)), sd_pivot('walking', 'recall_pct', ('dataset',))), '',
              '## Walking called stairs (after the 0.60 rule), %', '',
              show(pivot('called', 'walking_called_stairs_pct', ('key',)),
                   sd_pivot('called', 'walking_called_stairs_pct', ('key',))), '',
              '## Luo / PAMAP2 stairs, recall and precision, %', '']
    for metric in ('recall_pct', 'precision_pct'):
        parts += [f'### stairs {metric.replace("_pct", "")}', '',
                  show(pivot('stairs', metric, ('dataset', 'key')), sd_pivot('stairs', metric, ('dataset', 'key'))), '']
    parts += ['## Simulated transition events (R1) and false events per hour', '',
              show(pivot('events', 'event_recall_pct', ('dataset',)),
                   sd_pivot('events', 'event_recall_pct', ('dataset',))), '',
              show(pivot('events', 'false_per_hour', ('dataset', 'key')),
                   sd_pivot('events', 'false_per_hour', ('dataset', 'key'))), '',
              '## Model size, nodes of the fold-0 forest', '',
              show(pivot('size', 'nodes', ('dataset',)), None), '',
              '## Best variant for the G2 check', '',
              f'Chosen by: highest mean aid walking recall among variants whose overall real-still called-walking '
              f'cost is within 1.0 point of V4half. **{best}**.', '']
    g2txt = ''
    if os.path.exists(g2):
        with open(g2, encoding='utf-8') as f:
            g2txt = f.read()
    parts += [g2txt, '']
    path = os.path.join(out_dir, 'cv_aid_summary.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts) + '\n')
    return path


def owner_summary(agg, out_dir, best):
    """One screen, numbers only, no recommendation."""
    def val(table, metric, dataset=None, key=None):
        d = agg[(agg.table == table) & (agg.metric == metric)]
        if dataset is not None:
            d = d[d.dataset == dataset]
        if key is not None:
            d = d[d.key == key]
        return d.set_index('variant')['value'] if not d.empty else pd.Series(dtype=float)

    rows = []
    def add(label, s):
        rows.append([label] + [f'{s.get(v, np.nan):.1f}' if v in s.index and np.isfinite(s[v]) else '-'
                               for v in VARIANTS])
    add('Aid walking recall, %', val('aid', 'recall_pct', 'all', 'walking'))
    add('Aid walking recall: pick-up walker', val('aid_aid', 'recall_pct', dataset='pick-up walker'))
    add('Aid walking recall: rollator', val('aid_aid', 'recall_pct', dataset='rollator'))
    add('Aid walking recall: crutches', val('aid_aid', 'recall_pct', dataset='crutches'))
    add('Aid still called walking, %', val('aid', 'called_walking_pct', 'all', 'still'))
    add('Real still called walking, %', val('still', 'called_walking_pct', 'real', 'all'))
    add('Real still precision, %', val('still', 'still_precision_pct', 'real', 'all'))
    for d in ('WearGait-PD', 'CeTI', 'Luo', 'Lencioni', 'KneE-PAD', 'Marpino', 'PAMAP2'):
        add(f'Walking recall {d}, %', val('walking', 'recall_pct', d, 'walking'))
    add('Walking->stairs Lencioni fast, %', val('called', 'walking_called_stairs_pct', 'Lencioni', 'fast'))
    add('Walking->stairs Luo FE, %', val('called', 'walking_called_stairs_pct', 'Luo', 'FE'))
    add('Walking->stairs WG hurried, %', val('called', 'walking_called_stairs_pct', 'WearGait-PD', 'HurriedPace'))
    add('Luo stairs up recall, %', val('stairs', 'recall_pct', 'Luo', 'stairs_up'))
    add('Luo stairs down recall, %', val('stairs', 'recall_pct', 'Luo', 'stairs_down'))
    add('PAMAP2 stairs up recall, %', val('stairs', 'recall_pct', 'PAMAP2', 'stairs_up'))
    add('PAMAP2 stairs down recall, %', val('stairs', 'recall_pct', 'PAMAP2', 'stairs_down'))
    add('Sim transition recall, %', val('events', 'event_recall_pct', 'simulation', 'both'))
    add('False events / h (Camargo)', val('events', 'false_per_hour', 'Camargo', 'no transition'))
    ext = agg[agg.table == 'external'].groupby('variant')['value'].mean()
    rows.append(['External 8 personas walking recall, %'] + [f'{ext.get(v, np.nan):.1f}' for v in VARIANTS])
    nodes = agg[agg.table == 'size'].groupby('variant')['value'].mean()
    rows.append(['Forest nodes (fold 0)'] + [f'{nodes.get(v, np.nan):.0f}' for v in VARIANTS])
    head = '| metric | ' + ' | '.join(VARIANTS) + ' |'
    lines = [f'# A1 owner summary: V4half + aid gait (mean over 3 seeds)', '',
             'Numbers only; the owner decides. Stairs rule 0.60. Best variant for the G2 check: ' + best + '.', '',
             head, '|' + '---|' * (len(VARIANTS) + 1)]
    lines += ['| ' + ' | '.join(r) + ' |' for r in rows]
    path = os.path.join(out_dir, 'owner_summary.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def g2_check(agg, best, final_preds, ext, A, y, aid, pred_dir, out_dir, log):
    """Repeat G2's cut-off check on the best variant: viewer walker personas vs real still."""
    seed = 0
    Z = np.load(os.path.join(pred_dir, f'pred_{best}_W{WIN}s_8cls_seed{seed}.npz'))
    pred_ext = final_preds['__external__'][best][seed]
    # viewer walking recall (the model is trained on all data; the viewer personas are never trained on)
    rows = []
    for i, name in enumerate(VIEWER_IDS):
        m = ext['persona'] == name
        rows.append((name, int((ext['y'][m] == 0).sum()), 100.0 * float((pred_ext[m][ext['y'][m] == 0] == 0).mean())
                     if (ext['y'][m] == 0).any() else np.nan))
    # feature medians: walker viewer personas (old_14/18/20) vs real still (8-class still)
    walk_ids = ['old_14_your_protocol_early_wa', 'old_18_toe_touch_walker',
                'old_20_static_spacer_partial']
    mv = np.isin(ext['persona'], walk_ids)
    Xv = ext['X'][mv]
    real_still = (A['src'] == 'real') & (y == 3)
    Xs = A['X'][real_still]
    feats = ['std_m', 'mean_m', 'ptp_m', 'jerk_m']
    rows_med = []
    for f in feats:
        i = FEAT_NAMES.index(f)
        rows_med.append((f, float(np.median(Xv[:, i])), float(np.median(Xs[:, i])), G2_CUTOFF.get(f, np.nan)))
    # new forest roots (the G2 check looked at root splits), final model of the best variant, seed 0
    model = fit_variant(A, aid, None, None, best, seed, y, final=True)
    roots = Counter((FEAT_NAMES[int(est.tree_.feature[0])], round(float(est.tree_.threshold[0]), 3))
                    for est in model.estimators_)
    top_roots = roots.most_common(8)
    # real still cost for the best variant (out-of-fold predictions, after rule)
    p = rule06(Z['pred'], Z['proba'])
    still_m = real_still & (Z['pred'] >= 0)
    still_call = 100.0 * float((p[still_m] == 0).mean()) if still_m.any() else np.nan
    lines = ['## G2 check on the best variant', '',
             f'Best variant **{best}**, final forest seed {seed}; viewer personas are external (never trained on).',
             '', '| viewer persona | walking windows | called walking, % |', '|---|---:|---:|']
    lines += [f'| {n} | {k} | {v:.1f} |' for n, k, v in rows]
    lines += ['', '| feature | walker viewers (median) | real still (median) | G2 V4 cut-off |',
              '|---|---:|---:|---:|']
    lines += [f'| {f} | {a:.4f} | {b:.4f} | {c:.3f} |' for f, a, b, c in rows_med]
    lines += ['', f'Real still called walking (best variant, out-of-fold): **{still_call:.1f} %**.', '',
              'Most common root splits of the new forest (feature, threshold, trees):', '']
    lines += [f'- `{f} <= {t}`: {n}/20 trees' for (f, t), n in top_roots]
    lines += ['', 'G2 root splits of the old V4 forest (reference): `ptp_m <= 0.315` in 4/20 trees, '
              '`jerk_m <= 0.731` in 1/20, `std_m <= 0.062` in 1/20.']
    path = os.path.join(out_dir, 'G2_check.md')
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    log(f'Saved {path}')
    return path


def main():
    ap = argparse.ArgumentParser(description='KNEIL A1: aid-gait CV experiment')
    ap.add_argument('--aid-name', default='aid_gait')
    ap.add_argument('--out-name', default='cv_aid')
    ap.add_argument('--base-v4', default=os.path.join(config.RESULTS, 'v4'),
                    help='the real V4 folder with stepD/windows_v11 and stepD/D2')
    ap.add_argument('--variants', nargs='+', default=list(VARIANTS), choices=list(VARIANTS))
    ap.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    ap.add_argument('--holdout-ab07', action='store_true',
                    help='never train on AB07 (its viewer personas stay an independent external test)')
    a = ap.parse_args()
    global HOLDOUT
    HOLDOUT = {'ab07'} if a.holdout_ab07 else set()
    print(VERSION, flush=True)
    out_dir = config.out_dir('stepF', a.out_name)
    log_path = os.path.join(out_dir, 'cv_aid_log.txt')
    with S1.Tee(log_path):
        print(f'{VERSION} | {C.VERSION} | {S3.VERSION} | {config.VERSION} | {np.datetime64("now", "s")}')
        print(f'aid {a.aid_name}, base {a.base_v4}, variants {a.variants}, seeds {a.seeds}')
        S3.init_tinyml()
        A = load_base(WIN, a.base_v4)
        y = C.y_for(A, 8)
        gf4 = fold_map(2, a.base_v4)
        fold = C.folds_for(A, gf4, log=lambda *x: None)
        aid = load_aid(a.aid_name)
        fold_aid = aid_folds(aid, gf4)
        global AID_META
        AID_META = dict(aid=aid['aid'], speed_band=aid['speed_band'], steps=aid['steps'])
        log = lambda m: log_msg(m, log_path)
        log(f'base rows {len(y)}, aid rows {len(aid["y"])}, usable aid {int(aid["usable"].sum())}, '
            f'people {len(set(aid["grp"]))}')
        pred_dir = os.path.join(out_dir, 'pred_' + a.aid_name)
        os.makedirs(pred_dir, exist_ok=True)
        times = TE.window_times(A, WIN)
        ext = external_set(out_dir, log)
        # external predictions are made by a model trained on all rows, once per variant and seed
        final_preds = {'__external__': {v: {} for v in a.variants}}
        runs = {}
        for variant in a.variants:
            for seed in a.seeds:
                runs[(variant, seed)] = run_one(A, aid, fold, fold_aid, y, variant, seed, pred_dir, log)
                m = fit_variant(A, aid, fold, fold_aid, variant, seed, y, final=True)
                pe_proba = m.predict_proba(ext['X'].astype(np.float32))
                pe = rule06(np.argmax(pe_proba, axis=1), pe_proba)
                final_preds['__external__'][variant][seed] = pe
                log(f'  {variant} seed {seed}: external walking recall '
                    f'{100.0 * float((pe[ext["y"] == 0] == 0).mean()):.1f} %')
        rows = []
        base_still = {}
        for variant in a.variants:
            for seed in a.seeds:
                r = runs[(variant, seed)]
                p = rule06(r['pred'], r['proba'])
                pa = rule06(r['pred_aid'], r['proba_aid'])
                ys = [r['nodes']]
                mm, still, aid_rec = base_metrics(A, y, p, pa, variant, seed, aid['y'], times)
                rows += mm
                rows.append(dict(variant=variant, seed=seed, table='size', dataset='forest 20x d10',
                                 key='fold 0', metric='nodes', value=float(r['nodes']), n=1))
                for name in VIEWER_IDS:
                    m = ext['persona'] == name
                    pe = final_preds['__external__'][variant][seed]
                    wm = m & (ext['y'] == 0)
                    if wm.any():
                        v = 100.0 * float((pe[wm] == 0).mean())
                        rows.append(dict(variant=variant, seed=seed, table='external', dataset=name,
                                         key='walking', metric='recall_pct', value=v, n=int(wm.sum())))
                # baseline check against D2
                if variant == 'V4half':
                    d2 = os.path.join(a.base_v4, 'stepD', 'D2', f'pred_V4half_W{WIN}s_8cls_seed{seed}.npz')
                    if os.path.exists(d2):
                        z2 = np.load(d2)
                        same = int((r['pred'] == z2['pred']).sum())
                        log(f'  D2 baseline check seed {seed}: {same}/{len(r["pred"])} base predictions identical')
        R = pd.DataFrame(rows)
        R.to_csv(os.path.join(out_dir, 'cv_aid_runs.csv'), index=False)
        agg = (R.groupby(['variant', 'table', 'dataset', 'key', 'metric'])
               .agg(value=('value', 'mean'), sd=('value', 'std'), nseeds=('value', 'size'), n=('n', 'first'))
               .reset_index())
        agg.to_csv(os.path.join(out_dir, 'cv_aid_results.csv'), index=False)
        # best variant: highest aid recall, real-still cost within 1 point of V4half
        def mean_of(table, metric, dataset=None, key=None, variant='V4half'):
            d = agg[(agg.table == table) & (agg.metric == metric) & (agg.variant == variant)]
            if dataset is not None:
                d = d[d.dataset == dataset]
            if key is not None:
                d = d[d.key == key]
            return float(d.value.iloc[0]) if len(d) else np.nan
        base_cost = mean_of('still', 'called_walking_pct', 'real', 'all')
        cand = []
        for v in a.variants:
            ar = mean_of('aid', 'recall_pct', 'all', 'walking', v)
            cost = mean_of('still', 'called_walking_pct', 'real', 'all', v)
            cand.append((v, ar, cost))
        eligible = [c for c in cand if np.isfinite(c[2]) and c[2] <= base_cost + 1.0]
        pool = eligible if eligible else cand
        best = max(pool, key=lambda c: (c[1] if np.isfinite(c[1]) else -1))[0]
        log(f'best variant {best}; candidates {[(v, round(ar, 1), round(c, 1)) for v, ar, c in cand]}')
        g2 = g2_check(agg, best, final_preds, ext, A, y, aid, pred_dir, out_dir, log)
        write_summary(agg, out_dir, base_cost, best, g2)
        owner_summary(agg, out_dir, best)
        log(f'Saved {out_dir}/cv_aid_summary.md and owner_summary.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
