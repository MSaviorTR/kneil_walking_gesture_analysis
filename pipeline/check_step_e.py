"""
Step E checks: the C library v2.0 against Python on raw streams, events, summaries, sizes and export sanity.
   check_step_e 1.0, 17 Nov 2026

1. builds the V4 export (unless --no-export) and the C library (gcc, ctypes)
2. check 4: C per-window raw class vs the sklearn forest on the same features; C rule vs stairs_rule.apply_rule
3. check 5: the D2 V4half 4 s seed 0 predictions replayed through the C metrics and through transition_events R1
4. check 6: metrics_ref.py vs the C summary, byte for byte
5. check 7: sizeof / time per window (from the host test and a timed push loop)
6. check 8: in-sample sanity of the export (Luo FE, Lencioni fast, walking called stairs, with/without the rule)

All results are written to <V4_OUT>/stepE/E1/. Usage: python pipeline/check_step_e.py [--no-export] [--quick]
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from fractions import Fraction

import numpy as np
import pandas as pd
from scipy.signal import resample_poly
from sklearn.ensemble import RandomForestClassifier

import config
import cv_v4 as C
import metrics_ref as MR
import stage01 as S1
import stage3 as S3
import stage3_v4 as S4
import stairs_rule as SR
import transition_events as TE
from export_v4 import forest_votes

VERSION = 'check_step_e 1.0'
LIB = config.TINYML
W = 4.0
F = ctypes.c_float
P = ctypes.POINTER(ctypes.c_float)


# ------------------------------------------------------------------ build
def build_dll(log=print):
    d = os.path.join(config.CACHE, 'stepE')
    os.makedirs(d, exist_ok=True)
    so = os.path.join(d, 'libkneil_v4' + ('.dll' if os.name == 'nt' else '.so'))
    flags = ['-static-libgcc'] if os.name == 'nt' else ['-fPIC']
    srcs = [os.path.join(LIB, 'src', f) for f in ('kneil_features.c', 'kneil_classifier.c', 'kneil_metrics.c')]
    cmd = ['gcc', '-O2', '-std=c99', '-shared', *flags, '-I' + os.path.join(LIB, 'include'), *srcs, '-o', so, '-lm']
    subprocess.check_call(cmd)
    lib = ctypes.CDLL(so)
    lib.kneil_classifier_init.argtypes = [ctypes.c_void_p]
    lib.kneil_classifier_push.argtypes = [ctypes.c_void_p, F, F, F]
    lib.kneil_classifier_push.restype = ctypes.c_int
    lib.kneil_classifier_raw_class.argtypes = [ctypes.c_void_p]
    lib.kneil_classifier_raw_class.restype = ctypes.c_int
    lib.kneil_classifier_vote.argtypes = [ctypes.c_void_p]
    lib.kneil_classifier_vote.restype = ctypes.c_float
    lib.kneil_classifier_proba.argtypes = [ctypes.c_void_p, P]
    lib.kneil_metrics_reset.argtypes = [ctypes.c_void_p]
    lib.kneil_metrics_push.argtypes = [ctypes.c_void_p, ctypes.c_int, F, F, F, F]
    lib.kneil_metrics_summary.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.kneil_stairs_rule.argtypes = [ctypes.c_int, F]
    lib.kneil_stairs_rule.restype = ctypes.c_int
    log(f'  built {so}')
    return lib, so


# ------------------------------------------------------------------ streams
def read_sim_csv(f):
    df = pd.read_csv(f, usecols=['acc_x_g', 'acc_y_g', 'acc_z_g'])
    a = df[['acc_x_g', 'acc_y_g', 'acc_z_g']].values.astype(np.float64)
    fr = Fraction(50, 100)
    return resample_poly(a, fr.numerator, fr.denominator, axis=0).astype(np.float32)


def stage2_stream(ds, want, n, side='R', old=True):
    base = os.path.join(config.RESULTS, 'virtual_implant') if old else config.V4_OUT
    I = pd.read_csv(os.path.join(base, f'stage2_index_{ds}.csv'))
    I = I[I.plausible.astype(bool)]
    I = I[I.task.astype(str).map(want)]
    out = []
    for person, rows in I.groupby('person'):
        Z = np.load(os.path.join(base, 'stage2', ds, rows.file.iloc[0]))
        r = rows[rows.side == side].head(1)
        if not len(r):
            continue
        key = f'{r.task.iloc[0]}|{side}|implant'
        if key in Z.files:
            out.append((f'{ds} {person} {r.task.iloc[0]}', np.asarray(Z[key], np.float32)))
        if len(out) >= n:
            break
    return out


def check4_streams(quick=False):
    """10 simulation files, 10 Luo trials, 5 WearGait-PD walks, 3 CeTI recordings."""
    sims = [f for f, _ in TE.sim_files()]
    pick = [sims[int(i)] for i in np.unique(np.linspace(0, len(sims) - 1, 10).astype(int))]
    out = [('sim ' + os.path.basename(f), read_sim_csv(f)) for f in pick]
    luo = []
    d = os.path.join(config.V4_OUT, 'stage2', 'Luo')
    for person in ('1', '2'):
        Z = np.load(os.path.join(d, f'{person}.npz'))
        keys = sorted(k for k in Z.files if k.endswith('|R|implant'))[:5]
        luo += [(f'Luo {person} {k}', np.asarray(Z[k], np.float32)) for k in keys]
    out += luo[:10]
    out += [(n, a) for n, a in stage2_stream('WearGait-PD', lambda r: r == 'SelfPace', 5)]
    out += [(n, a) for n, a in stage2_stream('CeTI', lambda r: str(r).startswith('s01_ses01_run01'), 3)]
    return out[:18] if quick else out


def c_windows(lib, a):
    """Run one raw stream through the C classifier; returns lists (raw, vote, rule, proba) per window."""
    buf = ctypes.create_string_buffer(8192)
    lib.kneil_classifier_init(buf)
    raw, vote, rule, prob = [], [], [], []
    pr = (F * MR.N_CLASSES)()
    for i in range(len(a)):
        r = lib.kneil_classifier_push(buf, float(a[i, 0]), float(a[i, 1]), float(a[i, 2]))
        if r >= 0:
            lib.kneil_classifier_proba(buf, pr)
            raw.append(lib.kneil_classifier_raw_class(buf))
            vote.append(float(lib.kneil_classifier_vote(buf)))
            rule.append(int(r))
            prob.append([float(x) for x in pr])
    return raw, vote, rule, prob


def py_features(a):
    b = S3.T.apply_lowpass(np.asarray(a, np.float64), 50.0, 6.0).astype(np.float32)
    Wn = int(50 * W)
    return np.array([S3.T.features(S3.T_lib(), b[s:s + Wn, 0], b[s:s + Wn, 1], b[s:s + Wn, 2], 50.0)
                     for s in range(0, len(b) - Wn + 1, 50)], np.float32).reshape(-1, S3.T.NF)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description='KNEIL step E checks')
    ap.add_argument('--no-export', action='store_true', help='do not re-run the export')
    ap.add_argument('--quick', action='store_true', help='fewer streams')
    a = ap.parse_args()
    print(VERSION, flush=True)
    out = config.out_dir('stepE', 'E1')
    res = {'version': VERSION}
    with S1.Tee(os.path.join(out, 'check_step_e_log.txt')):
        print(f'{VERSION} | {config.VERSION} | {np.datetime64("now", "s")}')
        print(f'lib {LIB}  out {out}')
        t0 = time.time()
        if not a.no_export:
            print('\n--- export (check 2) ---')
            r = subprocess.run([sys.executable, os.path.join(config.WORKSPACE, 'pipeline', 'export_v4.py')],
                               capture_output=True, text=True, cwd=config.WORKSPACE)
            print(r.stdout.strip()[-1200:])
            if r.returncode:
                print(r.stderr.strip()); return 1
        info = os.path.join(config.V4_OUT, 'tinyml_final_v4_lp6', 'counts.json')
        cnt = json.load(open(info))
        print(f'\nexport: forest {cnt["forest_nodes"]} nodes, tree {cnt["tree_nodes"]} nodes, '
              f'{cnt["vectors"]} test vectors, {cnt["rows"]} training rows')
        res['export'] = cnt
        lib, so = build_dll()
        model = __import__('joblib').load(os.path.join(config.V4_OUT, 'tinyml_final_v4_lp6',
                                                       'model_forest.joblib'))
        Wn = int(50 * W)

        # ---------------------------------------------------------- check 4
        print('\n--- check 4: C vs Python on raw streams ---')
        streams = check4_streams(a.quick)
        rows, mism, rule_bad, n_win = [], [], 0, 0
        roll = {1: np.ones(1, np.int16)}
        n_pred_diff = 0
        for name, arr in streams:
            raw, vote, rule, prob = c_windows(lib, arr)
            Xp = py_features(arr)
            k = min(len(raw), len(Xp))
            if len(Xp) != len(raw):
                print(f'  {name}: C {len(raw)} windows, Python {len(Xp)} (using {k})')
            r = np.array(raw[:k])
            sk_vote = forest_votes(model, Xp[:k])          # what the exported C model does (emlearn voting)
            sk_pred = model.predict(Xp[:k])                # sklearn: averaged leaf probabilities
            n_pred_diff += int((sk_pred != r).sum())
            for i in range(k):
                n_win += 1
                if int(sk_vote[i]) != int(raw[i]):
                    mism.append(dict(stream=name, window=i, raw_c=raw[i], vote_sklearn=int(sk_vote[i]),
                                     vote_c=vote[i], proba_c=prob[i]))
                exp = int(SR.apply_rule(np.array([raw[i]], np.int8), np.array([vote[i]], np.float32), roll,
                                        0.60, 1, 1)[0])
                if exp != rule[i]:
                    rule_bad += 1
            rows.append(dict(stream=name, windows=k,
                             raw_agree_pct=100.0 * float((sk_vote[:k] == r).mean())))
        agree = 100.0 * (n_win - len(mism)) / n_win
        print(f'  {len(streams)} streams, {n_win} windows: raw class identical to the sklearn majority vote '
              f'{agree:.4f} % ({len(mism)} mismatches); C rule vs apply_rule mismatches {rule_bad}')
        print(f'  (sklearn predict() averages leaf probabilities and differs on {n_pred_diff} windows = '
              f'{100.0 * n_pred_diff / n_win:.2f} %: the emlearn export votes with the trees, it does not average '
              f'leaf distributions)')
        for m in mism[:10]:
            print(f'    mismatch {m["stream"]} window {m["window"]}: C {m["raw_c"]} (vote {m["vote_c"]:.2f}) '
                  f'vs vote {m["vote_sklearn"]}')
        pd.DataFrame(rows).to_csv(os.path.join(out, 'check4_streams.csv'), index=False)
        pd.DataFrame(mism).to_csv(os.path.join(out, 'check4_mismatches.csv'), index=False)
        res['check4'] = dict(streams=len(streams), windows=n_win, raw_agree_pct=agree, raw_mismatches=len(mism),
                             rule_mismatches=rule_bad, sklearn_predict_differs=n_pred_diff)
        print(f'  PASS: {"yes" if agree >= 99.9 and rule_bad == 0 else "NO"}')

        # ---------------------------------------------------------- check 5
        print('\n--- check 5: events, C metrics vs transition_events R1 (V4half 4 s seed 0) ---')
        A = C.load(W)
        Z = np.load(os.path.join(config.out_dir('stepD', 'D2'), 'pred_V4half_W4s_8cls_seed0.npz'))
        pred, proba = Z['pred'], Z['proba']
        times = TE.window_times(A, W)
        ev_rows, tot_c, tot_py = [], {}, {}
        st = A['stream']
        for sid in np.unique(st):
            m = st == sid
            pr, pb = pred[m], proba[m]
            if not len(pr):
                continue
            # C
            mb = ctypes.create_string_buffer(8192)
            lib.kneil_metrics_reset(mb)
            for i in range(len(pr)):
                lib.kneil_metrics_push(mb, int(pr[i]), float(pb[i, pr[i]]), 0.0, 0.0, 0.0)
            sb = ctypes.create_string_buffer(40)
            lib.kneil_metrics_summary(mb, sb)
            s = MR.decode(sb.raw)
            # Python (R1 by transition_events + the same run rule for bed_transfer); a run whose end is in the last
            # three windows is never closed by the C, so it is counted separately
            py = r1_events_with_end(pr, times[m], W)
            n_sts = sum(1 for _, d, i1 in py if d == 'sit_to_stand' and i1 <= len(pr) - 3)
            n_s2s = sum(1 for _, d, i1 in py if d == 'stand_to_sit' and i1 <= len(pr) - 3)
            n_bed = bed_events(pr)
            last3 = sum(1 for _, _, i1 in py if i1 > len(pr) - 3)
            ds = A['ds'][m][0]
            src = ('simulation' if A['src'][m][0] == 'sim' else
                   'Luo' if ds == 'Luo' else 'WearGait-PD' if ds == 'WearGait-PD' else
                   'CeTI' if ds == 'CeTI' else ds)
            for src_name, c_v, p_v in (('sts', s['n_sit_to_stand'], n_sts), ('s2s', s['n_stand_to_sit'], n_s2s),
                                       ('bed', s['n_bed_transfer'], n_bed)):
                k = (src, src_name)
                tot_c[k] = tot_c.get(k, 0) + c_v
                tot_py[k] = tot_py.get(k, 0) + p_v
            ev_rows.append(dict(stream=int(sid), source=src, c_sts=s['n_sit_to_stand'], py_sts=n_sts,
                                c_s2s=s['n_stand_to_sit'], py_s2s=n_s2s, c_bed=s['n_bed_transfer'], py_bed=n_bed,
                                py_events_in_last3=last3))
        pd.DataFrame(ev_rows).to_csv(os.path.join(out, 'check5_events_per_stream.csv'), index=False)
        print(f'  {"source":14s} {"kind":4s} {"C":>7s} {"Python":>7s} {"diff":>6s}')
        ok5 = True
        for k in sorted(tot_c):
            d = tot_c[k] - tot_py[k]
            print(f'  {k[0]:14s} {k[1]:4s} {tot_c[k]:7d} {tot_py[k]:7d} {d:6d}')
            if d != 0:
                ok5 = False
        n_last3 = int(sum(r['py_events_in_last3'] for r in ev_rows))
        print(f'  Python events that end within the last 3 windows of a stream: {n_last3} '
              f'(the C counts a run only after it has closed)')
        res['check5'] = dict(totals={f'{k[0]}/{k[1]}': tot_c[k] for k in tot_c},
                             python={f'{k[0]}/{k[1]}': tot_py[k] for k in tot_py}, last3_events=n_last3)
        print(f'  PASS: {"yes" if ok5 else "see the differences above"}')

        # ---------------------------------------------------------- check 6
        print('\n--- check 6: metrics_ref vs C summary on the check-4 streams ---')
        bad6, n6, examples = 0, 0, []
        for name, arr in streams:
            raw, vote, rule, prob = c_windows(lib, arr)
            mb = ctypes.create_string_buffer(8192)
            lib.kneil_metrics_reset(mb)
            ref = MR.Metrics()
            for i in range(len(raw)):
                lib.kneil_metrics_push(mb, int(raw[i]), float(vote[i]), 0.0, 0.0, 0.0)
                ref.push(int(raw[i]), float(vote[i]), 0.0, 0.0, 0.0)
            sb = ctypes.create_string_buffer(40)
            lib.kneil_metrics_summary(mb, sb)
            n6 += 1
            if sb.raw != ref.summary_bytes():
                bad6 += 1
                print(f'  summary differs on {name}:\n    C   {MR.decode(sb.raw)}\n    ref {ref.summary()}')
            elif len(examples) < 3:
                examples.append((name, MR.decode(sb.raw)))
        for name, e in examples:
            print(f'  example {name}: walk {e["minutes_by_class"][0]} min, still {e["minutes_by_class"][3]} min '
                  f'(sit {e["minutes_sitting"]} / stand {e["minutes_standing"]} / unknown {e["minutes_still_unknown"]}), '
                  f'lying {e["minutes_by_class"][4]} min, stairs {e["minutes_by_class"][1]}/{e["minutes_by_class"][2]} min, '
                  f'events s2s {e["n_sit_to_stand"]}/{e["n_stand_to_sit"]}/bed {e["n_bed_transfer"]}, steps {e["steps"]}, '
                  f'cadence {e["cadence_x10"] / 10:.1f}, seated tilt {e["sit_tilt_x10"] / 10:.1f} deg')
        print(f'  {n6} streams, {bad6} different summaries, size {len(ref.summary_bytes())} bytes')
        res['check6'] = dict(streams=n6, different=bad6, bytes=len(ref.summary_bytes()))
        print(f'  PASS: {"yes" if bad6 == 0 else "NO"}')

        # ---------------------------------------------------------- check 7
        print('\n--- check 7: sizes and time ---')
        r = subprocess.run([sys.executable, os.path.join(LIB, 'tests', 'run_host_test.py')],
                           capture_output=True, text=True, cwd=LIB)
        for line in r.stdout.splitlines():
            if line.startswith(('sizes:', 'library ', 'HOST TEST')):
                print('  ' + line)
        name, arr = streams[0]
        buf = ctypes.create_string_buffer(8192)
        lib.kneil_classifier_init(buf)
        t1 = time.perf_counter()
        for i in range(len(arr)):
            lib.kneil_classifier_push(buf, float(arr[i, 0]), float(arr[i, 1]), float(arr[i, 2]))
        dt = time.perf_counter() - t1
        nw = max(1, (len(arr) - Wn) // 50 + 1)
        print(f'  {len(arr)} samples in {dt * 1e3:.0f} ms = {dt / len(arr) * 1e6:.2f} us/sample, '
              f'{dt / nw * 1e6:.1f} us/window ({nw} windows)')
        res['check7'] = dict(us_per_sample=dt / len(arr) * 1e6, us_per_window=dt / nw * 1e6,
                             host_test_pass='HOST TEST: PASS' in r.stdout,
                             lines=[l for l in r.stdout.splitlines() if l.startswith('sizes:')])

        # ---------------------------------------------------------- check 8
        print('\n--- check 8: export sanity (in-sample) ---')
        X = A['X']
        proba_all = model.predict_proba(X)
        raw_all = proba_all.argmax(1).astype(np.int8)
        vote_all = proba_all[np.arange(len(raw_all)), raw_all]
        rule_all = np.array([SR.apply_rule(np.array([r], np.int8), np.array([v], np.float32), roll, 0.60, 1, 1)[0]
                             for r, v in zip(raw_all, vote_all)], np.int8)
        y = C.y_for(A, 8)
        for label, mask in (('Luo FE', (A['ds'] == 'Luo') & (A['surface'] == 'FE')),
                            ('Lencioni fast', (A['ds'] == 'Lencioni') & (A['speed_abs'] == 'fast'))):
            m = mask & (y == 0)
            b = 100.0 * float(np.isin(raw_all[m], (1, 2)).mean())
            f = 100.0 * float(np.isin(rule_all[m], (1, 2)).mean())
            print(f'  {label}: {int(m.sum())} walking windows, walking called stairs {b:.2f} % before the rule, '
                  f'{f:.2f} % after')
            res.setdefault('check8', {})[label] = dict(windows=int(m.sum()), before=b, after=f)
        print(f'\nall results in {out}  ({(time.time() - t0) / 60:.1f} min)')
        open(os.path.join(out, 'check_step_e.json'), 'w').write(json.dumps(res, indent=1, default=float))
    return 0


def r1_events_with_end(pred, t, win):
    """transition_events.detect for rule R1, but also returning the last window index of each run."""
    tr = np.flatnonzero(np.isin(pred, (5, 6)))
    if len(tr) == 0:
        return []
    groups, cur = [], [tr[0]]
    for i in tr[1:]:
        if i - cur[-1] <= 2:
            cur.append(i)
        else:
            groups.append(cur); cur = [i]
    groups.append(cur)
    out = []
    for g in groups:
        i0, i1 = g[0], g[-1]
        lo, hi = max(0, i0 - 3), min(len(pred), i1 + 4)
        if not np.any(pred[lo:hi] == 3):
            continue
        vals, cnt = np.unique(pred[g], return_counts=True)      # only the transition windows of the run
        order = np.argsort(-cnt, kind='stable')
        if len(cnt) > 1 and cnt[order[0]] == cnt[order[1]]:     # tie: the first window of the run decides
            direction = 'sit_to_stand' if pred[i0] == 5 else 'stand_to_sit'
        else:
            direction = 'sit_to_stand' if vals[order[0]] == 5 else 'stand_to_sit'
        out.append((0.5 * (t[i0] + t[i1] + win), direction, i1))
    return out


def bed_events(pred):
    """bed_transfer runs (same run rule as the transitions, no still condition): 1-gap merge, 2 non-bed windows end."""
    tr = np.flatnonzero(pred == 7)
    if not len(tr):
        return 0
    groups, cur = [], [tr[0]]
    for i in tr[1:]:
        if i - cur[-1] <= 2:
            cur.append(i)
        else:
            groups.append(cur); cur = [i]
    groups.append(cur)
    n = 0
    for g in groups:
        if g[-1] + 2 < len(pred):          # the C counts it only when it has closed
            n += 1
    return n


if __name__ == '__main__':
    raise SystemExit(main())


