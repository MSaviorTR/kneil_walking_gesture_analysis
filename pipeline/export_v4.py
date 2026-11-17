"""
Step E: train the V4 model on everyone and export it for the chip.   export_v4 1.0, 17 Nov 2026

Owner's decision (docs/STEP_D_SUMMARY.md): 8 classes, 4 s windows, hop 1 s, 50 Hz, 6 Hz low-pass, V4half training
data, forest 20 x depth 10 plus the single tree, float thresholds, stairs rule vote >= 0.60, transition events R1.

Writes into <V4_OUT>/tinyml_final_v4_lp6/ (kneil_model_forest.h, kneil_model_tree.h, kneil_model_info.h,
kneil_test_vectors.h, the joblib models, counts.json, export_log.txt) and copies the four headers into the chip
library (<lib>/include and <lib>/tests) so that the library builds and self-tests on its own.

CLI: python pipeline/export_v4.py [--win 4] [--max-people 2] [--lib keneil_tinyml]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import pandas as pd

import config
import cv_v4 as C
import stage01 as S1
import stage3 as S3
import stage3_v4 as S4

VERSION = 'export_v4 1.0'
WIN_S = 4.0
HOP_S = 1.0
NCLS = 8
STAIRS_MIN_VOTE = 0.60
NAME = 'V4half 4s'
VECTOR_PER_CLASS = 2                     # test vectors per class (>= 1, task E1 Part A.4)


def limit_people(A, n, log=print):
    """Keep the first n people of every (src, dataset), for the smoke test."""
    keep = np.zeros(len(A['y']), bool)
    for src in sorted(set(A['src'])):
        for ds in sorted(set(A['ds'][A['src'] == src])):
            m = (A['src'] == src) & (A['ds'] == ds)
            gs = sorted(set(A['grp'][m]))[:n]
            keep |= m & np.isin(A['grp'], gs)
    log(f'  smoke: {int(keep.sum())} of {len(keep)} rows, {len(set(A["grp"][keep]))} people')
    return {k: v[keep] for k, v in A.items()}


def sim_windows(lib, win, per_class=VECTOR_PER_CLASS, people=None, log=print):
    """Raw simulation windows (one W x 3 array per vector), at least one per class."""
    v16 = os.path.join(config.CACHE, 'sim', 'v16')
    cam = os.path.join(config.CACHE, 'sim', 'cam')
    X, y, g, raw, files = S4.load_windows_w(lib, [v16, cam], 50, int(50 * win), 50, min_share=0.6, lowpass=6.0,
                                            people=people, files_out=True)
    if not len(y):
        raise RuntimeError(f'no simulation windows: is {config.CACHE}\\sim extracted? (run stage3_v4.py once)')
    src = np.array(['v1.6 synthetic' if str(p).startswith('P') else 'Camargo simulated' for p in g])
    sel = []
    for c in range(NCLS):
        idx = np.flatnonzero(y == c)
        if not len(idx):
            raise RuntimeError(f'no simulation window of class {c} ({C.CLASSES8[c]})')
        picks = []
        for name in ('v1.6 synthetic', 'Camargo simulated'):       # prefer one of each source
            cand = [i for i in idx if src[i] == name and i not in picks]
            if cand:
                picks.append(int(cand[0]))
        for i in idx:
            if len(picks) >= per_class:
                break
            if int(i) not in picks:
                picks.append(int(i))
        sel += picks[:per_class]
    log(f'  test vectors: {len(sel)} windows, classes {sorted(set(y[sel].tolist()))}, '
        f'{len(X)} simulation windows available')
    return [raw[i] for i in sel], y[sel], [files[i] for i in sel]


def forest_votes(model, X):
    """Majority vote of the trees, exactly like the emlearn-generated forest (ties -> lowest id)."""
    v = np.zeros((len(X), NCLS), np.int32)
    for e in model.estimators_:
        v[np.arange(len(X)), e.predict(X).astype(int)] += 1
    return v.argmax(1)


def main():
    ap = argparse.ArgumentParser(description='KNEIL V4 export (step E)')
    ap.add_argument('--win', type=float, default=WIN_S)
    ap.add_argument('--max-people', type=int, default=None, help='people per dataset (smoke test)')
    ap.add_argument('--lib', default=config.TINYML, help='chip library folder to copy the headers into')
    a = ap.parse_args()
    print(VERSION, flush=True)
    out = config.out_dir('tinyml_final_v4_lp6')
    log_path = os.path.join(out, 'export_log.txt')
    with S1.Tee(log_path):
        print(f'{VERSION} | {S3.VERSION} | {C.VERSION} | {config.VERSION} | {np.datetime64("now", "s")}')
        print(f'V4_OUT {config.V4_OUT}  out {out}  lib {a.lib}  win {a.win:g} s  max_people {a.max_people}')
        t0 = time.time()
        A = C.load(a.win)
        if a.max_people:
            A = limit_people(A, a.max_people)
        y = C.y_for(A, NCLS)
        Xt, yt, wt = C.training_set_v4(A, np.ones(len(A['y']), bool), 'V4half', y)
        print(f'\ntraining rows {len(yt)} (V4half), classes {dict(zip(*np.unique(yt, return_counts=True)))}')
        lib = S3.init_tinyml(config.TINYML)
        models = {}
        for key, fname in (('forest 20x d10', 'kneil_model_forest.h'), ('tree d10', 'kneil_model_tree.h')):
            m = S3.make_model(key)
            m.set_params(random_state=0)
            m.fit(Xt, yt, sample_weight=wt)
            models[key] = m
            import emlearn
            emlearn.convert(m, method='inline', dtype='float').save(file=os.path.join(out, fname), name='kneil_model')
            print(f'  {key}: {S3.T.n_nodes(m)} nodes -> {fname} ({os.path.getsize(os.path.join(out, fname)) / 1024:.1f} kB)')
        import joblib
        joblib.dump(models['forest 20x d10'], os.path.join(out, 'model_forest.joblib'))
        joblib.dump(models['tree d10'], os.path.join(out, 'model_tree.joblib'))
        dset = ('kneil_dataset_v1_6; kneil_camargo_v1_3; caicedo_2020; real implant-site '
                '(CeTI, KneE-PAD, MHEALTH, Marpino, PAMAP2, WearGait-PD, Luo, Lencioni); V4half')
        open(os.path.join(out, 'kneil_model_info.h'), 'w').write(
            '/* Written by pipeline/export_v4.py (KNEIL V4). Owner decision 17 Nov 2026 (docs/STEP_D_SUMMARY.md). */\n'
            '#ifndef KNEIL_MODEL_INFO_H\n#define KNEIL_MODEL_INFO_H\n'
            f'#define KNEIL_MODEL_FS_HZ 50                 /* trained on 50 Hz data */\n'
            f'#define KNEIL_MODEL_N_FEATURES {S3.T.NF}\n'
            f'#define KNEIL_MODEL_LOWPASS_HZ 6             /* input low-pass used in training, applied on the device */\n'
            f'#define KNEIL_MODEL_WIN_S {a.win:g}                   /* window length in seconds */\n'
            f'#define KNEIL_MODEL_HOP_S {HOP_S:g}                   /* classify every HOP_S seconds */\n'
            f'#define KNEIL_MODEL_N_CLASSES {NCLS}\n'
            f'#define KNEIL_MODEL_STAIRS_MIN_VOTE {STAIRS_MIN_VOTE:.2f}f /* stairs kept only with this vote share */\n'
            f'#define KNEIL_MODEL_NAME "{NAME}"\n'
            f'#define KNEIL_MODEL_DATASET "{dset}"\n#endif\n')
        # test vectors: raw 4 s windows, features from the C code, classes from the two exported models
        raw, yv, files = sim_windows(lib, a.win, log=print)
        feat = np.array([S3.T.features(lib, w[:, 0], w[:, 1], w[:, 2], 50.0) for w in raw], np.float32)
        np.savez(os.path.join(a.lib, 'tools', 'test_vectors.npz'), raw=np.array(raw, np.float32), feat=feat, label=yv,
                 pred_forest=forest_votes(models['forest 20x d10'], feat),
                 pred_tree=models['tree d10'].predict(feat).astype(np.int8))
        r = subprocess.run([sys.executable, os.path.join(a.lib, 'tools', 'gen_test_vectors.py')],
                           capture_output=True, text=True, cwd=a.lib)
        print(r.stdout.strip())
        if r.returncode != 0:
            print(r.stderr.strip()); raise SystemExit('gen_test_vectors failed')
        shutil.copyfile(os.path.join(a.lib, 'tests', 'kneil_test_vectors.h'),
                        os.path.join(out, 'kneil_test_vectors.h'))      # keep all four headers in the results folder
        for f, sub in (('kneil_model_forest.h', 'include'), ('kneil_model_tree.h', 'include'),
                       ('kneil_model_info.h', 'include'), ('kneil_test_vectors.h', 'tests')):
            shutil.copyfile(os.path.join(out, f), os.path.join(a.lib, sub, f))
        counts = dict(version=VERSION, win_s=a.win, hop_s=HOP_S, n_classes=NCLS, name=NAME,
                      stairs_min_vote=STAIRS_MIN_VOTE, rows=int(len(yt)), max_people=a.max_people,
                      forest_nodes=int(S3.T.n_nodes(models['forest 20x d10'])),
                      tree_nodes=int(S3.T.n_nodes(models['tree d10'])),
                      vectors=int(len(raw)), vectors_per_class=VECTOR_PER_CLASS,
                      train_by_dataset={d: int((A['ds'] == d).sum()) for d in sorted(set(A['ds']))},
                      train_by_class={C.CLASSES8[c]: int((yt == c).sum()) for c in range(NCLS)},
                      test_vectors_files=files)
        open(os.path.join(out, 'counts.json'), 'w').write(json.dumps(counts, indent=1))
        print(f'\ncounts.json written; headers copied into {a.lib}')
        print(f'export done in {(time.time() - t0) / 60:.1f} min')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
