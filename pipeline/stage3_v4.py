"""
KNEIL stage 3 V4: one window builder for any window length.   stage3_v4 1.1, 16 Nov 2026

The V3 window cache (stage3.build_windows) is fixed to 2 s. This module rebuilds the same rows for a window of
W = 50 * W_s samples (hop always 1 s) and adds the V4 stage 2 datasets (Luo, Lencioni) and extra per-window metadata.

Adapted from stage3.py (the old modules are not modified): stream_windows, load_sim, load_caicedo and load_stage2 with
the window length as an argument. The chip library and the C features come from stage3 (stage3.init_tinyml, stage3.T),
the class list and label mappings from stage3 / stage2 / stage2_v4 (no copies).

1.1 adds the `stream` array: one int id per recording and leg, increasing in the order the rows are added; the rows of
one stream are contiguous and in time order (needed by the stairs evidence rule). Output goes to
<KNEIL_V4_OUT>/stepD/windows_v11/ so the D0 files stay untouched.

Simulation windows below min_share are SKIPPED (not kept with -1), like train_kneil_tinyml.load_windows.

Output: <KNEIL_V4_OUT>/stepD/windows_v11/windows_W<W_s>s.npz with X, Xr, y, src, ds, grp, task, lab (the V3 keys) plus
rec, surface, speed_abs, speed_rel, adult, role, stream and the scalar W. If the file exists it is loaded (resume).
CLI: python pipeline/stage3_v4.py --win 2 [--max-people 2]
"""
import argparse
import glob
import os
import re
import shutil
import time
import zipfile
from fractions import Fraction

import numpy as np
import pandas as pd
from scipy.signal import resample_poly

import config
import stage01 as S1
import stage2 as S2
import stage3 as S3
import stage2_v4 as S2V

VERSION = 'stage3_v4 1.1'
FS, H, LP = 50, 50, 6.0
WINDOWS_DIR = 'windows_v11'                 # 1.1 output folder (the D0 files in stepD/windows are kept)
TINY = config.TINYML
T = S3.T if S3.T is not None else S3._ensure()
DEVICE = S3.DEVICE
TO_DEVICE = S3.TO_DEVICE
TRUSTED = S3.TRUSTED
LUO_TRUSTED = ('walking', 'stairs_up', 'stairs_down', 'standing')      # step D decision (task D0)
META = ('rec', 'surface', 'speed_abs', 'speed_rel', 'adult', 'role')   # extra per-window metadata, '' = not known


def _s(v):
    """An index value as text; '' when it is missing (NaN / NA / None), so the metadata holds text only."""
    if v is None:
        return ''
    try:
        if pd.isna(v):
            return ''
    except (TypeError, ValueError):
        pass
    return str(v)


class Rows:
    """Row collector: the V3 arrays, the extra metadata and the stream id (one per recording and leg)."""

    def __init__(self):
        self.d = {k: [] for k in ('X', 'Xr', 'y', 'src', 'ds', 'grp', 'task', 'lab', 'stream') + META}
        self.sid = 0                                        # next stream id, one per add() call

    def add(self, X, y, src, ds, grp, task, lab, Xr=None, **meta):
        n = len(X)
        self.d['X'].append(X)
        self.d['Xr'].append(Xr if Xr is not None else np.full_like(X, np.nan))
        self.d['y'].append(np.asarray(y, np.int16))
        self.d['stream'].append(np.full(n, self.sid, np.int32))
        self.sid += 1
        for k, v in (('src', src), ('ds', ds), ('grp', grp), ('task', task)):
            self.d[k].append(np.full(n, v, dtype=object) if np.isscalar(v) or isinstance(v, str) else np.asarray(v, object))
        self.d['lab'].append(np.asarray(lab, object))
        for k in META:
            v = meta.get(k, '')
            self.d[k].append(np.full(n, v, dtype=object) if np.isscalar(v) or isinstance(v, str) else np.asarray(v, object))

    def arrays(self):
        return {k: (np.vstack(v) if k in ('X', 'Xr') else np.concatenate(v)) for k, v in self.d.items()}


def stream_windows(lib, a50, codes=None, W=100, H=50):
    """stage3.stream_windows with the window length as an argument (6 Hz causal filter on the stream, windows from
    sample 0, label = majority if >= 60 % of the window else -1)."""
    a = T.apply_lowpass(np.asarray(a50, float), FS, LP).astype(np.float32)
    X, labs = [], []
    for s in range(0, len(a) - W + 1, H):
        X.append(T.features(lib, a[s:s + W, 0], a[s:s + W, 1], a[s:s + W, 2], float(FS)))
        if codes is not None:
            v, c = np.unique(codes[s:s + W], return_counts=True); j = int(np.argmax(c))
            labs.append(int(v[j]) if c[j] >= 0.6 * W else -1)
    return np.array(X, np.float32).reshape(-1, T.NF), (np.array(labs, np.int64) if codes is not None else None)


def load_windows_w(lib, dirs, fs, W, H, min_share=0.6, lowpass=0.0, people=None, files_out=False):
    """Copy of train_kneil_tinyml.load_windows with W and H as arguments (fs, min_share, lowpass kept).
    `people` (optional) keeps only the files whose person id (before the first '_') is in the set, for test runs.
    `files_out` (optional) also returns the source file name per window (to build one stream id per recording)."""
    X, y, g, raw, files = [], [], [], [], []
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, '*.csv'))):
            if os.path.basename(f) == 'patients.csv':
                continue
            pid = os.path.basename(f).split('_')[0]
            if people is not None and pid not in people:
                continue
            df = pd.read_csv(f, usecols=['acc_x_g', 'acc_y_g', 'acc_z_g', 'activity'])
            a = df[['acc_x_g', 'acc_y_g', 'acc_z_g']].values.astype(np.float64)
            lab = df['activity'].map(T.MAP).fillna(-1).values.astype(int)
            if fs != 100:                                  # any integer rate, e.g. 50, 52, 25, 26
                fr = Fraction(fs, 100); a = resample_poly(a, fr.numerator, fr.denominator, axis=0)
                lab = lab[np.minimum(np.round(np.arange(len(a)) * 100.0 / fs).astype(int), len(lab) - 1)]
            if lowpass > 0:
                a = T.apply_lowpass(a, fs, lowpass)
            a = a.astype(np.float32)
            for s in range(0, len(a) - W + 1, H):
                l = lab[s:s + W]; vals, cnt = np.unique(l, return_counts=True); j = int(np.argmax(cnt))
                if vals[j] < 0 or cnt[j] < min_share * W:   # simulation windows below the share are skipped
                    continue
                X.append(T.features(lib, a[s:s + W, 0], a[s:s + W, 1], a[s:s + W, 2], float(fs)))
                y.append(int(vals[j])); g.append(pid); raw.append(a[s:s + W]); files.append(f)
    out = (np.array(X), np.array(y), np.array(g), raw)
    return out + (files,) if files_out else out


def _people(files, max_people):
    """The first `max_people` person ids (file name before the first '_') in sorted order, or None for all."""
    pids = sorted({os.path.basename(f).split('_')[0] for f in files})
    return set(pids[:max_people]) if max_people is not None else None


def _extract(zips, dest):
    """Extract the CSV members of the zips into `dest` once. Through a temp folder, so an interrupted run can never
    leave a partial `dest` that a later run would trust."""
    if os.path.isdir(dest):
        return
    tmp = dest + '.tmp'
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp, exist_ok=True)
    for zp in zips:
        with zipfile.ZipFile(S1.local_copy(zp, 'zips')) as z:
            for n in z.namelist():
                if n.endswith('.csv'):
                    open(os.path.join(tmp, os.path.basename(n)), 'wb').write(z.read(n))
    os.replace(tmp, dest)


def load_sim(root, lib, R, W, log=print, max_people=None):
    """stage3.load_sim with the window length (v1.6 synthetic + Camargo implant-site replay, extracted once)."""
    res = os.path.join(root, 'KNEIL_results'); local = os.path.join(S1.LOCAL_CACHE, 'sim')
    v16, cam = os.path.join(local, 'v16'), os.path.join(local, 'cam')
    _extract([os.path.join(res, 'kneil_dataset_v1_6.zip')], v16)
    _extract(sorted(glob.glob(os.path.join(res, 'dataset', 'ab*.zip'))), cam)
    csvs = [f for d in (v16, cam) for f in glob.glob(os.path.join(d, '*.csv'))]
    people = _people(csvs, max_people)
    X, y, g, _, files = load_windows_w(lib, [v16, cam], FS, W, H, min_share=0.6, lowpass=LP, people=people,
                                       files_out=True)
    fl = np.array(files, object)
    ds = np.where(np.char.startswith(g.astype(str), 'P'), 'v1.6 synthetic', 'Camargo simulated')
    for f in dict.fromkeys(files):                          # one stream id per recording (one CSV)
        m = fl == f
        R.add(X[m].astype(np.float32), y[m], 'sim', ds[m], g[m].astype(object), 'simulated',
              [DEVICE[int(c)] for c in y[m]])
    log(f'  simulated: {len(y)} windows from {len(set(files))} recordings ({(ds == "v1.6 synthetic").sum()} v1.6 '
        f'synthetic, {(ds != "v1.6 synthetic").sum()} Camargo)')


def load_caicedo(root, lib, R, W, log=print, max_people=None):
    """stage3.load_caicedo with the window length."""
    p = os.path.join(root, 'KNEIL_results', 'external', 'caicedo_implant_streams.npz')
    if not os.path.exists(p):
        log('  Caicedo streams not found (KNEIL_results/external/caicedo_implant_streams.npz): skipped'); return
    S = np.load(S1.local_copy(p, 'cai'))
    keys = list(S.files)
    if max_people is not None:
        subs = sorted({re.search(r'Subject(\d+)', k).group(1) for k in keys}, key=int)[:max_people]
        keys = [k for k in keys if re.search(r'Subject(\d+)', k).group(1) in subs]
    n = 0
    for k in keys:
        subj = re.search(r'Subject(\d+)', k).group(1)
        X, _ = stream_windows(lib, S[k], W=W)
        R.add(X, np.zeros(len(X)), 'caicedo', 'Caicedo older adults', f'caicedo:{int(subj)}', 'walking', ['walking'] * len(X))
        n += len(X)
    log(f'  Caicedo: {n} walking windows from {len(keys)} streams')


def load_stage2_old(root, lib, R, rng, W, log=print, max_people=None):
    """stage3.load_stage2 (the old stage 2 output under KNEIL_results/virtual_implant) with the window length.
    Adds the index column `task` as `rec`."""
    out = os.path.join(root, 'KNEIL_results', 'virtual_implant')
    for ip in sorted(glob.glob(os.path.join(out, 'stage2_index_*.csv'))):
        if ip.endswith('_all.csv'):
            continue
        I = pd.read_csv(ip); ds = I.dataset.iloc[0]
        flagged = int((~I.plausible.astype(bool)).sum()); I = I[I.plausible.astype(bool)]
        if max_people is not None:
            I = I[I.person.astype(str).isin(sorted(I.person.astype(str).unique())[:max_people])]
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
                X, lw = stream_windows(lib, a, codes, W=W)
                Xr, _ = stream_windows(lib, S3.rot_y(a, rng.uniform(-5, 5)), None, W=W)
                names = [S2.LABELS[int(c)] if c >= 0 else 'mixed' for c in lw]
                y = [DEVICE.index(TO_DEVICE[nm]) if nm in TRUSTED.get(ds, set()) and nm in TO_DEVICE else -1 for nm in names]
                grp = f'{ds}:{r.group}' if ds == 'Marpino' else f'{ds}:{r.person}'
                R.add(X, y, 'real', ds, grp, str(r.task_label), names, Xr=Xr, rec=_s(r.task))
                n_tr += sum(v >= 0 for v in y); n_out += sum(v < 0 for v in y)
            shutil.rmtree(os.path.join(S1.LOCAL_CACHE, 's2'), ignore_errors=True)
        log(f'  {ds}: {n_tr} windows with a chip class, {n_out} outside the chip classes; {flagged} flagged recordings left out')


def load_stage2_v4(lib, R, rng, W, log=print, max_people=None):
    """The V4 datasets (stage2_v4 output): Luo and Lencioni.
    Luo: trusted chip labels walking / stairs_up / stairs_down / standing, every other window label (slope_up,
         slope_down, calibration, mixed) is kept with y = -1 and its text in `lab`.
    Lencioni: role == 'train' -> trusted walking; role == 'test' -> y = -1 with the text label (stairs_up /
         stairs_down); role == 'other' -> skipped. Group id f'{dataset}:{person}'."""
    for ds in ('Luo', 'Lencioni'):
        ip = os.path.join(config.V4_OUT, f'stage2_index_{ds}.csv')
        if not os.path.exists(ip):
            log(f'  {ds}: index not found ({ip}): skipped'); continue
        I = pd.read_csv(ip)
        flagged = int((~I.plausible.astype(bool)).sum()); I = I[I.plausible.astype(bool)]
        if max_people is not None:
            I = I[I.person.astype(str).isin(sorted(I.person.astype(str).unique())[:max_people])]
        n_tr = n_out = n_skip = 0
        for fn, rows in I.groupby('file'):
            Z = np.load(S1.local_copy(os.path.join(config.V4_OUT, 'stage2', ds, fn), 's2v4'))
            lnames = [str(x) for x in Z['label_names']] if 'label_names' in Z.files else list(S2V.LABELS)
            for r in rows.itertuples():
                if ds == 'Lencioni' and str(r.role) == 'other':
                    n_skip += 1; continue
                prefix = next((t for t in (str(r.task), 'all') if f'{t}|{r.side}|implant' in Z.files), None)
                if prefix is None:
                    n_skip += 1; continue
                a = Z[f'{prefix}|{r.side}|implant']
                lk = f'{prefix}|labels'
                codes = Z[lk][:len(a)] if lk in Z.files else np.full(len(a), S2V.CODE.get(str(r.task_label), S2V.CODE['other']), np.int16)
                X, lw = stream_windows(lib, a, codes, W=W)
                Xr, _ = stream_windows(lib, S3.rot_y(np.asarray(a, float), rng.uniform(-5, 5)), None, W=W)
                names = [lnames[int(c)] if 0 <= int(c) < len(lnames) else 'mixed' for c in lw]
                if ds == 'Luo':
                    y = [DEVICE.index(TO_DEVICE[nm]) if nm in LUO_TRUSTED else -1 for nm in names]
                else:
                    y = [DEVICE.index('walking') if str(r.role) == 'train' and nm == 'walking' else -1 for nm in names]
                meta = dict(rec=_s(r.task), surface=_s(r.surface) if ds == 'Luo' else '')
                if ds == 'Lencioni':
                    meta.update(speed_abs=_s(r.speed_abs), speed_rel=_s(r.speed_rel),
                                adult=str(bool(r.adult)), role=_s(r.role))
                R.add(X, y, 'real', ds, f'{ds}:{r.person}', str(r.task_label), names, Xr=Xr, **meta)
                n_tr += sum(v >= 0 for v in y); n_out += sum(v < 0 for v in y)
        log(f'  {ds}: {n_tr} windows with a chip class, {n_out} outside the chip classes; {flagged} flagged, {n_skip} rows skipped')


def counts(A, log=print):
    """Window counts per dataset and per chip class."""
    y, ds = A['y'], A['ds']
    rows = []
    for d in sorted(set(ds)):
        m = ds == d
        r = dict(dataset=d, windows=int(m.sum()))
        for c in range(len(DEVICE)):
            r[DEVICE[c]] = int((y[m] == c).sum())
        r['no chip class'] = int((y[m] < 0).sum())
        rows.append(r)
    r = dict(dataset='ALL', windows=int(len(y)))
    for c in range(len(DEVICE)):
        r[DEVICE[c]] = int((y == c).sum())
    r['no chip class'] = int((y < 0).sum())
    rows.append(r)
    Tb = pd.DataFrame(rows).set_index('dataset')
    log('\nwindows per dataset and chip class:\n' + Tb.to_string())
    return Tb


def build(W_s, max_people=None, log=print):
    """Every window of every source for a window of W_s seconds (W = 50 * W_s samples, hop 1 s). Cached npz."""
    W = int(round(FS * W_s))
    out = config.out_dir('stepD', WINDOWS_DIR)
    path = os.path.join(out, f'windows_W{W_s:g}s.npz')
    if os.path.exists(path):
        log(f'windows: loading {path} (delete it to rebuild)')
        Z = np.load(S1.local_copy(path, 'w4'), allow_pickle=True)
        A = {k: Z[k] for k in Z.files}
        counts(A, log)
        return A
    rng = np.random.default_rng(0); R = Rows(); t0 = time.time()
    lib = S3.init_tinyml(TINY)
    log(f'windows: building W = {W} samples ({W_s:g} s), hop {H} samples, max_people {max_people}')
    load_sim(config.DATA_ROOT, lib, R, W, log=log, max_people=max_people)
    load_caicedo(config.DATA_ROOT, lib, R, W, log=log, max_people=max_people)
    load_stage2_old(config.DATA_ROOT, lib, R, rng, W, log=log, max_people=max_people)
    load_stage2_v4(lib, R, rng, W, log=log, max_people=max_people)
    A = R.arrays(); A['W'] = np.int32(W)
    np.savez_compressed(path, **A)
    log(f'windows: {len(A["y"])} in {(time.time() - t0) / 60:.1f} min -> {path}')
    counts(A, log)
    return A


def main():
    ap = argparse.ArgumentParser(description='KNEIL V4 window builder (window length in seconds)')
    ap.add_argument('--win', type=float, required=True, help='window length in seconds, e.g. 2, 3, 4, 5')
    ap.add_argument('--max-people', type=int, default=None, help='people per dataset (test runs)')
    a = ap.parse_args()
    print(VERSION, flush=True)
    log_path = os.path.join(config.out_dir('stepD', 'D0'), f'stage3_v4_W{a.win:g}s_log.txt')
    with S1.Tee(log_path):
        print(f'{VERSION} | {S3.VERSION} | {S2V.VERSION} | {config.VERSION} | {np.datetime64("now", "s")}')
        print(f'V4_OUT {config.V4_OUT}  CACHE {config.CACHE}  max_people {a.max_people}  log {log_path}')
        build(a.win, a.max_people)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
