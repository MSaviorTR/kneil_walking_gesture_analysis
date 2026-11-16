"""
KNEIL V4 step D2 part C: causal stairs evidence rule.   stairs_rule 1.0, 16 Nov 2026

Post-processing of the window predictions the chip could also do (it can only look back): a window whose raw
prediction is stairs_up or stairs_down keeps it only if
    (1) the probability of the predicted class is >= theta, and
    (2) at least k of the last n windows of the same stream (t-n+1 .. t, raw predictions) are stairs_up or stairs_down;
otherwise the prediction becomes walking. Other classes are never touched.

The parameters (theta, k, n) are tuned INSIDE the cross-validation: for test fold f they are chosen on the windows of
the other four folds (their out-of-fold predictions) to maximise the mean stairs F1 over {Luo, PAMAP2, simulated},
where stairs F1 treats stairs_up and stairs_down as one class "stairs" against everything else (windows with y >= 0).

Input: pred_{variant}_W{win}s_8cls_seed{seed}.npz (pred, proba, fold) from cv_v4 1.1 and the v1.1 window file.
Output (config.out_dir('stepD','D2')): rule_params.csv (parameters per fold), stairs_rule_runs.csv (per seed),
stairs_rule_results.csv (mean/sd over seeds) and stairs_rule_summary.md.

CLI: python pipeline/stairs_rule.py [--win 2 3 4 5] [--variants V3recipe V4data V4half] [--seeds 0 1 2] [--smoke]
"""
import argparse
import glob
import os
import re
import time

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

import config
import cv_v4 as C
import stage01 as S1
import stage3 as S3

VERSION = 'stairs_rule 1.0'
THETAS = (0.30, 0.40, 0.50, 0.60, 0.70)
KN = ((1, 1), (2, 2), (2, 3), (3, 3), (3, 4), (4, 5))
STAIRS = (1, 2)
WALKING = 0
OBJ = ('Luo', 'PAMAP2', 'sim')          # the datasets of the tuning objective
NS = tuple(sorted({n for _, n in KN}))


def rolling_stair_counts(pred, stream):
    """n -> number of stairs predictions among the last n windows of the same stream (including t). Causal.
    The rows are grouped by stream with a stable sort first, so the function also works on row-subsampled files
    (the smoke test), where the rows of one stream are not contiguous; time order within a stream is kept."""
    stair = np.isin(pred, STAIRS)
    m = len(stair)
    out = {n: np.zeros(m, np.int16) for n in NS}
    order = np.argsort(stream, kind='stable')
    s, sid = stair[order], stream[order]
    starts = np.r_[0, np.flatnonzero(np.diff(sid) != 0) + 1]
    ends = np.r_[starts[1:], m]
    for a, b in zip(starts, ends):
        c = np.concatenate(([0], np.cumsum(s[a:b], dtype=np.int32)))
        idx = np.arange(1, b - a + 1)
        for n in NS:
            out[n][order[a:b]] = c[idx] - c[np.maximum(idx - n, 0)]
    return out


def proba_at(pred, proba):
    """Probability of the class the model predicted, 0 where there is no prediction."""
    p = proba.astype(np.float32)
    idx = np.clip(pred, 0, p.shape[1] - 1)
    v = p[np.arange(len(pred)), idx].copy()
    v[pred < 0] = 0.0
    return v


def apply_rule(pred, pa, roll, theta, k, n):
    """The rule of the task. Predictions that are not stairs are returned unchanged."""
    stair = np.isin(pred, STAIRS)
    keep = stair & (pa >= theta) & (roll[n] >= k)
    out = pred.copy()
    out[stair & ~keep] = WALKING
    return out


def stairs_f1(y, pred, mask):
    """F1 of the merged class 'stairs' against everything else over `mask` (windows with y >= 0)."""
    mask = mask & (y >= 0)
    if not mask.any():
        return np.nan
    t = np.isin(y[mask], STAIRS); p = np.isin(pred[mask], STAIRS)
    if not t.any():
        return np.nan
    if not p.any():
        return 0.0
    return float(f1_score(t, p, pos_label=True, average='binary', zero_division=0))


def tune(y, pred, pa, roll, ds, src, train):
    """Best (theta, k, n) and its objective on the windows of the training folds."""
    masks = {'Luo': train & (ds == 'Luo'), 'PAMAP2': train & (ds == 'PAMAP2'), 'sim': train & (src == 'sim')}
    best, bestp = -np.inf, None
    for theta in THETAS:
        for k, n in KN:
            newp = apply_rule(pred, pa, roll, theta, k, n)
            vals = [stairs_f1(y, newp, masks[d]) for d in OBJ]
            vals = [v for v in vals if np.isfinite(v)]
            if vals and float(np.mean(vals)) > best:
                best, bestp = float(np.mean(vals)), (theta, k, n)
    return bestp, best


def predict(A, pred, proba, fold):
    """Apply the rule with parameters tuned per fold. Returns (after, params, unchanged_non_stairs)."""
    y = C.y_for(A, 8)
    pa = proba_at(pred, proba)
    roll = rolling_stair_counts(pred, A['stream'])
    after = pred.copy(); params = []
    for f in range(C.K):
        bestp, best = tune(y, pred, pa, roll, A['ds'], A['src'], (fold != f) & (pred >= 0))
        m = fold == f
        if bestp is None:
            params.append((f, None, None, None, np.nan))
            continue
        after[m] = apply_rule(pred, pa, roll, *bestp)[m]
        params.append((f, *bestp, best))
    non_stair = ~np.isin(pred, STAIRS)
    non_stair_changed = int((after[non_stair] != pred[non_stair]).sum())
    return after, params, non_stair_changed


def metrics(A, y, pred, stage, variant, win, seed):
    """The before/after numbers of the report, long format."""
    ds, src, ok = A['ds'], A['src'], pred >= 0
    rows = []

    def add(table, dataset, key, metric, value, n):
        if n and np.isfinite(value):
            rows.append(dict(variant=variant, win=win, seed=seed, stage=stage, table=table, dataset=dataset,
                             key=str(key), metric=metric, value=float(value), n=int(n)))

    for d in ('Luo', 'PAMAP2', 'sim'):
        m = ok & ((src == 'sim') if d == 'sim' else (ds == d))
        name = 'simulated' if d == 'sim' else d
        for c in STAIRS:
            cn = C.CLASSES8[c]
            mt = m & (y == c)
            add('stairs', name, cn, 'recall_pct', 100.0 * float((pred[mt] == c).mean()), int(mt.sum()))
            mp = m & (pred == c)
            add('stairs', name, cn, 'precision_pct', 100.0 * float((y[mp] == c).mean()), int(mp.sum()))
    for d in sorted(set(ds[src == 'real'])):
        m = ok & (ds == d) & (y == WALKING)
        add('walking', d, 'walking', 'recall_pct', 100.0 * float((pred[m] == WALKING).mean()), int(m.sum()))
    stair = np.isin(pred, STAIRS)

    def called(mask, d, key):
        m = mask & ok & (y == WALKING)
        add('called', d, key, 'walking_called_stairs_pct', 100.0 * float(stair[m].mean()), int(m.sum()))

    for r in sorted(set(A['rec'][(ds == 'WearGait-PD') & (y == WALKING)])):
        called((ds == 'WearGait-PD') & (A['rec'] == r), 'WearGait-PD', f'rec={r}')
    for col in ('speed_abs', 'speed_rel'):
        for v in sorted(x for x in set(A[col][(ds == 'Lencioni') & (y == WALKING)]) if x):
            called((ds == 'Lencioni') & (A[col] == v), 'Lencioni', f'{col}={v}')
    for v in sorted(x for x in set(A['surface'][(ds == 'Luo') & (y == WALKING)]) if x):
        called((ds == 'Luo') & (A['surface'] == v), 'Luo', f'surface={v}')
    for lbl in ('slope_up', 'slope_down'):
        m = ok & (ds == 'Luo') & (y < 0) & (A['lab'] == lbl)
        add('slopes', 'Luo', lbl, 'predicted_stairs_pct', 100.0 * float(stair[m].mean()), int(m.sum()))
    for lbl in ('stairs_up', 'stairs_down'):
        m = ok & (ds == 'Lencioni') & (A['role'] == 'test') & (A['lab'] == lbl)
        add('lencioni_test', 'Lencioni', lbl, 'recognised_as_stairs_pct', 100.0 * float(stair[m].mean()), int(m.sum()))
    return rows


def md_table(df):
    head = '| ' + ' | '.join([str(df.index.name or '')] + [str(c) for c in df.columns]) + ' |'
    out = [head, '|' + '---|' * (len(df.columns) + 1)]
    for i, r in df.iterrows():
        out.append('| ' + ' | '.join([str(i)] + ['' if pd.isna(v) else str(v) for v in r]) + ' |')
    return '\n'.join(out)


def write_outputs(rows, params, out_dir, log=print):
    R = pd.DataFrame(rows)
    runs_csv = os.path.join(out_dir, 'stairs_rule_runs.csv')
    key = ['variant', 'win', 'seed', 'stage', 'table', 'dataset', 'key', 'metric']
    if os.path.exists(runs_csv):
        old = pd.read_csv(runs_csv)
        tri = set(map(tuple, R[key].drop_duplicates().itertuples(index=False)))
        keep = ~pd.Series(list(zip(*[old[c] for c in key])), index=old.index).isin(tri)
        R = pd.concat([old[keep], R], ignore_index=True)
    R = R.sort_values(key)
    R.to_csv(runs_csv, index=False)
    P = pd.DataFrame(params)
    P.to_csv(os.path.join(out_dir, 'rule_params.csv'), index=False)
    agg = (R.groupby(['variant', 'win', 'stage', 'table', 'dataset', 'key', 'metric'], dropna=False)
           .agg(value=('value', 'mean'), sd=('value', 'std'), nseeds=('value', 'size'), n=('n', 'first'))
           .reset_index())
    agg.to_csv(os.path.join(out_dir, 'stairs_rule_results.csv'), index=False)
    recs = agg.to_dict('records')
    runs = (agg[['variant', 'win']].drop_duplicates().sort_values(['win', 'variant'])
            .apply(lambda r: f'{r.variant} {r.win:g}s', axis=1).tolist())
    parts = [f'# Stairs evidence rule, before -> after ({VERSION})', '',
             f'{len(runs)} runs (mean over seeds): ' + ', '.join(f'`{r}`' for r in runs), '',
             'Values in percent, format `mean (sd)` over the seeds. Rule: stairs kept only if the probability of the '
             'predicted class is >= theta and at least k of the last n windows of the same stream are stairs; '
             'otherwise walking. (theta, k, n) chosen per test fold on the other four folds.', '']
    for table, title in (('stairs', 'stairs_up / stairs_down recall and precision'),
                         ('walking', 'walking recall per real dataset'),
                         ('called', 'walking called stairs'),
                         ('slopes', 'Luo slopes predicted as stairs'),
                         ('lencioni_test', 'Lencioni test stairs recognised as stairs')):
        for metric in [m for m in ('recall_pct', 'precision_pct', 'walking_called_stairs_pct',
                                   'predicted_stairs_pct', 'recognised_as_stairs_pct') if
                       any(r['table'] == table and r['metric'] == m for r in recs)]:
            parts += [f'## {title} - {metric.replace("_pct", "")}, before', '']
            parts += [sub(recs, table, metric, 'before'), '']
            parts += [f'## {title} - {metric.replace("_pct", "")}, after', '']
            parts += [sub(recs, table, metric, 'after'), '']
    parts += ['## parameters chosen per fold (mean over the seeds and folds)', '']
    if not P.empty:
        Q = (P.groupby(['variant', 'win', 'theta', 'k', 'n']).size().rename('folds').reset_index())
        parts += [Q.to_string(index=False), '']
    path = os.path.join(out_dir, 'stairs_rule_summary.md')
    open(path, 'w', encoding='utf-8').write('\n'.join(parts) + '\n')
    log(f'  saved {runs_csv}, rule_params.csv, stairs_rule_results.csv and {path}')
    return agg


def sub(recs, table, metric, stage):
    d = [r for r in recs if r['table'] == table and r['metric'] == metric and r['stage'] == stage]
    if not d:
        return '(no data)'
    T = pd.DataFrame(d)
    T['run'] = T.variant + ' ' + T.win.map(lambda w: f'{w:g}s')
    T['row'] = T.dataset + T.key.map(lambda k: '' if k in ('', 'all') else ' ' + k)
    P = T.pivot_table(index='row', columns='run', values='value', aggfunc='first')
    Q = T.pivot_table(index='row', columns='run', values='sd', aggfunc='first')
    out = P.copy().astype(object)
    for c in P.columns:
        out[c] = [f'{v:.1f} ({s:.1f})' if np.isfinite(s) else f'{v:.1f}' for v, s in zip(P[c], Q[c])]
    out.index.name = 'dataset / key'
    return md_table(out)


def find_runs(out_dir, wins, variants, seeds):
    """The prediction files present in out_dir, as (variant, win, seed, path)."""
    out = []
    for p in glob.glob(os.path.join(out_dir, 'pred_*_W*s_8cls_seed*.npz')):
        b = os.path.basename(p)
        m = re.match(r'pred_(.+)_W([\d.]+)s_8cls_seed(\d+)\.npz$', b)
        if not m:
            continue
        v, w, s = m.group(1), float(m.group(2)), int(m.group(3))
        if (not wins or w in wins) and (not variants or v in variants) and (not seeds or s in seeds):
            out.append((v, w, s, p))
    return sorted(out, key=lambda t: (t[1], t[0], t[2]))


def main():
    ap = argparse.ArgumentParser(description='KNEIL V4 stairs evidence rule (D2 part C)')
    ap.add_argument('--win', type=float, nargs='+', default=[])
    ap.add_argument('--variants', nargs='+', default=[])
    ap.add_argument('--seeds', type=int, nargs='+', default=[])
    ap.add_argument('--smoke', action='store_true', help='use stepD/D2/smoke (the --max-rows predictions)')
    ap.add_argument('--max-rows', type=int, default=None, help='the same subsample as the smoke run (seed 0)')
    a = ap.parse_args()
    print(VERSION, flush=True)
    out_dir = config.out_dir('stepD', 'D2', 'smoke') if a.smoke else config.out_dir('stepD', 'D2')
    with S1.Tee(os.path.join(out_dir, 'stairs_rule_log.txt')):
        print(f'{VERSION} | {C.VERSION} | {config.VERSION} | {np.datetime64("now", "s")}')
        runs = find_runs(out_dir, a.win, a.variants, a.seeds)
        print(f'  {len(runs)} prediction files in {out_dir}')
        rows, params, t0, cache = [], [], time.time(), {}
        for variant, win, seed, path in runs:
            if win not in cache:
                A = C.load(win)
                cache[win] = C.subsample(A, a.max_rows) if a.max_rows else A
            A = cache[win]
            Z = np.load(path)
            pred, proba, fold = Z['pred'], Z['proba'], Z['fold'].astype(int)
            if len(pred) != len(A['y']):
                raise SystemExit(f'{path}: {len(pred)} predictions but {len(A["y"])} rows; '
                                 f'set --max-rows to the same value as the prediction run')
            y = C.y_for(A, 8)
            after, pars, changed = predict(A, pred, proba, fold)
            if changed:
                print(f'  ERROR: {variant} {win:g}s seed {seed}: the rule changed {changed} non-stairs windows')
            params += [dict(variant=variant, win=win, seed=seed, fold=p[0], theta=p[1], k=p[2], n=p[3], objective=p[4])
                       for p in pars]
            rows += metrics(A, y, pred, 'before', variant, win, seed)
            rows += metrics(A, y, after, 'after', variant, win, seed)
            n_changed = int((after != pred).sum())
            print(f'  {variant} {win:g}s seed {seed}: {n_changed} windows changed, parameters '
                  f'{[(p[1], p[2], p[3]) for p in pars if p[1] is not None]}')
        T = write_outputs(rows, params, out_dir)
        print(f'\nrows {len(T)}, total {(time.time() - t0) / 60:.1f} min')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
