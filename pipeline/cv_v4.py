"""
KNEIL V4 steps D1/D2: cross-validation of 8 classes x window length x data variant.   cv_v4 1.1, 16 Nov 2026

Runs a 20-tree forest (stage3.make_model) with 5 folds by person on the v1.1 window caches
(<KNEIL_V4_OUT>/stepD/windows_v11/windows_W{2,3,4,5}s.npz) and writes the tables of the task.

Classes: 8 classes (sitting + standing -> 'still'); the 9-class labels are kept for the V3 regression.
Folds:  person groups (stage3.assign_folds). The 8-class runs use the map of the 2 s file (task item 2), the
        9-class regression run uses the map of the V3 cache, so that its folds are exactly V3's (D1 check 1;
        inserting Luo/Lencioni into the real-dataset list would otherwise shift the shuffles of 105 old groups).
Data:   'V3recipe' = sim + Caicedo + the six old real datasets (no Luo, no Lencioni) with the V3 weights;
        'V4data'   = the same + Luo + Lencioni (y >= 0 rows only), as two more real datasets in the sqrt weighting;
        'V4half'   = 'V4data' with the weights of the Luo and Lencioni rows multiplied by 0.5.

1.1: --seeds (forest random_state), the V4half variant, class probabilities saved with every run, and mean (sd)
over the seeds in the tables.

Output (config.out_dir('stepD','D2')): pred_{variant}_W{win}s_{ncls}cls_seed{seed}.npz (pred, proba, fold, nodes;
resume), D2_results.csv (long format, mean and sd over the seeds) and D2_summary.md (tables a-g).
Smoke test: --max-rows N writes to stepD/D2/smoke and is never resumed from the real cache.
CLI: python pipeline/cv_v4.py --win 2 3 4 5 --seeds 0 1 2 --variants V3recipe V4data V4half
     python pipeline/cv_v4.py --win 2 --variants V3recipe --classes 9      # V3 regression (D1 check 1)
"""
import argparse
import os
import time

import numpy as np
import pandas as pd

import config
import stage01 as S1
import stage3 as S3
import stage3_v4 as S4

VERSION = 'cv_v4 1.1'
WINS = (2, 3, 4, 5)
VARIANTS = ('V3recipe', 'V4data', 'V4half')
CLASSES8 = ['walking', 'stairs_up', 'stairs_down', 'still', 'lying', 'sit_to_stand', 'stand_to_sit', 'bed_transfer']
CLASSES9 = S3.DEVICE
Y8 = np.array([0, 1, 2, 3, 3, 4, 5, 6, 7], np.int8)     # 9-class id -> 8-class id (sitting and standing -> still)
NEW_DS = ('Luo', 'Lencioni')
NEW_WEIGHT = {'V4data': 1.0, 'V4half': 0.5}             # factor on the Luo/Lencioni weights
K = 5
COLS = ('X', 'y', 'src', 'ds', 'grp', 'task', 'lab', 'rec', 'surface', 'speed_abs', 'speed_rel', 'adult', 'role',
        'stream')


def classes(ncls):
    return CLASSES8 if ncls == 8 else CLASSES9


def y_for(A, ncls):
    """The labels of one run: the 9-class y (with -1) or the 8-class map of it (with -1)."""
    y = A['y']
    return (np.where(y >= 0, Y8[np.clip(y, 0, 8)], -1).astype(np.int8) if ncls == 8 else y).copy()


def windows_path(win):
    return os.path.join(config.out_dir('stepD', S4.WINDOWS_DIR), f'windows_W{win:g}s.npz')


def load(win):
    path = windows_path(win)
    if not os.path.exists(path):
        raise FileNotFoundError(f'{path}: run pipeline/stage3_v4.py --win {win:g} first')
    Z = np.load(S1.local_copy(path, 'w4'), allow_pickle=True)
    return {k: Z[k] for k in Z.files if k in COLS}


def fold_map_v4(win2=2):
    """Group -> fold from stage3.assign_folds on the 2 s file (task D1 item 2)."""
    return S3.assign_folds(load(win2))[1]


_V3 = {}


def fold_map_v3():
    """(group -> fold, fold per row) of the V3 cache - exactly what stage3.cross_validate used."""
    if not _V3:
        p = os.path.join(config.RESULTS, 'virtual_implant', 'stage3', 'stage3_windows.npz')
        Z = np.load(S1.local_copy(p, 'v3'), allow_pickle=True)
        fold, gf = S3.assign_folds({k: Z[k] for k in Z.files})
        _V3.update(gf=gf, fold=fold)
    return _V3['gf'], _V3['fold']


def folds_for(A, gf, log=print):
    f = np.array([gf.get(g, -1) for g in A['grp']], int)
    miss = int((f < 0).sum())
    if miss:
        log(f'  WARNING: {miss} rows have a group without a fold (prediction stays -2; they are never tested)')
    return f


def folds_v3_extended(A, gf3, gf4, log=print):
    """The V3 fold map for the old rows, the 2 s-file map for the V4 rows (no V3 fold exists for them). The old rows
    keep exactly V3's fold; the new dataset groups get their fold from the 2 s-file map. No fold trains on them in
    the V3recipe, so their prediction is still out-of-sample."""
    f3 = np.array([gf3.get(g, -1) for g in A['grp']], int)
    f4 = np.array([gf4.get(g, -1) for g in A['grp']], int)
    new = np.isin(A['ds'], NEW_DS)
    f = np.where(new, f4, f3)
    log(f'  folds: V3 map for {int((~new).sum())} old rows, 2 s-file map for {int(new.sum())} V4 rows; '
        f'{int((f < 0).sum())} rows without a fold')
    return f


def subsample(A, n, log=print):
    """At most n rows, allocated per dataset in proportion to its size (seed 0), for a smoke test."""
    rng = np.random.default_rng(0)
    ds = A['ds']
    keep = []
    for d in sorted(set(ds)):
        idx = np.flatnonzero(ds == d)
        k = max(1, int(round(n * len(idx) / len(ds))))
        keep.append(rng.choice(idx, min(k, len(idx)), replace=False))
    idx = np.sort(np.concatenate(keep))
    log(f'  smoke: {len(idx)} of {len(ds)} rows kept ({len(set(ds))} datasets)')
    return {k: v[idx] for k, v in A.items()}


def training_set_v4(A, mask, variant, y):
    """Rows, labels and weights of one data variant (logic of stage3.training_set, variant 'V3', no tilt copies)."""
    src, ds = A['src'], A['ds']
    ok = mask & (y >= 0)
    sim = ok & (src == 'sim'); cai = ok & (src == 'caicedo'); real = ok & (src == 'real')
    if variant == 'V3recipe':
        real &= ~np.isin(ds, NEW_DS)
    new_w = NEW_WEIGHT.get(variant, 1.0)
    Xs, ys, ws = [A['X'][sim]], [y[sim]], [np.ones(int(sim.sum()))]
    if cai.sum():
        Xs.append(A['X'][cai]); ys.append(y[cai])
        ws.append(np.full(int(cai.sum()), 0.3 * float((y[sim] == 0).sum()) / int(cai.sum())))
    if real.sum():
        n_sim = int(sim.sum()); dss = sorted(set(ds[real]))
        sz = {d: int((real & (ds == d)).sum()) for d in dss}
        tot = sum(np.sqrt(v) for v in sz.values())
        for d in dss:
            m = real & (ds == d)
            w = n_sim * np.sqrt(sz[d]) / tot / sz[d]
            if d in NEW_DS:
                w *= new_w
            Xs.append(A['X'][m]); ys.append(y[m]); ws.append(np.full(sz[d], w))
    return np.vstack(Xs), np.concatenate(ys).astype(int), np.concatenate(ws)


def run_one(A, variant, win, ncls, fold, out_dir, seed=0, log=print):
    """5 folds; every window of the test fold is predicted (also y = -1 windows) and the class probabilities are
    saved. Resumes from the npz."""
    path = os.path.join(out_dir, f'pred_{variant}_W{win:g}s_{ncls}cls_seed{seed}.npz')
    if os.path.exists(path):
        log(f'  {variant} {win:g} s {ncls} cls seed {seed}: loading {os.path.basename(path)}')
        Z = np.load(path)
        return dict(pred=Z['pred'], proba=Z['proba'] if 'proba' in Z.files else None, fold=Z['fold'],
                    nodes=int(Z['nodes']))
    y = y_for(A, ncls)
    pred = np.full(len(y), -2, np.int8)
    proba = np.zeros((len(y), ncls), np.float16)
    nodes = -1; t0 = time.time()
    for k in range(K):
        Xt, yt, wt = training_set_v4(A, fold != k, variant, y)
        m = S3.make_model('forest 20x d10')
        m.set_params(random_state=seed)
        m.fit(Xt, yt, sample_weight=wt)
        if k == 0:
            nodes = int(S3.T.n_nodes(m))
        te = fold == k
        p = m.predict_proba(A['X'][te])
        cls = np.asarray(m.classes_, int)
        assert np.array_equal(cls, np.arange(ncls)), f'unexpected classes {cls}'
        proba[te] = p.astype(np.float16)
        pred[te] = cls[np.argmax(p, axis=1)].astype(np.int8)
        log(f'  {variant} {win:g} s {ncls} cls seed {seed} fold {k + 1}/{K}: trained on {len(yt)} rows, tested on '
            f'{int(te.sum())} windows ({time.time() - t0:.0f} s, {nodes} nodes)')
    np.savez_compressed(path, pred=pred, proba=proba, fold=fold.astype(np.int8), nodes=np.int64(nodes),
                        variant=variant, win=np.float64(win), ncls=np.int64(ncls), seed=np.int64(seed))
    log(f'  {variant} {win:g} s {ncls} cls seed {seed}: done in {(time.time() - t0) / 60:.1f} min -> {path}')
    return dict(pred=pred, proba=proba, fold=fold, nodes=nodes)


# ------------------------------------------------------------------ tables a-g
def _recall(y, pred, c):
    m = y == c
    return 100.0 * float((pred[m] == c).mean()) if m.any() else np.nan


def _f1(y, pred, labels):
    from sklearn.metrics import f1_score
    return 100.0 * float(f1_score(y, pred, labels=labels, average='macro', zero_division=0)) if len(y) else np.nan


def tables(A, ncls, pred, nodes, variant, win, wg_groups, seed=0, log=print):
    """All the task's tables (a-g) for one run, in long format."""
    y = y_for(A, ncls); names = classes(ncls); src, ds = A['src'], A['ds']
    ok = pred >= 0                                        # rows a model actually predicted (fold -1 stays out)
    rows = []

    def add(table, dataset, key, metric, value, n):
        if n and np.isfinite(value):
            rows.append(dict(variant=variant, win=win, ncls=ncls, seed=seed, table=table, dataset=dataset,
                             key=str(key), metric=metric, value=float(value), n=int(n)))

    # a. simulation: macro-F1 and recall per class
    m = ok & (src == 'sim') & (y >= 0)
    add('a_sim', 'simulated', 'all', 'macro_f1', _f1(y[m], pred[m], list(range(ncls))), int(m.sum()))
    for c in range(ncls):
        add('a_sim', 'simulated', names[c], 'recall_pct', _recall(y[m], pred[m], c), int((m & (y == c)).sum()))
    # b. per real dataset: recall of every trusted class + macro-F1 over the classes present
    for d in sorted(set(ds[src == 'real'])):
        md = ok & (src == 'real') & (ds == d) & (y >= 0)
        if not md.any():
            continue
        present = sorted(set(y[md]))
        add('b_real', d, 'all', 'macro_f1', _f1(y[md], pred[md], present), int(md.sum()))
        for c in present:
            add('b_real', d, names[c], 'recall_pct', _recall(y[md], pred[md], c), int((md & (y == c)).sum()))
    # b2. WearGait-PD walking per person, controls vs Parkinson (group column of the stage 2 index)
    mw = ok & (ds == 'WearGait-PD') & (y == 0)
    if mw.any() and wg_groups:
        per = pd.DataFrame(dict(g=A['grp'][mw], ok=(pred[mw] == 0))).groupby('g').ok.mean() * 100
        grp = per.index.map(lambda g: wg_groups.get(g, 'unknown'))
        for gname in sorted(set(grp)):
            x = per[grp == gname]
            add('b_wg_person', 'WearGait-PD', gname, 'median_pct', float(x.median()), len(x))
            add('b_wg_person', 'WearGait-PD', gname, 'p10_pct', float(x.quantile(0.1)), len(x))
    # c. stairs on real people: recall and precision (Luo, PAMAP2)
    for d in ('Luo', 'PAMAP2'):
        md = ok & (ds == d) & (y >= 0)
        for c in (1, 2):
            add('c_stairs', d, names[c], 'recall_pct', _recall(y[md], pred[md], c), int((md & (y == c)).sum()))
            pm = ok & (ds == d) & (pred == c)      # precision over all windows of the dataset predicted as c
            add('c_stairs', d, names[c], 'precision_pct', 100.0 * float((y[pm] == c).mean()), int(pm.sum()))
    # d. walking called stairs, by speed / surface / recording
    stair = np.isin(pred, [1, 2])

    def called_stairs(mask, d, key):
        m = mask & ok & (y == 0)
        add('d_speed', d, key, 'walking_called_stairs_pct', 100.0 * float(stair[m].mean()), int(m.sum()))

    for r in sorted(set(A['rec'][(ds == 'WearGait-PD') & (y == 0)])):
        called_stairs((ds == 'WearGait-PD') & (A['rec'] == r), 'WearGait-PD', f'rec={r}')
    for col in ('speed_abs', 'speed_rel'):
        for v in sorted(x for x in set(A[col][(ds == 'Lencioni') & (y == 0)]) if x):
            called_stairs((ds == 'Lencioni') & (A[col] == v), 'Lencioni', f'{col}={v}')
    for v in sorted(x for x in set(A['surface'][(ds == 'Luo') & (y == 0)]) if x):
        called_stairs((ds == 'Luo') & (A['surface'] == v), 'Luo', f'surface={v}')
    # d2. what the Luo slopes (y = -1) are predicted as
    for lbl in ('slope_up', 'slope_down'):
        m = ok & (ds == 'Luo') & (y < 0) & (A['lab'] == lbl)
        for c in range(ncls):
            add('d_luo_slope', 'Luo', f'{lbl}->{names[c]}', 'pct', 100.0 * float((pred[m] == c).mean()), int(m.sum()))
    # e. Lencioni test stairs (y = -1, role == 'test')
    for lbl in ('stairs_up', 'stairs_down'):
        m = ok & (ds == 'Lencioni') & (A['role'] == 'test') & (A['lab'] == lbl)
        for c in (0, 1, 2):
            add('e_lencioni_test', 'Lencioni', f'{lbl}->{names[c]}', 'pct', 100.0 * float((pred[m] == c).mean()),
                int(m.sum()))
    # f. still (sitting + standing) and lying recall per dataset
    still_true = np.isin(y, [3, 4]) if ncls == 9 else (y == 3)
    still_pred = np.isin(pred, [3, 4]) if ncls == 9 else (pred == 3)
    ly = 5 if ncls == 9 else 4
    for d in sorted(set(ds)):
        md = ok & (ds == d) & still_true
        if md.any():
            add('f_still', d, 'still', 'recall_pct', 100.0 * float(still_pred[md].mean()), int(md.sum()))
        md = ok & (ds == d) & (y == ly)
        if md.any():
            add('f_still', d, 'lying', 'recall_pct', 100.0 * float((pred[md] == ly).mean()), int(md.sum()))
    # g. model size
    add('g_size', 'forest 20x d10', 'fold 0', 'nodes', float(nodes), 1)
    return rows


# ------------------------------------------------------------------ output
def md_table(df, fmt='{:.1f}'):
    """A markdown table from a DataFrame, without extra packages."""
    head = '| ' + ' | '.join([str(df.index.name or '')] + [str(c) for c in df.columns]) + ' |'
    sep = '|' + '---|' * (len(df.columns) + 1)
    out = [head, sep]
    for i, r in df.iterrows():
        cells = [fmt.format(v) if isinstance(v, (float, np.floating)) and np.isfinite(v) else ('' if pd.isna(v) else str(v))
                 for v in r]
        out.append('| ' + ' | '.join([str(i)] + cells) + ' |')
    return '\n'.join(out)


def pivot(rows, table, metric, index=('dataset', 'key'), run_key='run', col='value'):
    d = [r for r in rows if r['table'] == table and r['metric'] == metric]
    if not d:
        return None
    T = pd.DataFrame(d)
    T[run_key] = T.variant + ' ' + T.win.map(lambda w: f'{w:g}s') + ' ' + T.ncls.map(lambda n: f'{n}cls')
    if len(index) == 1:
        T['row'] = T[index[0]]
    else:
        T['row'] = T[index[0]] + T[index[1]].map(lambda k: '' if k in ('', 'all') else ' ' + k)
    P = T.pivot_table(index='row', columns=run_key, values=col, aggfunc='first')
    P.index.name = ' / '.join(index)
    return P


def write_outputs(rows, out_dir, log=print):
    """Per-seed rows -> D2_runs.csv; mean (sd) over the seeds -> D2_results.csv and D2_summary.md."""
    R = pd.DataFrame(rows)
    key = ['variant', 'win', 'ncls', 'seed', 'table', 'dataset', 'key', 'metric']
    runs_csv = os.path.join(out_dir, 'D2_runs.csv')
    if os.path.exists(runs_csv):                 # merge with earlier invocations at the per-seed level
        old = pd.read_csv(runs_csv)
        tri = set(map(tuple, R[key].drop_duplicates().itertuples(index=False)))
        keep = ~pd.Series(list(zip(*[old[c] for c in key])), index=old.index).isin(tri)
        R = pd.concat([old[keep], R], ignore_index=True)
        log(f'  merged: {int((~keep).sum())} old per-seed rows replaced, {len(R)} rows in total')
    R = R.sort_values(key)
    R.to_csv(runs_csv, index=False)
    agg = (R.groupby(['variant', 'win', 'ncls', 'table', 'dataset', 'key', 'metric'], dropna=False)
           .agg(value=('value', 'mean'), sd=('value', 'std'), nseeds=('value', 'size'), n=('n', 'first'))
           .reset_index())
    csv = os.path.join(out_dir, 'D2_results.csv')
    agg.to_csv(csv, index=False)
    recs = agg.to_dict('records')                 # the summary covers every run in the merged table
    runs = (agg[['variant', 'win', 'ncls']].drop_duplicates().sort_values(['ncls', 'win', 'variant'])
            .apply(lambda r: f"{r.variant} {r.win:g}s {int(r.ncls)}cls", axis=1).tolist())
    ns = sorted(set(agg.nseeds))

    def show(P, Q=None, fmt='{:.1f}'):
        if P is None:
            return '(no data)'
        if Q is None:
            return md_table(P, fmt=fmt)
        out = P.copy().astype(object)
        for c in P.columns:
            out[c] = [f'{v:.1f} ({s:.1f})' if np.isfinite(s) else f'{v:.1f}' for v, s in zip(P[c], Q[c])]
        return md_table(out)

    def pq(table, metric, index=('dataset', 'key')):
        return pivot(recs, table, metric, index=index), pivot(recs, table, metric, index=index, col='sd')

    parts = [f'# D2: 8 classes x window length x data variant, mean (sd) over {ns} seeds', '',
             f'{len(runs)} runs: ' + ', '.join(f'`{r}`' for r in runs), '',
             'All values in percent except macro-F1 (also percent) and the node count; format `mean (sd)`, '
             'sd = sample sd over the seeds. `still` = sitting + standing.', '',
             'Folds: every 8-class run uses the 2 s-file fold map. A 9-class run (V3 regression) uses the V3 map.', '',
             '## a. simulation: macro-F1 and recall per class', '']
    P, Q = pq('a_sim', 'macro_f1'); parts += ['### macro-F1 (simulated people)', '', show(P, Q), '']
    P, Q = pq('a_sim', 'recall_pct', index=('key',))
    parts += ['### recall per class (simulated people), %', '', show(P, Q), '']
    parts += ['## b. real datasets: recall per class and macro-F1, %', '']
    P, Q = pq('b_real', 'recall_pct'); parts += ['### recall per dataset and activity', '', show(P, Q), '']
    P, Q = pq('b_real', 'macro_f1'); parts += ['### macro-F1 over the classes present', '', show(P, Q), '']
    for metric, title in (('median_pct', 'median'), ('p10_pct', '10th percentile')):
        P, Q = pq('b_wg_person', metric, index=('key',))
        parts += [f'### WearGait-PD walking per person, {title}', '', show(P, Q), '']
    parts += ['## c. stairs on real people: recall and precision, %', '']
    for metric in ('recall_pct', 'precision_pct'):
        P, Q = pq('c_stairs', metric)
        parts += [f'### stairs {metric.replace("_pct", "")}', '', show(P, Q), '']
    parts += ['## d. walking called stairs, by speed / surface / recording, % of true walking windows', '']
    P, Q = pq('d_speed', 'walking_called_stairs_pct', index=('key',))
    parts += [show(P, Q), '']
    parts += ['## d2. Luo slopes (y = -1): what they are predicted as, % of the slope windows', '']
    P, Q = pq('d_luo_slope', 'pct', index=('key',))
    parts += [show(P, Q), '']
    parts += ['## e. Lencioni test stairs (not in training): prediction, %', '']
    P, Q = pq('e_lencioni_test', 'pct', index=('key',))
    parts += [show(P, Q), '']
    parts += ['## f. still (sitting + standing) and lying recall per dataset, %', '']
    P, Q = pq('f_still', 'recall_pct')
    parts += [show(P, Q), '']
    parts += ['## g. model size (nodes of the fold-0 forest)', '']
    P, Q = pq('g_size', 'nodes', index=('key',))
    parts += [show(P, Q, fmt='{:.0f}'), '']
    path = os.path.join(out_dir, 'D2_summary.md')
    open(path, 'w', encoding='utf-8').write('\n'.join(parts) + '\n')
    log(f'  saved {runs_csv}, {csv} and {path}')
    return agg


def main():
    ap = argparse.ArgumentParser(description='KNEIL V4 cross-validation (D1/D2)')
    ap.add_argument('--win', type=float, nargs='+', default=list(WINS), help='window lengths in seconds')
    ap.add_argument('--variants', nargs='+', default=list(VARIANTS), choices=list(VARIANTS))
    ap.add_argument('--seeds', type=int, nargs='+', default=[0], help='forest random_state values')
    ap.add_argument('--classes', type=int, nargs='+', default=[8], choices=[8, 9])
    ap.add_argument('--max-rows', type=int, default=None, help='subsample rows (stratified by dataset, seed 0)')
    ap.add_argument('--folds', choices=['auto', 'v4', 'v3'], default='auto',
                    help='auto: 8-class runs on the 2 s map, the 9-class V3recipe 2 s run on the V3 map')
    a = ap.parse_args()
    print(VERSION, flush=True)
    out_dir = config.out_dir('stepD', 'D2', 'smoke') if a.max_rows else config.out_dir('stepD', 'D2')
    log_path = os.path.join(out_dir, 'cv_v4_log.txt')
    with S1.Tee(log_path):
        print(f'{VERSION} | {S3.VERSION} | {S4.VERSION} | {config.VERSION} | {np.datetime64("now", "s")}')
        print(f'V4_OUT {config.V4_OUT}  out {out_dir}  win {a.win}  variants {a.variants}  seeds {a.seeds}  '
              f'classes {a.classes}  max_rows {a.max_rows}  folds {a.folds}')
        gf4 = fold_map_v4(2)
        gf3, f3 = fold_map_v3()
        wg = S3._wg_groups(config.DATA_ROOT)
        rows, t0, cache = [], time.time(), {}

        def get_A(win):
            if win not in cache:
                A = load(win)
                cache[win] = subsample(A, a.max_rows) if a.max_rows else A
            return cache[win]

        for ncls in a.classes:
            for variant in a.variants:
                for win in a.win:
                    A = get_A(win)
                    use_v3 = (a.folds == 'v3') or (a.folds == 'auto' and ncls == 9 and variant == 'V3recipe' and win == 2)
                    fold = folds_v3_extended(A, gf3, gf4) if use_v3 else folds_for(A, gf4)
                    if use_v3:
                        n_old = len(f3)
                        ok_first = not np.isin(A['ds'][:n_old], NEW_DS).any()
                        same = int((fold[:n_old] == f3).sum()) if len(fold) >= n_old and ok_first else -1
                        print(f'  folds: old rows first {ok_first}; {same}/{n_old} old rows carry the V3 fold')
                    print(f'\n=== {variant} | {win:g} s | {ncls} classes | {len(fold)} rows | folds '
                          f'{np.bincount(fold[fold >= 0], minlength=5).tolist()}')
                    for seed in a.seeds:
                        r = run_one(A, variant, win, ncls, fold, out_dir, seed=seed)
                        rows += tables(A, ncls, r['pred'], r['nodes'], variant, win, wg, seed=seed)
        T = write_outputs(rows, out_dir)
        print(f'\nruns: {len(T[["variant", "win", "ncls"]].drop_duplicates())} x {len(a.seeds)} seeds, '
              f'table rows: {len(T)}, total {(time.time() - t0) / 60:.1f} min')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
