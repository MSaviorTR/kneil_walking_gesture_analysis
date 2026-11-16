"""
Train the KNEIL on-device activity classifier.

- Windows the dataset exactly like the firmware (2 s windows, 1 s hop, from the first sample).
- Features come from the C implementation (libkneil_features.so built from src/kneil_features.c),
  so the model is trained on exactly what the nRF54L15 computes.
- Cross-validation by virtual patient (GroupKFold), model and sampling-rate comparison.
- Exports the chosen model to C with emlearn (include/kneil_model.h) and writes test vectors.

Usage: python train_kneil_tinyml.py --data <kneil_dataset_v1_6> --fs 50 [--extra more_csv_dir ...]   (export)
       python train_kneil_tinyml.py --data <kneil_dataset_v1_6> --compare                              (rates x models)
Extra directories may hold real recordings in the same CSV format (time_s, acc_x_g, acc_y_g, acc_z_g, activity).
"""
import argparse, ctypes, glob, json, os, subprocess, sys
from fractions import Fraction
import numpy as np, pandas as pd
from scipy.signal import resample_poly
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import GroupKFold
from sklearn.metrics import f1_score, balanced_accuracy_score, accuracy_score, confusion_matrix

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CLASSES = ['walking', 'stairs_up', 'stairs_down', 'sitting', 'standing', 'lying', 'sit_to_stand', 'stand_to_sit', 'bed_transfer']
MAP = {'walking': 0, 'stairs_up': 1, 'stairs_down': 2, 'sitting': 3, 'standing': 4, 'lying_supine': 5, 'lying_side': 5,
       'sit_to_stand': 6, 'stand_to_sit': 7, 'rolling': 8, 'sit_up': 8, 'lie_down': 8}
NF = 20


def c_features_lib():
    # .so on Linux/macOS, .dll on Windows (MinGW-w64 gcc: GCC runtime linked in, no -fPIC)
    so = os.path.join(HERE, 'libkneil_features' + ('.dll' if os.name == 'nt' else '.so'))
    if not os.path.exists(so):
        flags = ['-static-libgcc'] if os.name == 'nt' else ['-fPIC']
        subprocess.check_call(['gcc', '-O2', '-std=c99', '-shared', *flags, '-I' + os.path.join(ROOT, 'include'),
                               os.path.join(ROOT, 'src', 'kneil_features.c'), '-o', so, '-lm'])
    lib = ctypes.CDLL(so)
    P = ctypes.POINTER(ctypes.c_float)
    lib.kneil_features.argtypes = [P, P, P, ctypes.c_int, ctypes.c_float, P]
    return lib


def features(lib, x, y, z, fs):
    out = np.zeros(NF, np.float32); P = ctypes.POINTER(ctypes.c_float)
    x, y, z = (np.ascontiguousarray(a, np.float32) for a in (x, y, z))
    lib.kneil_features(x.ctypes.data_as(P), y.ctypes.data_as(P), z.ctypes.data_as(P), len(x), ctypes.c_float(fs), out.ctypes.data_as(P))
    return out


def lowpass_coeffs(fs, fc):
    """Same 2nd-order Butterworth as kneil_lowpass_design() in C (float32 coefficients)."""
    K = np.float32(np.tan(np.pi * fc / fs)); r2 = np.float32(1.41421356)
    norm = np.float32(1.0) / (np.float32(1.0) + r2 * K + K * K)
    b0 = K * K * norm; a1 = np.float32(2.0) * (K * K - 1) * norm; a2 = (np.float32(1.0) - r2 * K + K * K) * norm
    return np.array([b0, 2 * b0, b0], np.float64), np.array([1.0, a1, a2], np.float64)


def apply_lowpass(a, fs, fc):
    """Causal filter primed at steady state with the first sample, like the device (per axis)."""
    from scipy.signal import lfilter, lfilter_zi
    b, aa = lowpass_coeffs(fs, fc)
    zi = lfilter_zi(b, aa)
    return np.column_stack([lfilter(b, aa, a[:, k], zi=zi * a[0, k])[0] for k in range(a.shape[1])])


def lowpass_parity(lib, fs, fc):
    """Check the Python filter against the C one (kneil_lowpass_step) on a random signal."""
    class BQ(ctypes.Structure):
        _fields_ = [(n, ctypes.c_float) for n in ('b0', 'b1', 'b2', 'a1', 'a2', 'z1', 'z2')] + [('primed', ctypes.c_int)]
    lib.kneil_lowpass_design.argtypes = [ctypes.POINTER(BQ), ctypes.c_float, ctypes.c_float]
    lib.kneil_lowpass_step.argtypes = [ctypes.POINTER(BQ), ctypes.c_float]; lib.kneil_lowpass_step.restype = ctypes.c_float
    x = (np.random.default_rng(0).normal(0, 0.5, 2000) + 1.0).astype(np.float32)
    f = BQ(); lib.kneil_lowpass_design(ctypes.byref(f), fs, fc)
    yc = np.array([lib.kneil_lowpass_step(ctypes.byref(f), float(v)) for v in x])
    yp = apply_lowpass(x[:, None].astype(np.float64), fs, fc)[:, 0]
    return float(np.abs(yc - yp).max())


def load_windows(lib, dirs, fs, min_share=0.6, lowpass=0.0):
    X, y, g, raw = [], [], [], []
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, '*.csv'))):
            if os.path.basename(f) == 'patients.csv': continue
            df = pd.read_csv(f, usecols=['acc_x_g', 'acc_y_g', 'acc_z_g', 'activity'])
            a = df[['acc_x_g', 'acc_y_g', 'acc_z_g']].values.astype(np.float64); lab = df['activity'].map(MAP).fillna(-1).values.astype(int)
            if fs != 100:                                # any integer rate, e.g. 50, 52 (ST parts), 25, 26
                fr = Fraction(fs, 100); a = resample_poly(a, fr.numerator, fr.denominator, axis=0)
                lab = lab[np.minimum(np.round(np.arange(len(a)) * 100.0 / fs).astype(int), len(lab) - 1)]
            if lowpass > 0:
                a = apply_lowpass(a, fs, lowpass)
            a = a.astype(np.float32); W, H = 2 * fs, fs
            pid = os.path.basename(f).split('_')[0]
            for s in range(0, len(a) - W + 1, H):
                l = lab[s:s + W]; vals, cnt = np.unique(l, return_counts=True); j = np.argmax(cnt)
                if vals[j] < 0 or cnt[j] < min_share * W: continue
                X.append(features(lib, a[s:s + W, 0], a[s:s + W, 1], a[s:s + W, 2], fs)); y.append(vals[j]); g.append(pid)
                raw.append(a[s:s + W])
    return np.array(X), np.array(y), np.array(g), raw


MODELS = {
    'tree d10': lambda: DecisionTreeClassifier(max_depth=10, min_samples_leaf=3, class_weight='balanced', random_state=0),
    'forest 10x d8': lambda: RandomForestClassifier(10, max_depth=8, min_samples_leaf=3, class_weight='balanced_subsample', random_state=0),
    'forest 20x d8': lambda: RandomForestClassifier(20, max_depth=8, min_samples_leaf=3, class_weight='balanced_subsample', random_state=0),
    'forest 20x d10': lambda: RandomForestClassifier(20, max_depth=10, min_samples_leaf=3, class_weight='balanced_subsample', random_state=0),
}


def n_nodes(m):
    return sum(e.tree_.node_count for e in m.estimators_) if hasattr(m, 'estimators_') else m.tree_.node_count


def cv(X, y, g, make):
    P = np.zeros_like(y)
    for tr, te in GroupKFold(5).split(X, y, g):
        P[te] = make().fit(X[tr], y[tr]).predict(X[te])
    return dict(macro_f1=float(f1_score(y, P, average='macro')), bal_acc=float(balanced_accuracy_score(y, P)),
                acc=float(accuracy_score(y, P)), f1=f1_score(y, P, average=None, labels=range(9)).round(3).tolist(),
                cm=confusion_matrix(y, P, labels=range(9)).tolist())


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--data', default=os.path.join(ROOT, '..', '..', 'kneil', 'kneil_dataset_v1_6'))
    ap.add_argument('--extra', nargs='*', default=[]); ap.add_argument('--fs', type=int, default=50)
    ap.add_argument('--model', default='forest 20x d10'); ap.add_argument('--compare', action='store_true')
    ap.add_argument('--lowpass', type=float, default=0.0, help='causal input low-pass (Hz) applied in training and on the device; 0 = off')
    a = ap.parse_args(); lib = c_features_lib(); report = {}
    if a.lowpass > 0:
        err = lowpass_parity(lib, a.fs, a.lowpass)
        print(f'input low-pass {a.lowpass:g} Hz: C vs Python max difference {err:.2e} g', flush=True)
        assert err < 1e-4, 'C and Python low-pass differ'
    for fs in ((100, 50, 25) if a.compare else (a.fs,)):
        X, y, g, raw = load_windows(lib, [a.data] + a.extra, fs, lowpass=a.lowpass)
        for name in (MODELS if a.compare else [a.model]):
            r = cv(X, y, g, MODELS[name]); r['nodes'] = n_nodes(MODELS[name]().fit(X, y)); report[f'{fs} Hz | {name}'] = r
            print(f"{fs:3d} Hz | {name:14s} | macro-F1 {r['macro_f1']:.3f}  bal-acc {r['bal_acc']:.3f}  acc {r['acc']:.3f} | nodes {r['nodes']:5d} | windows {len(y)}", flush=True)
    json.dump(report, open(os.path.join(HERE, 'cv_report.json' if a.compare else f'cv_final_{a.fs}Hz.json'), 'w'), indent=1)
    if not a.compare:                                    # final models on all data -> C headers + model info + test vectors
        import emlearn
        X, y, g, raw = load_windows(lib, [a.data] + a.extra, a.fs, lowpass=a.lowpass)
        models = {}
        for name, fname in (('forest 20x d10', 'kneil_model_forest.h'), ('tree d10', 'kneil_model_tree.h')):
            models[name] = MODELS[name]().fit(X, y)
            # dtype='float' is essential: the default int16 thresholds break float features
            emlearn.convert(models[name], method='inline', dtype='float').save(file=os.path.join(ROOT, 'include', fname), name='kneil_model')
        open(os.path.join(ROOT, 'include', 'kneil_model_info.h'), 'w').write(
            '/* Written by tools/train_kneil_tinyml.py together with the model headers. */\n#ifndef KNEIL_MODEL_INFO_H\n#define KNEIL_MODEL_INFO_H\n'
            f'#define KNEIL_MODEL_FS_HZ {a.fs}          /* the models were trained on {a.fs} Hz data */\n#define KNEIL_MODEL_N_FEATURES {NF}\n'
            f'#define KNEIL_MODEL_LOWPASS_HZ {a.lowpass:g}      /* input low-pass used in training, applied on the device (0 = off) */\n'
            f'#define KNEIL_MODEL_DATASET "{"; ".join(os.path.basename(os.path.normpath(d)) for d in [a.data] + a.extra)}"\n#endif\n')
        def forest_c_vote(m, X):                         # the generated C forest uses majority voting (ties -> lowest id)
            v = np.zeros((len(X), 9), int)
            for e in m.estimators_: v[np.arange(len(X)), e.predict(X).astype(int)] += 1
            return v.argmax(1)
        rng = np.random.default_rng(0); sel = []
        for c in range(9):
            idx = np.flatnonzero(y == c); sel += list(rng.choice(idx, min(3, len(idx)), replace=False))
        np.savez(os.path.join(HERE, 'test_vectors.npz'), raw=np.array([raw[i] for i in sel]), feat=X[sel], label=y[sel],
                 pred_forest=forest_c_vote(models['forest 20x d10'], X[sel]), pred_tree=models['tree d10'].predict(X[sel]))
        subprocess.check_call([sys.executable, os.path.join(HERE, 'gen_test_vectors.py')])   # the running Python (Windows has no python3)
        print('exported include/kneil_model_forest.h, kneil_model_tree.h, kneil_model_info.h and tests/kneil_test_vectors.h')
        print('next: python tests/run_host_test.py  (must print RESULT: PASS for both models)')
