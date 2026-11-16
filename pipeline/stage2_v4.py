"""
KNEIL stage 2 for V4: implant-site data from Luo 2020 and Lencioni 2019 (same output format as stage2.py).   v1.0, 16 Nov 2026
Output: <V4_OUT>/stage2/<dataset>/<person>.npz plus <V4_OUT>/stage2_index_<dataset>.csv (one row per recording and leg).
npz keys: '<task>|<R|L>|implant' (N x 3, g, device frame x anterior / y left / z superior, 50 Hz), '<task>|labels' (int16
per 50 Hz sample, names in 'label_names' = stage2.LABELS + the V4 labels appended, so the old codes are unchanged).

Luo (see docs/STEP_B_REPORT.md): raw CSVs (serial -> position fixed), shank sensors 5 cm above the ankle
  -> implant with lever arm LUO_GEOM; ONE tibia frame per person and leg (vimp.person_frame): up from the standing part of
  the CALIB trials, forward from the flat-even (FE) walking trials. Per sample: still (vimp.still_mask) -> 'standing',
  otherwise the trial's surface label: FE, CS, GR, BnkL, BnkR -> walking; StrU/StrD -> stairs_up/down; SlpU/SlpD -> slope_up/
  down; CALIB -> calibration. The wrist sensor is kept ('<task>|wrist_W', acc g + gyro rad/s, sensor frame, 50 Hz).
Lencioni: single strides of marker data. Per stride and leg: tibia axis z = FH -> LatCon direction (lateral markers);
  left-right from the pelvis (RxAsis - LxAsis); forward = walking direction; implant point = knee centre (LatCon moved
  medially by LEN_HALF_KNEE x height) - 2.5 cm along z + 5 mm along x. PERIODISED: the stride (one gait cycle) is
  detrended (the straight progression and the stair rise are removed: no acceleration), repeated LEN_CYCLES times,
  low-passed (zero lag, LEN_LP Hz), differentiated twice, gravity added, projected on the tibia frame, resampled to 50 Hz.
  Keys '<task>|<side>|implant' (periodised stream) and '<task>|<side>|cycle' (the middle cycle only, for per-stride tests).
"""
import argparse, json, os, re, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import stage01 as S1
import stage2 as S2
import v4_readers as R
import vimp as V

VERSION = 'stage2_v4 1.0'
FS = S2.FS
LABELS = S2.LABELS + ['slope_up', 'slope_down', 'calibration', 'toe_walking', 'heel_walking']
CODE = {n: i for i, n in enumerate(LABELS)}
G = 9.80665

LUO_ROOT = os.path.join(config.DATA_ROOT, 'Luo et. al. 2020')
LUO_SERIAL = {'shankR': '00B4329B', 'shankL': '00B432B6', 'thighR': '00B43293', 'thighL': '00B4328B', 'trunk': '00B432CC',
              'wrist': '00B43295'}
LUO_LABEL = {'FE': 'walking', 'CS': 'walking', 'GR': 'walking', 'BnkL': 'walking', 'BnkR': 'walking', 'StrU': 'stairs_up',
             'StrD': 'stairs_down', 'SlpU': 'slope_up', 'SlpD': 'slope_down', 'CALIB': 'calibration'}
LUO_GEOM = dict(distance=0.36, anterior=0.0, medial=0.0)   # sensor 5 cm above the malleolus -> implant (assumption, as PAMAP2)

LEN_ROOT = os.path.join(config.DATA_ROOT, 'Lencioni et. al. 2019')
LEN_LABEL = {'Walking': 'walking', 'StepUp': 'stairs_up', 'StepDown': 'stairs_down', 'ToeWalking': 'toe_walking',
             'HeelWalking': 'heel_walking'}
LEN_HALF_KNEE = 0.028            # half knee width / body height (assumption: ~5 cm at 1.75 m)
LEN_CYCLES = 7                   # periodised stream length in cycles (>= 5 s at the slowest stride)
LEN_LP = 8.0                     # Hz, zero-lag low-pass on positions before differentiation
SPEED_ABS = (1.0, 1.4)           # m/s: slow < 1.0 <= comfortable <= 1.4 < fast
SPEED_REL = (0.85, 1.15)         # x the person's median walking speed


class Store(S2.Store):
    """stage2.Store with the V4 label list."""
    def save(self, person, arrays, rows):
        arrays['label_names'] = np.array(LABELS)
        fn = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(person)) + '.npz'
        np.savez_compressed(os.path.join(self.dir, fn), **arrays)
        for r in rows:
            r.update(dataset=self.dataset, person=str(person), file=fn)
        self.index = pd.concat([self.index, pd.DataFrame(rows)], ignore_index=True)
        S1.save_csv(self.index, self.index_path)


def flag_by_walking(rows, key='side'):
    """The stage 1 lean rule (-5..+35 deg) holds for LEVEL walking only: stairs and slopes down lean more. A leg whose
    median level-walking lean is outside the rule has a suspect frame: all its recordings are flagged."""
    for s in {r[key] for r in rows}:
        t = [r['walk_tilt_deg'] for r in rows if r[key] == s and r['task_label'] == 'walking' and np.isfinite(r['walk_tilt_deg'])]
        ok = bool(t) and S1.TILT_OK[0] <= float(np.median(t)) <= S1.TILT_OK[1]
        for r in rows:
            if r[key] == s:
                r['plausible'] = ok and r.get('forward_matches_walking', True)
                r['leg_walking_tilt_deg'] = round(float(np.median(t)), 1) if t else np.nan


# ------------------------------------------------------------------------------------------------ Luo
def luo_trial_list(L, person):
    t = L.table(person, 'shankR', channels=())
    return [(int(tr), sf) for tr, sf in zip(t['Trial'], t['Surface'])]


def luo_read_sensor(person, trial, position):
    files = R.luo_csv_files(LUO_ROOT, person, trial)
    C = R.luo_csv_read(files[LUO_SERIAL[position]])
    return S1.fill(C['Acc']) / G, S1.fill(C['Gyr']), float(np.isnan(C['Acc']).any(1).mean())


def gen_luo(people=None, log=print):
    st = Store(config.V4_OUT, 'Luo')
    with R.Luo(os.path.join(LUO_ROOT, 'data.mat')) as L:
        allp = L.people()
        trials = {p: luo_trial_list(L, p) for p in (people or allp)}
    for p in (people or allp):
        if st.done(p):
            log(f'  Luo {p}: already done'); continue
        t0 = time.time()
        try:
            data = {}
            for tr, sf in trials[p]:
                data[tr] = dict(surface=sf, **{pos: luo_read_sensor(p, tr, pos) for pos in ('shankR', 'shankL', 'wrist')})
            arrays, rows = {}, []
            for side in 'RL':
                pos = f'shank{side}'
                stand = [data[tr][pos][:2] for tr, sf in trials[p] if sf == 'CALIB']
                walk = [data[tr][pos][:2] for tr, sf in trials[p] if sf == 'FE']
                gsign, T, note = 1.0, None, ''
                for gs in (1.0, -1.0):                              # retry with the gyroscope sign inverted (MHEALTH lesson)
                    T, note = V.person_frame(stand, [(f, gs * w) for f, w in walk], R.LUO_FS)
                    if T is None:
                        break
                    tilts = [S2.walk_check(S2.implant(f, gs * w, R.LUO_FS, T, LUO_GEOM, side))[0] for f, w in walk[:2]]
                    if np.median(tilts) > -3.0:
                        gsign = gs; break
                if T is None:
                    log(f'  Luo {p} {side}: no frame ({note})'); continue
                if gsign < 0:
                    note += '; gyroscope sign inverted'
                for tr, sf in trials[p]:
                    f, w, miss = data[tr][pos]
                    p50 = S2.implant(f, gsign * w, R.LUO_FS, T, LUO_GEOM, side)
                    key = f'{tr:02d}_{sf}'
                    lab = LUO_LABEL[sf]
                    if side == 'R':
                        still = V.still_mask(V.lowpass(f, 15, R.LUO_FS), V.lowpass(w, 15, R.LUO_FS), R.LUO_FS)
                        codes = np.where(still, CODE['standing'], CODE[lab]).astype(np.int16)
                        arrays[f'{key}|labels'] = S2.resample_labels(codes, R.LUO_FS, len(p50))
                        wf, ww, _ = data[tr]['wrist']
                        arrays[f'{key}|wrist_W'] = S2.resample(np.c_[wf, ww], R.LUO_FS)[:len(p50)]
                    codes50 = arrays[f'{key}|labels'][:len(p50)]
                    arrays[f'{key}|{side}|implant'] = p50[:len(codes50)]
                    tilt, ok = S2.walk_check(p50[:len(codes50)], codes50) if lab in ('walking', 'stairs_up', 'stairs_down', 'slope_up', 'slope_down') else (np.nan, True)
                    rows.append(dict(group=str(p), task=key, task_label=lab, surface=sf, side=side, seconds=round(len(p50) / FS, 1),
                                     still_s=round(float((codes50 == CODE['standing']).sum()) / FS, 1), missing_pct=round(100 * miss, 2),
                                     walk_tilt_deg=tilt, plausible=ok, frame=note, label_source='dataset surface + still detection'))
            if rows:
                flag_by_walking(rows)
                st.save(p, arrays, rows)
                d = pd.DataFrame(rows)
                tl = d[d.task_label == 'walking'].groupby('side').walk_tilt_deg.median().round(1).to_dict()
                log(f'  Luo {p}: {len(d) // 2} trials x 2 legs, walking lean {tl} deg, {int((~d.plausible).sum())} flagged, '
                    f'{time.time() - t0:.0f} s')
        except Exception as e:
            import traceback
            log(f'  Luo {p}: FAILED {e!r}\n{traceback.format_exc()}')
    return st.index


# ------------------------------------------------------------------------------------------------ Lencioni
def periodise(P, n_cycles):
    """P: (n, 3) one cycle. Remove the straight line from the first to the end point (constant velocity: no acceleration),
    repeat n_cycles times. Returns the repeated positions and the jump that was removed (m)."""
    n = len(P)
    trend = np.outer(np.arange(n) / n, P[-1] - P[0] + (P[-1] - P[-2]))   # end point extrapolated one sample: P[n] ~ P[0] + step
    Q = P - trend
    # what the loop cannot fix: the velocity at the end differs from the start (per sample step, m) -> a kink at the joint
    kink = float(np.linalg.norm((P[-1] - P[-2]) - (P[1] - P[0])))
    return np.tile(Q, (n_cycles, 1)), kink


def lencioni_implant(S, st, side, n_cycles=LEN_CYCLES, fc=LEN_LP):
    """Periodised implant specific force (g, device frame, at the marker rate) for one stride and leg."""
    fs = S['fs']; m = st['markers']; sd = 'Rx' if side == 'R' else 'Lx'
    H = S['height_cm'] / 100.0
    rep = {}
    jumps = []
    for k in (f'{sd}LatCon', f'{sd}FH', f'{sd}LatMal', 'RxAsis', 'LxAsis', 'Psis'):
        rep[k], j = periodise(m[k], n_cycles); jumps.append(j * fs)          # velocity mismatch end vs start, m/s
    lp = lambda x: V.lowpass(x, fc, fs)
    K, F, A = lp(rep[f'{sd}LatCon']), lp(rep[f'{sd}FH']), lp(rep[f'{sd}LatMal'])
    up = np.array([0.0, 1.0, 0.0])                                  # lab Y is vertical
    z = V.unit(K - A)                                               # tibia long axis (lateral line, knee - ankle)
    right = lp(rep['RxAsis'] - rep['LxAsis'])
    r = right - np.sum(right * z, 1, keepdims=True) * z
    y = -V.unit(r)                                                  # device y = subject's left
    x = np.cross(y, z)
    prog = m['Psis'][-1] - m['Psis'][0]; prog[1] = 0.0              # walking direction from the real (not detrended) pelvis
    fwd_ok = bool(np.mean(x @ prog) > 0)                            # x = y x z is anterior by construction: check only
    medial = LEN_HALF_KNEE * H * (y if side == 'R' else -y)         # medial = toward the other leg
    P = K + medial - 0.025 * z + 0.005 * x
    acc = np.gradient(np.gradient(P, 1 / fs, axis=0), 1 / fs, axis=0)
    f = (acc + G * up) / G
    dev = np.stack([np.sum(f * x, 1), np.sum(f * y, 1), np.sum(f * z, 1)], axis=1)
    return dev, max(jumps), fwd_ok


def gen_lencioni(max_subjects=None, log=print):
    st = Store(config.V4_OUT, 'Lencioni')
    files = R.lencioni_files(LEN_ROOT)[:max_subjects or None]
    for fp in files:
        S = R.lencioni_load(fp)
        person = S['name']
        if st.done(person):
            log(f'  Lencioni {person}: already done'); continue
        t0 = time.time()
        try:
            walk_speeds = [x['speed'] for x in S['strides'] if x['task'] == 'Walking']
            med = float(np.median(walk_speeds)) if walk_speeds else np.nan
            arrays, rows = {}, []
            for x in S['strides']:
                lab = LEN_LABEL.get(x['task'], 'other')
                key = f"{x['index']:03d}_{x['task']}"
                n_cycle = len(x['markers']['Psis'])
                for side in 'RL':
                    dev, jump, fwd_ok = lencioni_implant(S, x, side)
                    p50 = S2.resample(dev, S['fs'])
                    c0 = int(round((LEN_CYCLES // 2) * n_cycle * FS / S['fs'])); c1 = int(round((LEN_CYCLES // 2 + 1) * n_cycle * FS / S['fs']))
                    arrays[f'{key}|{side}|implant'] = p50
                    arrays[f'{key}|{side}|cycle'] = p50[c0:c1]
                    if side == 'R':
                        arrays[f'{key}|labels'] = np.full(len(p50), CODE[lab], np.int16)
                    tilt, ok = S2.walk_check(p50) if lab in ('walking', 'stairs_up', 'stairs_down') else (np.nan, True)
                    sp = x['speed']
                    rows.append(dict(group=person, task=key, task_label=lab, side=side, stride_leg=x['foot'][0] == side,
                                     seconds=round(len(p50) / FS, 2), cycle_s=round(n_cycle / S['fs'], 3), marker_fs=S['fs'],
                                     age=S['age'], adult=S['age'] >= 18, height_cm=S['height_cm'], speed=round(sp, 3),
                                     speed_abs=('slow' if sp < SPEED_ABS[0] else 'fast' if sp > SPEED_ABS[1] else 'comfortable') if lab == 'walking' else '',
                                     speed_rel=('slow' if sp < SPEED_REL[0] * med else 'fast' if sp > SPEED_REL[1] * med else 'comfortable') if lab == 'walking' else '',
                                     person_median_speed=round(med, 3), cadence=x['cadence'], loop_kink_ms=round(jump, 3),
                                     forward_matches_walking=fwd_ok, walk_tilt_deg=tilt, plausible=ok and fwd_ok,
                                     frame='markers (lateral); periodised stride',
                                     label_source='dataset task'))
            flag_by_walking(rows)
            st.save(person, arrays, rows)
            d = pd.DataFrame(rows)
            log(f"  Lencioni {person} (age {S['age']}, {S['fs']:.0f} Hz): {len(d) // 2} strides x 2 legs; walking lean "
                f"{d[d.task_label == 'walking'].walk_tilt_deg.median():+.1f} deg; loop kink median {d.loop_kink_ms.median():.2f} m/s; "
                f"{int((~d.plausible).sum())} flagged; {time.time() - t0:.0f} s")
        except Exception as e:
            import traceback
            log(f'  Lencioni {person}: FAILED {e!r}\n{traceback.format_exc()}')
    return st.index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', choices=['luo', 'lencioni', 'both'], default='both')
    ap.add_argument('--luo-people', default='', help='e.g. 1,2 (default all)')
    ap.add_argument('--lencioni-max', type=int, default=0)
    a = ap.parse_args()
    with S1.Tee(os.path.join(config.out_dir('stepC'), 'stage2_v4_log.txt')):
        print(f'\n===== {VERSION} | {S2.VERSION} | {V.VERSION} | {R.VERSION} | {config.VERSION} | {time.strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'args: {vars(a)}; output {config.V4_OUT}')
        if a.dataset in ('luo', 'both'):
            gen_luo([int(x) for x in a.luo_people.split(',') if x] or None)
        if a.dataset in ('lencioni', 'both'):
            gen_lencioni(a.lencioni_max or None)
        print('done')


if __name__ == '__main__':
    main()
