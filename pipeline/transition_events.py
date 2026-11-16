"""
KNEIL V4 step D3 part A: sit-to-stand and stand-to-sit as EVENTS, not windows.   transition_events 1.0, 16 Nov 2026

The chip counts a transition once per event. This module turns the window predictions of a stream into events and
scores them against the per-sample ground truth of the source.

Detection (per stream, time order, hop 1 s, window t covers seconds t .. t + W):
  R0: a maximal run of windows predicted sit_to_stand or stand_to_sit; runs separated by one other window are merged;
      direction = majority class of the run; event time = centre of the run, (t_first + t_last + W) / 2.
  R1: R0, kept only if a window predicted `still` lies within 3 windows before or after the run.

Ground truth (from the per-sample labels, never from the windows):
  simulation (v1.6 synthetic, Camargo simulated): every run of sit_to_stand / stand_to_sit samples in the source CSV
      (50 Hz labels) = one event;
  CeTI s01 recordings: sitting run -> standing run (transition samples allowed between) = sit_to_stand, reverse =
      stand_to_sit, from <rec>|labels in the stage 2 npz;
  WearGait-PD TUG: sitting <-> non-sitting change, same source (APPROXIMATE: its labels come from the HAR labeller).

Evaluation per source and rule: event recall and precision with |t_det - t_true| <= W/2 + 2 s and one-to-one matching,
direction errors counted separately, and false events per hour on recordings without transitions.

CLI: python pipeline/transition_events.py [--win 2 3 4 5] [--variants ...] [--seeds ...] [--one]
"""
import argparse
import glob
import os
import re
import sys
import time

import numpy as np
import pandas as pd

import config
import cv_v4 as C
import stage01 as S1
import stage2 as S2
import stage3 as S3
import stage3_v4 as S4

VERSION = 'transition_events 1.0'
HOP = 1.0
STS, S2S, STILL = 5, 6, 3                      # 8-class prefixes of the PREDICTIONS: sit_to_stand, stand_to_sit, still
STS9, S2S9 = 6, 7                              # 9-class ids in the source label arrays (train_kneel_tinyml.MAP)
MIN_RUN = 5                                    # source posture runs shorter than 0.1 s are ignored (labeller jitter)
RULES = ('R0', 'R1')
TRUTH_SOURCES = ('simulation', 'CeTI s01', 'TUG (approx)')
NO_EVENT_SOURCES = ('Luo (no CALIB)', 'WearGait-PD SelfPace', 'WearGait-PD HurriedPace', 'Camargo (no transition)')
_OUT = {}


# ------------------------------------------------------------------ window start times
def sim_files():
    v16 = [f for f in sorted(glob.glob(os.path.join(config.CACHE, 'sim', 'v16', '*.csv')))
           if os.path.basename(f) != 'patients.csv']
    cam = [f for f in sorted(glob.glob(os.path.join(config.CACHE, 'sim', 'cam', '*.csv')))
           if os.path.basename(f) != 'patients.csv']
    return [(f, 'v1.6 synthetic') for f in v16] + [(f, 'Camargo simulated') for f in cam]


def sim_labels(f):
    """50 Hz label codes of one simulation CSV, exactly as load_windows_w builds them."""
    df = pd.read_csv(f, usecols=['activity'])
    lab = df['activity'].map(S4.T.MAP).fillna(-1).values.astype(int)
    n50 = int(round(len(lab) * 50.0 / 100.0))
    return lab[np.minimum(np.round(np.arange(n50) * 100.0 / 50).astype(int), len(lab) - 1)]


def runs(codes, value):
    """(start, end) sample indices of the maximal runs where codes == value (end exclusive)."""
    m = (codes == value).astype(np.int8)
    d = np.diff(np.r_[0, m, 0])
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def sim_truth_and_starts(win):
    """Per stream id (in load_sim order): window start times (s) and the true events of that file."""
    key = ('sim', win)
    if key in _OUT:
        return _OUT[key]
    W, H = int(50 * win), 50
    starts, truth, files = {}, {}, []
    sid = 0
    for f, ds in sim_files():
        lab = sim_labels(f)
        st = []
        for s in range(0, len(lab) - W + 1, H):
            l = lab[s:s + W]; vals, cnt = np.unique(l, return_counts=True); j = int(np.argmax(cnt))
            if vals[j] < 0 or cnt[j] < 0.6 * W:
                continue
            st.append(s / 50.0)
        if not st:
            continue
        starts[sid] = np.array(st)
        ev = [(0.5 * (a + b) / 50.0, 'sit_to_stand') for a, b in runs(lab, STS9)] + \
             [(0.5 * (a + b) / 50.0, 'stand_to_sit') for a, b in runs(lab, S2S9)]
        truth[sid] = dict(ds=ds, rec=os.path.basename(f), events=sorted(ev), has_transition=bool(ev))
        files.append((sid, f, ds))
        sid += 1
    _OUT[key] = (starts, truth, files)
    return _OUT[key]


def window_times(A, win):
    """Start time (s) of every window row. Stage 2 streams start at sample 0 and skip no window, so the time is the
    row index within the stream; simulation streams have their own surviving starts (min_share skips windows)."""
    t = np.zeros(len(A['y']))
    st = A['stream']
    b = np.r_[0, np.flatnonzero(np.diff(st) != 0) + 1]
    e = np.r_[b[1:], len(st)]
    starts_sim = sim_truth_and_starts(win)[0]
    for a_, b_ in zip(b, e):
        sid = int(st[a_])
        if A['src'][a_] == 'sim':
            s = starts_sim.get(sid)
            if s is None or len(s) != b_ - a_:
                raise RuntimeError(f'stream {sid}: {b_ - a_} rows but {0 if s is None else len(s)} simulation starts')
            t[a_:b_] = s
        else:
            t[a_:b_] = np.arange(b_ - a_) * HOP
    return t


# ------------------------------------------------------------------ ground truth (stage 2)
def change_events(codes, mode):
    """sitting <-> standing (mode 'sit_stand') or sitting <-> anything (mode 'sit_any') changes. Posture runs shorter
    than MIN_RUN samples are ignored (single-sample posture labels are labeller jitter)."""
    if mode == 'sit_stand':
        sel = np.flatnonzero(np.isin(codes, [S2.CODE['sitting'], S2.CODE['standing']]))
        vals = codes[sel]
        if len(vals) == 0:
            return []
        ch = np.r_[0, np.flatnonzero(np.diff(vals) != 0) + 1]
        ln = np.r_[ch[1:], len(vals)] - ch
        good = np.zeros(len(vals), bool)
        for i in np.flatnonzero(ln >= MIN_RUN):
            good[ch[i]:ch[i] + ln[i]] = True
        seq_t, idx = vals[good], sel[good]
    else:
        seq_t = np.where(codes == S2.CODE['sitting'], 1, 0)
        idx = np.arange(len(codes))
    if len(seq_t) == 0:
        return []
    change = np.flatnonzero(np.diff(seq_t) != 0)
    out = []
    for k in change:
        if mode == 'sit_stand':
            before = seq_t[k]
            out.append((0.5 * (idx[k] + idx[k + 1]) / 50.0,
                        'sit_to_stand' if before == S2.CODE['sitting'] else 'stand_to_sit'))
        else:
            out.append((idx[k + 1] / 50.0, 'sit_to_stand' if seq_t[k] == 1 else 'stand_to_sit'))
    return out


def stage2_truth(log=print):
    """(ds, rec) -> true events for CeTI s01 and WearGait-PD TUG, from the stage 2 per-sample labels."""
    key = 'stage2'
    if key in _OUT:
        return _OUT[key]
    out, counts = {}, []
    for ds, match, mode, label in (('CeTI', lambda r: str(r).startswith('s01'), 'sit_stand', 'CeTI s01'),
                                   ('WearGait-PD', lambda r: str(r) == 'TUG', 'sit_any', 'TUG (approx)')):
        base = os.path.join(config.RESULTS, 'virtual_implant')
        I = pd.read_csv(os.path.join(base, f'stage2_index_{ds}.csv'))
        I = I[I.task.astype(str).map(match) & I.plausible.astype(bool)]
        for person, rows in I.groupby('person'):
            Z = np.load(os.path.join(base, 'stage2', ds, rows.file.iloc[0]))
            for r in rows.itertuples():
                k = f'{r.task}|labels'
                if k not in Z.files:
                    continue
                names = [str(x) for x in Z['label_names']] if 'label_names' in Z.files else S2.LABELS
                codes = np.array([S2.CODE.get(names[c], -1) if 0 <= c < len(names) else -1 for c in Z[k]])
                ev = change_events(codes, mode)
                out.setdefault((ds, str(person), str(r.task)), ev)
                counts.append(dict(source=label, person=str(person), rec=str(r.task), sit_to_stand=int(sum(e[1] == 'sit_to_stand' for e in ev)),
                                   stand_to_sit=int(sum(e[1] == 'stand_to_sit' for e in ev))))
        log(f'  {label}: {len({k for k in out if k[0] == ds})} recordings')
    K = pd.DataFrame(counts)
    _OUT[key] = (out, K)
    return _OUT[key]


# ------------------------------------------------------------------ detection
def detect(pred, t, W, rule):
    """Events (time, direction) of one stream."""
    tr = np.flatnonzero(np.isin(pred, (STS, S2S)))
    if len(tr) == 0:
        return []
    groups, cur = [], [tr[0]]
    for i in tr[1:]:
        if i - cur[-1] <= 2:                       # contiguous or separated by one other window
            cur.append(i)
        else:
            groups.append(cur); cur = [i]
    groups.append(cur)
    out = []
    for g in groups:
        i0, i1 = g[0], g[-1]
        if rule == 'R1':
            lo, hi = max(0, i0 - 3), min(len(pred), i1 + 4)
            if not np.any(pred[lo:hi] == STILL):
                continue
        vals, cnt = np.unique(pred[i0:i1 + 1], return_counts=True)
        j = int(np.argmax(cnt))
        direction = 'sit_to_stand' if vals[j] == STS else 'stand_to_sit'
        out.append((0.5 * (t[i0] + t[i1] + W), direction))
    return out


def match(true, det, tol):
    """One-to-one matching; returns matched, direction errors, false detections."""
    used = np.zeros(len(det), bool)
    matched = direrr = 0
    for tt, td in sorted(true):
        best, bd = -1, np.inf
        for k, (dt, dd) in enumerate(det):
            if used[k]:
                continue
            d = abs(dt - tt)
            if d <= tol and d < bd:
                best, bd = k, d
        if best < 0:
            continue
        used[best] = True
        if det[best][1] == td:
            matched += 1
        else:
            direrr += 1
    return matched, direrr, int((~used).sum())


# ------------------------------------------------------------------ main
def evaluate(A, pred, win, rule, times):
    """Per-source event metrics of one run and one rule."""
    tol = win / 2.0 + 2.0
    ds, src, st = A['ds'], A['src'], A['stream']
    sim_starts, sim_truth, _ = sim_truth_and_starts(win)
    s2_truth, _ = stage2_truth(log=lambda *a: None)
    res = {}
    # --- simulation: one stream = one recording
    tp = direrr = fp = n_true = n_det = 0
    for sid, info in sim_truth.items():
        m = st == sid
        if not m.any():
            continue
        det = detect(pred[m], times[m], win, rule)
        a, b, c = match(info['events'], det, tol)
        tp += a; direrr += b; fp += c; n_true += len(info['events']); n_det += len(det)
    res['simulation'] = dict(n_true=n_true, n_detected=n_det, matched=tp, direction_errors=direrr, false_detected=fp)
    # --- CeTI s01 and TUG: per recording, detections of all its streams merged (both legs, one implant)
    for source, d in (('CeTI s01', 'CeTI'), ('TUG (approx)', 'WearGait-PD')):
        tp = direrr = fp = n_true = n_det = 0
        for (ds_name, person, rec), true in s2_truth.items():
            if ds_name != d:
                continue
            m = (ds == d) & (A['grp'] == f'{d}:{person}') & (A['rec'] == rec)
            if not m.any():
                continue
            det = []
            for sid in np.unique(st[m]):
                det += detect(pred[(st == sid)], times[(st == sid)], win, rule)
            det.sort()
            ded = []
            for e in det:                                   # merge near-simultaneous detections of the two legs
                if any(abs(e[0] - f[0]) <= 1.0 for f in ded):
                    continue
                ded.append(e)
            a, b, c = match(true, ded, tol)
            tp += a; direrr += b; fp += c; n_true += len(true); n_det += len(ded)
        res[source] = dict(n_true=n_true, n_detected=n_det, matched=tp, direction_errors=direrr, false_detected=fp)
    return res


def false_events(A, pred, win, rule, times):
    """Detected events per hour on recordings without transitions."""
    ds, src, st, rec = A['ds'], A['src'], A['stream'], A['rec']
    sim_starts, sim_truth, _ = sim_truth_and_starts(win)
    out = {}
    recs = np.array([str(x) for x in rec], object)
    groups = {
        'Luo (no CALIB)': (ds == 'Luo') & ~np.array(['CALIB' in x for x in recs]),
        'WearGait-PD SelfPace': (ds == 'WearGait-PD') & (recs == 'SelfPace'),
        'WearGait-PD HurriedPace': (ds == 'WearGait-PD') & (recs == 'HurriedPace'),
    }
    for name, m in groups.items():
        n, hours = 0, 0.0
        for sid in np.unique(st[m]):
            r = st == sid
            n += len(detect(pred[r], times[r], win, rule))
            hours += (int(r.sum()) - 1) * HOP + win
        out[name] = dict(events=n, hours=hours / 3600.0, per_hour=n / (hours / 3600.0) if hours else np.nan)
    n, hours = 0, 0.0
    for sid, info in sim_truth.items():
        if info['ds'] != 'Camargo simulated' or info['has_transition']:
            continue
        r = st == sid
        if not r.any():
            continue
        n += len(detect(pred[r], times[r], win, rule))
        hours += (int(r.sum()) - 1) * HOP + win
    out['Camargo (no transition)'] = dict(events=n, hours=hours / 3600.0, per_hour=n / (hours / 3600.0) if hours else np.nan)
    return out


def md_table(df):
    head = '| ' + ' | '.join([str(df.index.name or '')] + [str(c) for c in df.columns]) + ' |'
    out = [head, '|' + '---|' * (len(df.columns) + 1)]
    for i, r in df.iterrows():
        out.append('| ' + ' | '.join([str(i)] + [('' if pd.isna(v) else str(v)) for v in r]) + ' |')
    return '\n'.join(out)


def write_outputs(rows, out_dir, log=print):
    R = pd.DataFrame(rows)
    key = ['variant', 'win', 'seed', 'rule', 'table', 'source', 'metric']
    runs_csv = os.path.join(out_dir, 'transition_events_runs.csv')
    if os.path.exists(runs_csv):
        old = pd.read_csv(runs_csv)
        tri = set(map(tuple, R[key].drop_duplicates().itertuples(index=False)))
        keep = ~pd.Series(list(zip(*[old[c] for c in key])), index=old.index).isin(tri)
        R = pd.concat([old[keep], R], ignore_index=True)
    R = R.sort_values(key)
    R.to_csv(runs_csv, index=False)
    agg = (R.groupby(['variant', 'win', 'rule', 'table', 'source', 'metric'], dropna=False)
           .agg(value=('value', 'mean'), sd=('value', 'std'), nseeds=('value', 'size')).reset_index())
    agg.to_csv(os.path.join(out_dir, 'transition_events_results.csv'), index=False)
    recs = agg.to_dict('records')
    runs = sorted({f'{r["variant"]} {r["win"]:g}s' for r in recs}, key=lambda s: (float(s.split()[-1][:-1]), s))
    parts = [f'# Transitions as events ({VERSION})', '',
             f'{len(runs)} runs (mean over seeds): ' + ', '.join(f'`{r}`' for r in runs), '',
             'Recall and precision in %, false events per hour. Matching: same direction, |dt| <= W/2 + 2 s, one-to-one.',
             'CeTI s01 and TUG truth are obtained from the per-sample stage 2 labels; TUG labels are approximate.', '']
    wr = window_recall()
    if wr is not None:
        parts += ['## window-level recall on the simulation (from D2, % of windows)', '', wr, '']

    def sub(table, metric):
        d = [r for r in recs if r['table'] == table and r['metric'] == metric]
        if not d:
            return '(no data)'
        T = pd.DataFrame(d)
        T['run'] = T.variant + ' ' + T.win.map(lambda w: f'{w:g}s') + ' ' + T.rule
        T['row'] = T.source
        P = T.pivot_table(index='row', columns='run', values='value', aggfunc='first')
        Q = T.pivot_table(index='row', columns='run', values='sd', aggfunc='first').reindex(index=P.index, columns=P.columns)
        out = P.copy().astype(object)
        for c in P.columns:
            out[c] = [f'{v:.1f} ({s:.1f})' if np.isfinite(s) else f'{v:.1f}' for v, s in zip(P[c], Q[c])]
        out.index.name = 'source'
        return md_table(out)

    for metric, title in (('event_recall_pct', 'event recall, %'), ('event_precision_pct', 'event precision, %'),
                          ('direction_error_pct', 'direction errors, % of true events'),
                          ('false_per_hour', 'false events per hour')):
        parts += [f'## {title}', '', sub('events' if metric != 'false_per_hour' else 'false', metric), '']
    path = os.path.join(out_dir, 'transition_events_summary.md')
    open(path, 'w', encoding='utf-8').write('\n'.join(parts) + '\n')
    log(f'  saved {runs_csv}, transition_events_results.csv and {path}')
    return agg


def window_recall():
    """Window-level recall of sit_to_stand / stand_to_sit on the simulation, from the D2 tables (mean over seeds)."""
    p = os.path.join(config.out_dir('stepD', 'D2'), 'D2_results.csv')
    if not os.path.exists(p):
        return None
    T = pd.read_csv(p)
    d = T[(T.table == 'a_sim') & (T.metric == 'recall_pct') & T.key.isin(['sit_to_stand', 'stand_to_sit'])]
    if d.empty:
        return None
    d = d.copy()
    d['run'] = d.variant + ' ' + d.win.map(lambda w: f'{w:g}s')
    P = d.pivot_table(index='key', columns='run', values='value', aggfunc='first')
    Q = d.pivot_table(index='key', columns='run', values='sd', aggfunc='first')
    out = P.copy().astype(object)
    for c in P.columns:
        out[c] = [f'{v:.1f} ({s:.1f})' if np.isfinite(s) else f'{v:.1f}' for v, s in zip(P[c], Q[c])]
    out.index.name = 'class'
    return md_table(out)


def main():
    ap = argparse.ArgumentParser(description='KNEIL V4 D3 part A: transition events')
    ap.add_argument('--win', type=float, nargs='+', default=[])
    ap.add_argument('--variants', nargs='+', default=[])
    ap.add_argument('--seeds', type=int, nargs='+', default=[])
    ap.add_argument('--one', action='store_true', help='one run only (V3recipe 2 s seed 0) with examples')
    a = ap.parse_args()
    print(VERSION, flush=True)
    out_dir = config.out_dir('stepD', 'D3')
    with S1.Tee(os.path.join(out_dir, 'transition_events_log.txt')):
        print(f'{VERSION} | {C.VERSION} | {config.VERSION} | {np.datetime64("now", "s")}')
        runs = [r for r in C_files() if (not a.win or r[1] in a.win) and (not a.variants or r[0] in a.variants)
                and (not a.seeds or r[2] in a.seeds)]
        if a.one:
            runs = [r for r in runs if r[0] == 'V3recipe' and r[1] == 2 and r[2] == 0]
        print(f'  {len(runs)} runs')
        s2_truth, K = stage2_truth()
        print('\ntrue events per recording (CeTI s01 and TUG):')
        print(K.groupby(['source', 'rec']).agg(recordings=('person', 'size'), sit_to_stand=('sit_to_stand', 'sum'),
                                               stand_to_sit=('stand_to_sit', 'sum')).to_string())
        _, sim_truth, files = sim_truth_and_starts(2.0)
        ev = [len(v['events']) for v in sim_truth.values()]
        print(f'\nsimulation at 2 s: {len(ev)} recordings, {sum(ev)} true events, '
              f'{sum(1 for v in sim_truth.values() if not v["events"])} without a transition')
        rows, t0, cache = [], time.time(), {}
        for variant, win, seed in runs:
            key = (win, seed)
            if key not in cache:                       # the window file and its times do not depend on the variant
                A = C.load(win)
                cache[key] = (A, window_times(A, win))
            A, times = cache[key]
            pred = np.load(os.path.join(config.out_dir('stepD', 'D2'),
                                        f'pred_{variant}_W{win:g}s_8cls_seed{seed}.npz'))['pred']
            if a.one:
                pr = stage2_truth()[0]
                for sid in list(sim_truth)[:2]:
                    r = A['stream'] == sid
                    print(f'\n  example sim stream {sid} ({sim_truth[sid]["rec"]}): true '
                          f'{[f"{t:.1f} {d}" for t, d in sim_truth[sid]["events"]]}; R0 detected '
                          f'{[f"{t:.1f} {d}" for t, d in detect(pred[r], times[r], win, "R0")]}')
                for (dsn, person, rec), true in list(pr.items())[:2]:
                    r = (A['ds'] == dsn) & (A['grp'] == f'{dsn}:{person}') & (A['rec'] == rec)
                    if r.any():
                        det = [e for sid in np.unique(A['stream'][r]) for e in
                               detect(pred[A['stream'] == sid], times[A['stream'] == sid], win, 'R0')]
                        print(f'  example {dsn} {rec}: true {[f"{t:.1f} {d}" for t, d in true]}; R0 detected '
                              f'{[f"{t:.1f} {d}" for t, d in sorted(det)]}')
            for rule in RULES:
                ev = evaluate(A, pred, win, rule, times)
                fe = false_events(A, pred, win, rule, times)
                for source, m in ev.items():
                    for metric, num in (('event_recall_pct', m['matched'] / m['n_true'] * 100 if m['n_true'] else np.nan),
                                        ('event_precision_pct', m['matched'] / (m['matched'] + m['false_detected']) * 100
                                         if (m['matched'] + m['false_detected']) else np.nan),
                                        ('direction_error_pct', m['direction_errors'] / m['n_true'] * 100 if m['n_true'] else np.nan)):
                        rows.append(dict(variant=variant, win=win, seed=seed, rule=rule, table='events', source=source,
                                         metric=metric, value=float(num), n=int(m['n_true'])))
                for source, d in fe.items():
                    rows.append(dict(variant=variant, win=win, seed=seed, rule=rule, table='false', source=source,
                                     metric='false_per_hour', value=float(d['per_hour']), n=int(d['events'])))
            print(f'  {variant} {win:g}s seed {seed}: done ({(time.time() - t0) / 60:.1f} min)')
        T = write_outputs(rows, out_dir)
        print(f'\nrows {len(T)}, total {(time.time() - t0) / 60:.1f} min')
    return 0


def C_files():
    """Available D2 prediction files as (variant, win, seed)."""
    out = []
    for p in glob.glob(os.path.join(config.out_dir('stepD', 'D2'), 'pred_*_W*s_8cls_seed*.npz')):
        m = re.match(r'pred_(.+)_W([\d.]+)s_8cls_seed(\d+)\.npz$', os.path.basename(p))
        if m:
            out.append((m.group(1), float(m.group(2)), int(m.group(3))))
    return sorted(out, key=lambda t: (t[1], t[0], t[2]))


if __name__ == '__main__':
    raise SystemExit(main())
