"""
KNEIL stage 3: test V2 on real people, train V3, export it for the chip.   v1.0, Nov 2026
3a  Windows: every signal -> the chip's 6 Hz input low-pass and its 20 C features (2 s windows, 1 s hop, 50 Hz).
    Sources: simulated (v1.6 synthetic + Camargo implant-site replay), Caicedo virtual implant, the real implant-site
    data of stage 2 (both legs), and the spacer personas if their recordings are on Drive.
3b  5-fold cross-validation BY PERSON: each dataset's people are split into 5 folds (Marpino: by group, because its
    files do not say who is who; a Camargo subject's personas share that subject's fold). Every person is tested once,
    by a model that never saw them. Variants: V2 (as now), V3 (+ real data), V3 + tilt variation (+-5 deg), and
    V3 + tilt + personas at weight 0.5.
3c  Report per dataset and activity, plus what the chip says about activities outside its 9 classes.
3d  The chosen variant is trained on everyone and exported (forest + tree, float thresholds, test vectors, host test)
    to KNEIL_results/tinyml_final_v3_lp6.
"""
import glob, json, os, re, shutil, subprocess, sys, time
import numpy as np
import pandas as pd

import stage01 as S1
import stage2 as S2

VERSION = 'stage3 1.2'
FS, W, H, LP = 50, 100, 50, 6.0
TINY = '/content/kneil_tinyml'
T = None
DEVICE = ['walking', 'stairs_up', 'stairs_down', 'sitting', 'standing', 'lying', 'sit_to_stand', 'stand_to_sit', 'bed_transfer']
TO_DEVICE = {'walking': 'walking', 'stairs_up': 'stairs_up', 'stairs_down': 'stairs_down', 'sitting': 'sitting', 'standing': 'standing',
             'lying': 'lying', 'balance': 'standing'}
TRUSTED = {'WearGait-PD': {'walking', 'standing', 'sitting'}, 'Marpino': {'walking', 'standing'}, 'CeTI': {'walking', 'standing', 'sitting'},
           'KneE-PAD': {'walking'}, 'PAMAP2': {'walking', 'standing', 'sitting', 'lying', 'stairs_up', 'stairs_down'},
           'MHEALTH': {'walking', 'standing', 'sitting', 'lying'}}
VARIANTS = {'V2': dict(real=False, tilt=False, personas=False), 'V3': dict(real=True, tilt=False, personas=False),
            'V3+tilt': dict(real=True, tilt=True, personas=False),
            'V3 real x0.5': dict(real=True, tilt=False, personas=False, real_w=0.5),
            'V3 real x0.3': dict(real=True, tilt=False, personas=False, real_w=0.3),
            'V3+tilt+personas': dict(real=True, tilt=True, personas=True)}
SIM_ONLY = ['sit_to_stand', 'stand_to_sit', 'bed_transfer']     # classes only the simulation contains
MAX_SIM_ONLY_LOSS = 5.0                                          # points of recall a variant may lose on them


def _ensure(tiny=TINY):
    """Connect to the chip library's training tools (also after a module reload in a later cell)."""
    global T
    if T is None:
        sys.path.insert(0, os.path.join(tiny, 'tools'))
        import train_kneil_tinyml as tk
        T = tk
    return T


def init_tinyml(tiny=TINY):
    _ensure(tiny)
    assert list(T.CLASSES) == DEVICE, f'unexpected class list {T.CLASSES}'
    lib = T.c_features_lib()
    err = T.lowpass_parity(lib, FS, LP)
    print(f'chip feature code built; C vs Python 6 Hz low-pass: max difference {err:.2e} g')
    assert err < 1e-4
    return lib


def rot_y(a, deg):
    t = np.radians(deg); c, s = np.cos(t), np.sin(t)
    return np.c_[c * a[:, 0] + s * a[:, 2], a[:, 1], -s * a[:, 0] + c * a[:, 2]]


def stream_windows(lib, a50, codes=None):
    a = T.apply_lowpass(np.asarray(a50, float), FS, LP).astype(np.float32)
    X, labs = [], []
    for s in range(0, len(a) - W + 1, H):
        X.append(T.features(lib, a[s:s + W, 0], a[s:s + W, 1], a[s:s + W, 2], FS))
        if codes is not None:
            v, c = np.unique(codes[s:s + W], return_counts=True); j = np.argmax(c)
            labs.append(int(v[j]) if c[j] >= 0.6 * W else -1)
    return np.array(X, np.float32).reshape(-1, T.NF), (np.array(labs) if codes is not None else None)


class Rows:
    def __init__(self):
        self.d = {k: [] for k in ('X', 'Xr', 'y', 'src', 'ds', 'grp', 'task', 'lab')}
    def add(self, X, y, src, ds, grp, task, lab, Xr=None):
        n = len(X)
        self.d['X'].append(X); self.d['Xr'].append(Xr if Xr is not None else np.full_like(X, np.nan)); self.d['y'].append(np.asarray(y, np.int16))
        for k, v in (('src', src), ('ds', ds), ('grp', grp), ('task', task)):
            self.d[k].append(np.full(n, v, dtype=object) if np.isscalar(v) or isinstance(v, str) else np.asarray(v, object))
        self.d['lab'].append(np.asarray(lab, object))
    def arrays(self):
        return {k: (np.vstack(v) if k in ('X', 'Xr') else np.concatenate(v)) for k, v in self.d.items()}


def load_sim(root, lib, R, log=print):
    res = os.path.join(root, 'KNEIL_results'); local = os.path.join(S1.LOCAL_CACHE, 'sim')
    v16, cam = os.path.join(local, 'v16'), os.path.join(local, 'cam')
    import zipfile
    if not os.path.isdir(v16):
        with zipfile.ZipFile(S1.local_copy(os.path.join(res, 'kneil_dataset_v1_6.zip'), 'zips')) as z:
            for n in z.namelist():
                if n.endswith('.csv'):
                    os.makedirs(v16, exist_ok=True); open(os.path.join(v16, os.path.basename(n)), 'wb').write(z.read(n))
    if not os.path.isdir(cam):
        os.makedirs(cam, exist_ok=True)
        for zp in sorted(glob.glob(os.path.join(res, 'dataset', 'ab*.zip'))):
            with zipfile.ZipFile(S1.local_copy(zp, 'zips')) as z:
                for n in z.namelist():
                    if n.endswith('.csv'):
                        open(os.path.join(cam, os.path.basename(n)), 'wb').write(z.read(n))
    X, y, g, raw = T.load_windows(lib, [v16, cam], FS, lowpass=LP)
    ds = np.where(np.char.startswith(g.astype(str), 'P'), 'v1.6 synthetic', 'Camargo simulated')
    R.add(X.astype(np.float32), y, 'sim', ds, g.astype(object), 'simulated', [DEVICE[int(c)] for c in y])
    log(f'  simulated: {len(y)} windows ({(ds == "v1.6 synthetic").sum()} v1.6 synthetic, {(ds != "v1.6 synthetic").sum()} Camargo)')
    return raw


def load_caicedo(root, lib, R, log=print):
    p = os.path.join(root, 'KNEIL_results', 'external', 'caicedo_implant_streams.npz')
    if not os.path.exists(p):
        log('  Caicedo streams not found (KNEIL_results/external/caicedo_implant_streams.npz): skipped'); return
    S = np.load(S1.local_copy(p, 'cai'))
    n = 0
    for k in S.files:
        subj = re.search(r'Subject(\d+)', k).group(1)
        X, _ = stream_windows(lib, S[k])
        R.add(X, np.zeros(len(X)), 'caicedo', 'Caicedo older adults', f'caicedo:{int(subj)}', 'walking', ['walking'] * len(X)); n += len(X)
    log(f'  Caicedo: {n} walking windows from {len(S.files)} streams')


def load_stage2(root, lib, R, rng, log=print):
    out = os.path.join(root, 'KNEIL_results', 'virtual_implant')
    for ip in sorted(glob.glob(os.path.join(out, 'stage2_index_*.csv'))):
        if ip.endswith('_all.csv'):
            continue
        I = pd.read_csv(ip); ds = I.dataset.iloc[0]
        flagged = int((~I.plausible.astype(bool)).sum()); I = I[I.plausible.astype(bool)]
        n_tr = n_out = 0
        for fn, rows in I.groupby('file'):
            Z = np.load(S1.local_copy(os.path.join(out, 'stage2', ds, fn), 's2'))
            for r in rows.itertuples():
                prefix = next((t for t in (str(r.task), 'all') if f'{t}|{r.side}|implant' in Z.files), None)
                if prefix is None:                         # PAMAP2/MHEALTH store their whole protocol under 'all'
                    continue
                a = Z[f'{prefix}|{r.side}|implant']
                lk = f'{prefix}|labels'
                codes = Z[lk][:len(a)] if lk in Z.files else np.full(len(a), S2.CODE.get(r.task_label, S2.CODE['other']), np.int16)
                X, lw = stream_windows(lib, a, codes)
                Xr, _ = stream_windows(lib, rot_y(a, rng.uniform(-5, 5)))
                names = [S2.LABELS[c] if c >= 0 else 'mixed' for c in lw]
                y = [DEVICE.index(TO_DEVICE[nm]) if nm in TRUSTED.get(ds, set()) and nm in TO_DEVICE else -1 for nm in names]
                grp = f'{ds}:{r.group}' if ds == 'Marpino' else f'{ds}:{r.person}'
                R.add(X, y, 'real', ds, grp, str(r.task_label), names, Xr=Xr)
                n_tr += sum(v >= 0 for v in y); n_out += sum(v < 0 for v in y)
            shutil.rmtree(os.path.join(S1.LOCAL_CACHE, 's2'), ignore_errors=True)
        log(f'  {ds}: {n_tr} windows with a chip class, {n_out} outside the chip classes; {flagged} flagged recordings left out')


def load_personas(root, lib, R, log=print):
    res = os.path.join(root, 'KNEIL_results')
    cands = [d for d in glob.glob(os.path.join(res, '**', '*persona*'), recursive=True) if os.path.isdir(d)]
    for d in cands:
        csvs = glob.glob(os.path.join(d, '*.csv'))
        if len(csvs) >= 10 and 'acc_x_g' in pd.read_csv(csvs[0], nrows=0).columns:
            X, y, g, _ = T.load_windows(lib, [d], FS, lowpass=LP)
            grp = [(re.search(r'(ab\d+)', str(x), re.I).group(1).lower() if re.search(r'(ab\d+)', str(x), re.I) else str(x)) for x in g]
            R.add(X.astype(np.float32), y, 'persona', 'spacer personas', np.array(grp, object), 'persona', [DEVICE[int(c)] for c in y])
            log(f'  spacer personas: {len(y)} windows from {d}'); return True
    log('  spacer personas: no recordings found under KNEIL_results (only the diagnosis files are on Drive); the persona variant is skipped.\n'
        '    To include it, copy the folder with the persona CSV files (columns acc_x_g, acc_y_g, acc_z_g, activity) into KNEIL_results/spacer_personas/')
    return False


def build_windows(root, lib, cache_dir, log=print):
    """All windows, cached (local + Drive) so that a new session does not recompute them."""
    os.makedirs(cache_dir, exist_ok=True)
    cpath = os.path.join(cache_dir, 'stage3_windows.npz')
    if os.path.exists(cpath):
        log(f'windows: loading the cache {cpath} (delete it to rebuild)')
        Z = np.load(S1.local_copy(cpath, 'w3'), allow_pickle=True)
        A = {k: Z[k] for k in Z.files if k != 'raw_sim'}
        return A, Z['raw_sim']
    rng = np.random.default_rng(0); R = Rows(); t0 = time.time()
    raw = load_sim(root, lib, R, log); load_caicedo(root, lib, R, log); load_stage2(root, lib, R, rng, log); load_personas(root, lib, R, log)
    A = R.arrays()
    rng = np.random.default_rng(1); sel = []
    for c in range(9):
        idx = np.flatnonzero(A['y'][:len(raw)] == c); sel += list(rng.choice(idx, min(3, len(idx)), replace=False))
    raw_sim = np.array([raw[i] for i in sel], np.float32)
    A['raw_sel'] = np.array(sel)
    local = os.path.join(S1.LOCAL_CACHE, 'stage3_windows.npz')
    np.savez_compressed(local, raw_sim=raw_sim, **A)
    S1.with_retry(lambda: shutil.copyfile(local, cpath), 'save the window cache')
    log(f'windows: {len(A["y"])} in {(time.time() - t0) / 60:.1f} min, cached to {cpath}')
    return A, raw_sim


def assign_folds(A, k=5, seed=0):
    fold = np.full(len(A['y']), -1, int); gf = {}
    rng = np.random.default_rng(seed)
    order = [('sim', None), ('caicedo', None), ('real', None), ('persona', None)]
    for src, _ in order:
        m = A['src'] == src
        for ds in sorted(set(A['ds'][m])):
            groups = sorted(set(A['grp'][m & (A['ds'] == ds)]) - set(gf))
            rng.shuffle(groups)
            for i, g in enumerate(groups):
                gf[g] = i % k
    for i, g in enumerate(A['grp']):
        fold[i] = gf[g]
    return fold, gf


def training_set(A, mask, variant):
    """Rows, labels and weights of one variant (mask selects the training people)."""
    v = VARIANTS[variant]; y = A['y']; src = A['src']
    ok = mask & (y >= 0)
    sim = ok & (src == 'sim'); cai = ok & (src == 'caicedo'); real = ok & (src == 'real') if v['real'] else np.zeros_like(ok)
    per = ok & (src == 'persona') if v['personas'] else np.zeros_like(ok)
    Xs, ys, ws = [A['X'][sim]], [y[sim]], [np.ones(sim.sum())]
    if cai.sum():
        Xs.append(A['X'][cai]); ys.append(y[cai]); ws.append(np.full(cai.sum(), 0.3 * (y[sim] == 0).sum() / cai.sum()))
    if real.sum():
        n_sim = sim.sum(); dss = sorted(set(A['ds'][real])); sz = {d: (real & (A['ds'] == d)).sum() for d in dss}
        tot = sum(np.sqrt(v_) for v_ in sz.values())
        for d in dss:
            m = real & (A['ds'] == d); wd = v.get('real_w', 1.0) * n_sim * np.sqrt(sz[d]) / tot / sz[d]
            if v['tilt']:
                Xs += [A['X'][m], A['Xr'][m]]; ys += [y[m], y[m]]; ws += [np.full(m.sum(), wd / 2), np.full(m.sum(), wd / 2)]
            else:
                Xs.append(A['X'][m]); ys.append(y[m]); ws.append(np.full(m.sum(), wd))
    if per.sum():
        Xs.append(A['X'][per]); ys.append(y[per]); ws.append(np.full(per.sum(), 0.5))
    return np.vstack(Xs), np.concatenate(ys).astype(int), np.concatenate(ws)


def make_model(name='forest 20x d10'):
    m = T.MODELS[name]()
    if hasattr(m, 'n_jobs'):
        m.n_jobs = -1
    return m


def cross_validate(A, fold, variants, out_dir, log=print):
    ppath = os.path.join(out_dir, 'stage3_cv_predictions.npz')
    P = dict(np.load(S1.local_copy(ppath, 'cvp'))) if os.path.exists(ppath) else {}
    for v in variants:
        if v in P and (P[v] > -2).all():
            log(f'  {v}: already cross-validated'); continue
        pred = np.full(len(A['y']), -2, np.int8); t0 = time.time()
        for k in range(5):
            Xt, yt, wt = training_set(A, fold != k, v)
            m = make_model().fit(Xt, yt, sample_weight=wt)
            te = fold == k
            pred[te] = m.predict(A['X'][te])
            log(f'  {v} fold {k + 1}/5: trained on {len(yt)} rows, tested on {te.sum()} windows ({time.time() - t0:.0f} s)')
        P[v] = pred
        local = os.path.join(S1.LOCAL_CACHE, 'stage3_cv_predictions.npz'); np.savez_compressed(local, **P)
        S1.with_retry(lambda: shutil.copyfile(local, ppath), 'save CV predictions')
    return P


def _f1(y, p, labels):
    from sklearn.metrics import f1_score
    return float(f1_score(y, p, labels=labels, average='macro', zero_division=0)) if len(y) else np.nan


def _recall(y, p, c):
    m = y == c
    return 100 * float((p[m] == c).mean()) if m.any() else np.nan


def _wg_groups(root):
    p = os.path.join(root, 'KNEIL_results', 'virtual_implant', 'stage2_index_WearGait-PD.csv')
    if not os.path.exists(p):
        return {}
    I = pd.read_csv(p)
    return {f'WearGait-PD:{r.person}': r.group for r in I.drop_duplicates('person').itertuples()}


def report(A, P, out_dir, root=None, log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    variants = [v for v in VARIANTS if v in P]
    y, ds, src = A['y'], A['ds'], A['src']
    rows = []
    for v in variants:
        p = P[v]; r = dict(variant=v)
        m = (src == 'sim') & (y >= 0); r['simulated macro-F1'] = _f1(y[m], p[m], list(range(9)))
        m = src == 'caicedo'; r['Caicedo walking %'] = 100 * float((p[m] == 0).mean()) if m.any() else np.nan
        for d in sorted(set(ds[src == 'real'])):
            m = (ds == d) & (y >= 0)
            r[f'{d} F1'] = _f1(y[m], p[m], sorted(set(y[m])))
            r[f'{d} walk %'] = _recall(y[m], p[m], 0)
        rows.append(r)
    Tb = pd.DataFrame(rows).set_index('variant')
    log('\n=== STAGE 3: cross-validated by person (every person tested by a model that never saw them) ===')
    log(Tb.round(3).T.to_string())
    # recall per class on the simulated people
    m = (src == 'sim') & (y >= 0)
    S = pd.DataFrame({v: [_recall(y[m], P[v][m], c) for c in range(9)] for v in variants}, index=DEVICE).round(1)
    log('\nrecall per class, SIMULATED people (%):\n' + S.to_string())
    # recall per dataset and class on real people
    rr = []
    for d in sorted(set(ds[src == 'real'])):
        for c in sorted(set(y[(ds == d) & (y >= 0)])):
            m = (ds == d) & (y == c)
            rr.append(dict(dataset=d, activity=DEVICE[c], windows=int(m.sum()), **{v: round(_recall(y[m], P[v][m], c), 1) for v in variants}))
    Rr = pd.DataFrame(rr)
    log('\nrecall per dataset and activity, REAL people (%):\n' + Rr.to_string(index=False))
    # sitting vs standing: would one 'upright and still' class work?
    up = []
    for d in sorted(set(ds[src == 'real'])):
        for c in (3, 4):
            m = (ds == d) & (y == c)
            if m.sum() >= 20:
                up.append(dict(dataset=d, activity=DEVICE[c], windows=int(m.sum()),
                               **{v: round(100 * float(np.isin(P[v][m], [3, 4]).mean()), 1) for v in variants}))
    if up:
        log('\nreal sitting and standing called EITHER sitting or standing (%) -- would one "upright and still" class work?\n'
            + pd.DataFrame(up).to_string(index=False))
    # controls vs Parkinson (groups from the stage 2 index)
    G = _wg_groups(root) if root else {}
    wg = (ds == 'WearGait-PD') & (y == 0)
    if wg.any() and G:
        q = []
        for v in variants:
            per = pd.DataFrame(dict(g=A['grp'][wg], ok=P[v][wg] == 0)).groupby('g').ok.mean() * 100
            grp = per.index.map(lambda g: G.get(g, 'unknown'))
            row = dict(variant=v)
            for gname in sorted(set(grp)):
                x = per[grp == gname]
                row[f'{gname} n'] = len(x); row[f'{gname} median'] = round(x.median(), 1); row[f'{gname} p10'] = round(x.quantile(0.1), 1)
            q.append(row)
        log('\nWearGait-PD walking recognised per person (%; median and 10th percentile; groups from the stage 2 index)\n'
            + pd.DataFrame(q).to_string(index=False))
    # outside the chip classes, for V2 and the best real-data variant
    real_f1 = [c for c in Tb.columns if c.endswith(' F1') and not c.startswith('simulated')]
    Tb['mean real F1'] = Tb[real_f1].mean(1)
    loss = {v: max(0.0, max(S.loc[c, 'V2'] - S.loc[c, v] for c in SIM_ONLY)) if 'V2' in S else 0.0 for v in variants}
    Tb['worst loss on sim-only classes'] = pd.Series(loss)
    ok = Tb[Tb['worst loss on sim-only classes'] <= MAX_SIM_ONLY_LOSS]
    score = ok['mean real F1'] + ok['Caicedo walking %'].fillna(0) / 100
    best = score.idxmax() if len(score) else 'V2'
    log(f'\nworst recall loss on {SIM_ONLY} vs V2 (points): ' + ', '.join(f'{v} {loss[v]:.1f}' for v in variants))
    log(f'RECOMMENDED: {best} (best mean real-data F1 + Caicedo walking among variants losing at most {MAX_SIM_ONLY_LOSS:g} points '
        f'on the simulation-only classes). Nothing is exported until you set FINAL_VARIANT.')
    p = P[best]; m = (src == 'real') & (y < 0)
    if m.any():
        O = pd.DataFrame(dict(dataset=ds[m], activity=A['lab'][m], pred=[DEVICE[int(c)] for c in p[m]]))
        tab = O.groupby(['dataset', 'activity']).pred.value_counts(normalize=True).mul(100).round(0).rename('%').reset_index()
        top = tab.sort_values('%', ascending=False).groupby(['dataset', 'activity']).head(3)
        top = top.merge(O.groupby(['dataset', 'activity']).size().rename('windows').reset_index(), on=['dataset', 'activity'])
        top = top[(top.windows >= 30) & ~top.activity.isin(['mixed', 'unknown', 'other'])].sort_values(['dataset', 'activity', '%'], ascending=[True, True, False])
        log(f'\n{best}: what the chip says about activities outside its classes (top 3, % of windows)\n' + top.to_string(index=False))
    for name, df in (('stage3_results.csv', Tb), ('stage3_recall_simulated.csv', S), ('stage3_recall_real.csv', Rr.set_index(['dataset', 'activity']))):
        df.to_csv(os.path.join(S1.LOCAL_CACHE, name))
        S1.with_retry(lambda name=name: shutil.copyfile(os.path.join(S1.LOCAL_CACHE, name), os.path.join(out_dir, name)), f'save {name}')
    fig, ax = plt.subplots(1, 3, figsize=(18, 4.8), gridspec_kw=dict(width_ratios=[1.1, 1.1, 1]))
    cols = [c for c in Tb.columns if c.endswith(' F1') and not c.startswith(('mean', 'simulated'))]
    Tb[cols].T.plot.bar(ax=ax[0]); ax[0].set_ylim(0, 1); ax[0].set_title('a  macro-F1 per real dataset', loc='left')
    ax[0].tick_params(axis='x', labelrotation=30, labelsize=8); ax[0].legend(fontsize=7)
    wc = [c for c in Tb.columns if c.endswith('walk %') or c.startswith('Caicedo')]
    Tb[wc].T.plot.bar(ax=ax[1], legend=False); ax[1].set_ylim(0, 100); ax[1].set_title('b  walking recognised (%)', loc='left')
    ax[1].tick_params(axis='x', labelrotation=30, labelsize=8)
    S.plot.bar(ax=ax[2], legend=False); ax[2].set_ylim(0, 100); ax[2].set_title('c  recall per class, simulated people (%)', loc='left')
    ax[2].tick_params(axis='x', labelrotation=30, labelsize=8)
    fig.tight_layout(); local = os.path.join(S1.LOCAL_CACHE, 'stage3_summary.png'); fig.savefig(local, dpi=130)
    S1.with_retry(lambda: shutil.copyfile(local, os.path.join(out_dir, 'stage3_summary.png')), 'save figure')
    return best, Tb


def export_final(A, raw_sim, variant, root, results=None, tiny=TINY, log=print):
    import emlearn
    Xt, yt, wt = training_set(A, np.ones(len(A['y']), bool), variant)
    log(f'final {variant}: training on {len(yt)} rows from everyone ...')
    models = {}
    for name, fname in (('forest 20x d10', 'kneil_model_forest.h'), ('tree d10', 'kneil_model_tree.h')):
        models[name] = make_model(name).fit(Xt, yt, sample_weight=wt)
        emlearn.convert(models[name], method='inline', dtype='float').save(file=os.path.join(tiny, 'include', fname), name='kneil_model')
    srcs = sorted(set(A['ds'][(A['src'] == 'real')])) if VARIANTS[variant]['real'] else []
    dset = 'kneil_dataset_v1_6; kneil_camargo_v1_3; caicedo_2020' + (('; real implant-site (' + ', '.join(srcs) + ')') if srcs else '') + f'; {variant}'
    open(os.path.join(tiny, 'include', 'kneil_model_info.h'), 'w').write(
        '/* Written by stage3.py (KNEIL virtual implant) together with the model headers. */\n#ifndef KNEIL_MODEL_INFO_H\n#define KNEIL_MODEL_INFO_H\n'
        f'#define KNEIL_MODEL_FS_HZ {FS}          /* the models were trained on {FS} Hz data */\n#define KNEIL_MODEL_N_FEATURES {T.NF}\n'
        f'#define KNEIL_MODEL_LOWPASS_HZ {LP:g}      /* input low-pass used in training, applied on the device (0 = off) */\n'
        f'#define KNEIL_MODEL_DATASET "{dset}"\n#endif\n')
    sel = A['raw_sel']
    feat = np.array([T.features(T_lib(), w[:, 0], w[:, 1], w[:, 2], FS) for w in raw_sim], np.float32)
    assert np.allclose(feat, A['X'][sel], atol=1e-5), 'test-vector features differ from the training features'
    vote = np.zeros((len(feat), 9), int)
    for e in models['forest 20x d10'].estimators_:
        vote[np.arange(len(feat)), e.predict(feat).astype(int)] += 1
    np.savez(os.path.join(tiny, 'tools', 'test_vectors.npz'), raw=raw_sim, feat=feat, label=A['y'][sel],
             pred_forest=vote.argmax(1), pred_tree=models['tree d10'].predict(feat))
    subprocess.check_call([sys.executable, os.path.join(tiny, 'tools', 'gen_test_vectors.py')])
    r = subprocess.run([sys.executable, os.path.join(tiny, 'tests', 'run_host_test.py')], capture_output=True, text=True, cwd=tiny)
    log(r.stdout.strip()[-1500:]); passed = 'HOST TEST: PASS' in r.stdout
    nodes = {k: T.n_nodes(m) for k, m in models.items()}
    out = os.path.join(root, 'KNEIL_results', 'tinyml_final_v3_lp6'); os.makedirs(out, exist_ok=True)
    files = [os.path.join(tiny, 'include', f) for f in ('kneil_model_forest.h', 'kneil_model_tree.h', 'kneil_model_info.h')] + \
            [os.path.join(tiny, 'tests', 'kneil_test_vectors.h')]
    for f in files:
        S1.with_retry(lambda f=f: shutil.copyfile(f, os.path.join(out, os.path.basename(f))), f'copy {os.path.basename(f)}')
    info = dict(version=VERSION, variant=variant, rows=int(len(yt)), nodes=nodes, host_test='PASS' if passed else 'FAILED',
                forest_header_kB=round(os.path.getsize(files[0]) / 1024, 1), dataset=dset,
                cross_validation=(results.reset_index().to_dict(orient='records') if results is not None else None))
    open(os.path.join(S1.LOCAL_CACHE, 'v3_info.json'), 'w').write(json.dumps(info, indent=1, default=float))
    S1.with_retry(lambda: shutil.copyfile(os.path.join(S1.LOCAL_CACHE, 'v3_info.json'), os.path.join(out, 'v3_info.json')), 'save info')
    log(f"exported to {out}: forest {nodes['forest 20x d10']} nodes ({info['forest_header_kB']} kB header), tree {nodes['tree d10']} nodes; "
        f"host test {info['host_test']}")
    return passed


_LIB = None


def T_lib():
    global _LIB
    if _LIB is None:
        _LIB = T.c_features_lib()
    return _LIB


if os.path.isdir(os.path.join(TINY, 'tools')):
    _ensure()
