"""
Independent check of the chip's 20 C features against the numpy reference (pipeline/features_ref.py).   v1.0, 16 Nov 2026

Signals
  (a) 3 Luo people (<KNEIL_V4_OUT>/stage2/Luo/*.npz), 10 trials per person, shank R implant stream, filtered with the
      chip's 6 Hz low-pass (stage3.T.apply_lowpass) exactly like the training windows; cut with hop 50.
  (b) 200 random windows per length (normal noise, std 0.3 g, +1 g on z).
  (c) one constant window (0, 0, 1) per length.

For every window length n = 100, 150, 200, 250 samples (2, 3, 4, 5 s) the C features (ctypes, float32) and the
reference (float64) are compared feature by feature. PASS per feature and length:
    max |C - ref| <= 1e-4 + 1e-3 * max(|ref|)   over all windows of that length
and zcr_z_hz must be identical (no mismatch at all).
"""
import glob
import os
import re
import sys

import numpy as np
import pandas as pd

import config
import features_ref as FR
import stage01 as S1
import stage3 as S3

VERSION = 'test_features_window 1.0'
FS = 50.0
LP = 6.0
LENGTHS = (100, 150, 200, 250)          # 2, 3, 4, 5 s
HOP = 50
N_RANDOM = 200
LUO_PEOPLE, LUO_TRIALS = 3, 10
ATOL, RTOL = 1e-4, 1e-3


def luo_streams(log=print):
    """Filtered Luo shank-R implant streams (one per trial), like the training windows."""
    d = os.path.join(config.V4_OUT, 'stage2', 'Luo')
    files = sorted(glob.glob(os.path.join(d, '*.npz')),
                   key=lambda p: int(re.sub(r'\D', '', os.path.basename(p)) or 0))
    if not files:
        log(f'  ERROR: no Luo npz in {d} (set KNEIL_V4_OUT to the v4 results folder)')
        return []
    out = []
    for f in files[:LUO_PEOPLE]:
        Z = np.load(S1.local_copy(f, 'luo'))
        keys = sorted(k for k in Z.files if k.endswith('|R|implant'))
        for k in keys[:LUO_TRIALS]:
            a = np.asarray(Z[k], np.float64)
            if len(a) >= max(LENGTHS):
                out.append((f'{os.path.basename(f)}:{k}', S3.T.apply_lowpass(a, FS, LP)))
    log(f'  Luo: {len(files[:LUO_PEOPLE])} people, {len(out)} filtered streams '
        f'({", ".join(f"{os.path.basename(f)}" for f in files[:LUO_PEOPLE])})')
    return out


def cut(stream, n):
    return [stream[s:s + n] for s in range(0, len(stream) - n + 1, HOP)]


def main():
    print(VERSION, flush=True)
    out = config.out_dir('stepD', 'D0')
    log_path = os.path.join(out, 'test_features_window_log.txt')
    csv_path = os.path.join(out, 'test_features_window_diffs.csv')
    with S1.Tee(log_path):
        print(f'{VERSION} | {FR.VERSION} | {S3.VERSION} | {config.VERSION}')
        print(f'{np.datetime64("now", "s")} | data root {config.DATA_ROOT}')
        print(f'log {log_path}\n')
        lib = S3.init_tinyml(config.TINYML)
        streams = luo_streams()
        if not streams:
            print('FAIL: no Luo streams, the check cannot run'); return 1
        rng = np.random.default_rng(0)
        rows, tables, failures = [], {}, {}
        for n in LENGTHS:
            W6 = [w for _, s in streams for w in cut(s, n)]
            noise = rng.normal(0.0, 0.3, size=(N_RANDOM, n, 3)); noise[:, :, 2] += 1.0
            const = np.tile(np.array([0.0, 0.0, 1.0]), (n, 1))[None, :, :]
            wins = W6 + list(noise) + list(const)
            maxd = np.zeros(20); maxr = np.zeros(20); zc_bad = 0; bad_finite = 0
            for i, w in enumerate(wins):
                fc = S3.T.features(lib, w[:, 0], w[:, 1], w[:, 2], FS).astype(np.float64)
                fr = FR.features_ref(w[:, 0], w[:, 1], w[:, 2], FS)
                if i >= len(W6) + N_RANDOM:                     # the constant window
                    if not np.all(np.isfinite(fc)) or not np.all(np.isfinite(fr)):
                        bad_finite += 1
                        print(f'  {n} samples: constant window not finite\n    C   {fc}\n    ref {fr}')
                maxd = np.maximum(maxd, np.abs(fc - fr))
                maxr = np.maximum(maxr, np.abs(fr))
                # zcr_z_hz = zc * fs / n: the crossing COUNT must be identical (the value differs only by float32 rounding)
                zc_bad += int(round(fc[FR.I_ZCR] * n / FS) != round(fr[FR.I_ZCR] * n / FS))
            tol = ATOL + RTOL * maxr
            ok = (maxd <= tol)
            ok[FR.I_ZCR] &= (zc_bad == 0)
            ok &= np.isfinite(maxr) & np.isfinite(maxd)
            tables[n] = dict(windows=len(wins), luo=len(W6), random=N_RANDOM, const=1,
                             maxd=maxd, maxr=maxr, tol=tol, ok=ok, zc_bad=zc_bad, nonfinite=bad_finite)
            failures[n] = [FR.NAMES[j] for j in range(20) if not ok[j]]
            for j, name in enumerate(FR.NAMES):
                rows.append(dict(window_s=n / FS, n_samples=n, feature=name, windows=len(wins),
                                 max_abs_diff=float(maxd[j]), max_abs_ref=float(maxr[j]), tolerance=float(tol[j]),
                                 zcr_mismatches=(zc_bad if j == FR.I_ZCR else ''), pass_=bool(ok[j])))
            print(f'{n} samples ({n / FS:g} s): {len(wins)} windows '
                  f'({len(W6)} Luo + {N_RANDOM} random + 1 constant), '
                  f'{int(np.sum(~ok))} feature(s) FAIL, zcr_z_hz mismatches {zc_bad}, '
                  f'constant window non-finite values {bad_finite}')
        head = 'feature'.ljust(16) + ''.join('| ' + f'{n} samples ({n / FS:g} s)'.rjust(19) + ' ' for n in LENGTHS)
        print('\n' + head)
        print('-' * len(head))
        for j, name in enumerate(FR.NAMES):
            line = name.ljust(16)
            for n in LENGTHS:
                tb = tables[n]
                line += '| ' + f'{tb["maxd"][j]:9.2e} {"PASS" if tb["ok"][j] else "FAIL"}'.rjust(19) + ' '
            print(line)
        print('-' * len(head))
        print('max |C - ref|; PASS = max|C-ref| <= 1e-4 + 1e-3*max|ref| and (for zcr_z_hz) the same crossing count\n')
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        print(f'table saved: {csv_path}')
        failed = {n: v for n, v in failures.items() if v}
        if failed:
            print(f'RESULT: FAIL - {failed}')
            return 1
        print(f'RESULT: PASS - all 20 features pass at {", ".join(f"{n / FS:g} s" for n in LENGTHS)}')
        return 0


if __name__ == '__main__':
    sys.exit(main())
