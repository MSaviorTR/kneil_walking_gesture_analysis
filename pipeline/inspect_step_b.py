"""
Step B (PROMPT_V4.md): inspect Luo 2020 and Lencioni 2019 before writing generators.   v1.0, 16 Nov 2026
Luo:      per trial: surface, duration, samples, missing %, units check (|acc| at rest, gyro range), still fraction;
          sensor serial -> position map (CSV vs data.mat by PacketCounter and correlation) and CSV vs .mat difference.
Lencioni: per stride: task, foot, speed, duration, marker gaps of the tibia markers, vertical rise (stairs check),
          shank length; per subject: rate, age, strides by task, walking speed range.
Output: <V4_OUT>/stepB/ (log, luo_trials.csv, luo_sensor_map.csv, lencioni_strides.csv, lencioni_subjects.csv, png).
Usage: python pipeline/inspect_step_b.py [--luo-people 1,2] [--lencioni-max 5]   (no option = everything)
"""
import argparse, os, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import stage01 as S1
import v4_readers as R

VERSION = 'inspect_step_b 1.0'
G = 9.80665
LUO = os.path.join(config.DATA_ROOT, 'Luo et. al. 2020')
LEN = os.path.join(config.DATA_ROOT, 'Lencioni et. al. 2019')
TIBIA = ('FH', 'Shank', 'LatMal', 'LatCon')


def still_fraction(acc_g, fs, thr=0.03):
    m = np.linalg.norm(acc_g, axis=1)
    k = max(1, int(fs))
    sd = pd.Series(m).rolling(k, center=True, min_periods=k // 2).std().to_numpy()
    return float(np.nanmean(sd < thr))


def luo(people, out):
    rows, maps = [], []
    with R.Luo(os.path.join(LUO, 'data.mat')) as L:
        allp = L.people()
        print(f'Luo data.mat: {len(allp)} people: {allp[0]}..{allp[-1]}')
        for p in (people or allp):
            t0 = time.time()
            T = {s: L.table(p, s) for s in R.LUO_SENSORS}
            for s in ('shankR', 'shankL', 'thighR', 'thighL', 'wrist', 'trunk'):
                t = T[s]
                for i in range(len(t['Trial'])):
                    a, g = t['Acc'][i], t['Gyr'][i]
                    ag = a / G
                    rows.append(dict(person=p, sensor=s, trial=int(t['Trial'][i]), surface=t['Surface'][i],
                                     duration_s=t['TrialDuration'][i], samples=len(a), fs_from_duration=len(a) / t['TrialDuration'][i],
                                     missing_pct=t['Missingpct'][i], nan_pct=100 * float(np.isnan(a).any(1).mean()),
                                     acc_norm_median=float(np.nanmedian(np.linalg.norm(a, axis=1))),
                                     gyr_norm_p99=float(np.nanpercentile(np.linalg.norm(g, axis=1), 99)),
                                     still_frac=still_fraction(np.nan_to_num(ag), R.LUO_FS),
                                     mean_ax_g=float(np.nanmean(ag[:, 0])), mean_ay_g=float(np.nanmean(ag[:, 1])), mean_az_g=float(np.nanmean(ag[:, 2]))))
            # serial -> position: first flat-even trial
            tr = next(int(x) for x, sf in zip(T['shankR']['Trial'], T['shankR']['Surface']) if sf == 'FE')
            i = T['shankR']['Trial'].index(float(tr))
            csvs = R.luo_csv_files(LUO, p, tr)
            for serial, path in sorted(csvs.items()):
                C = R.luo_csv_read(path)
                best, scores = None, {}
                for s in R.LUO_SENSORS:
                    pc, a = T[s]['PacketCounter'][i], T[s]['Acc'][i]
                    common, ia, ib = np.intersect1d(pc, C['PacketCounter'], return_indices=True)
                    if len(common) < 100:
                        scores[s] = (np.nan, np.nan, 0); continue
                    x, y = a[ia], C['Acc'][ib]
                    ok = np.isfinite(x).all(1) & np.isfinite(y).all(1)
                    r = float(np.mean([np.corrcoef(x[ok, k], y[ok, k])[0, 1] for k in range(3)]))
                    rms = float(np.sqrt(((x[ok] - y[ok]) ** 2).sum(1).mean()))
                    scores[s] = (r, rms, len(common))
                best = max(scores, key=lambda s: -1 if np.isnan(scores[s][0]) else scores[s][0])
                hf = lambda v: float(np.mean(np.abs(np.diff(v, 2, axis=0))))
                pc, a = T[best]['PacketCounter'][i], T[best]['Acc'][i]
                common, ia, ib = np.intersect1d(pc, C['PacketCounter'], return_indices=True)
                x, y = np.nan_to_num(a[ia]), C['Acc'][ib]
                xl, yl = S1.V.lowpass(x, S1.LP, R.LUO_FS), S1.V.lowpass(y, S1.LP, R.LUO_FS)
                r6 = float(np.mean([np.corrcoef(xl[:, k], yl[:, k])[0, 1] for k in range(3)]))
                rms6 = float(np.sqrt(((xl - yl) ** 2).sum(1).mean()))
                lag = S1._lag(np.linalg.norm(xl, axis=1), np.linalg.norm(yl, axis=1), 50)
                maps.append(dict(person=p, trial=tr, serial=serial, position=best, r=scores[best][0], rms_ms2=scores[best][1],
                                 r_6hz=r6, rms_6hz_ms2=rms6, lag_samples_mat_vs_csv=lag,
                                 n_common=scores[best][2], second_r=sorted([v[0] for k, v in scores.items() if k != best and np.isfinite(v[0])])[-1],
                                 csv_rows=len(C['Acc']), mat_rows=len(a),
                                 hf_csv=hf(C['Acc'][ib]), hf_mat=hf(np.nan_to_num(a[ia]))))
            print(f'  person {p}: 6 tables, {len(csvs)} CSV sensors of trial {tr} mapped, {time.time() - t0:.0f} s', flush=True)
    D = pd.DataFrame(rows); M = pd.DataFrame(maps)
    D.to_csv(os.path.join(out, 'luo_trials.csv'), index=False); M.to_csv(os.path.join(out, 'luo_sensor_map.csv'), index=False)
    sh = D[D.sensor.isin(['shankR', 'shankL'])]
    print('\nLuo: trials per surface per person (shankR):')
    print(D[D.sensor == 'shankR'].groupby('surface').person.agg(['count', 'nunique']).rename(columns={'count': 'trials', 'nunique': 'people'}).to_string())
    print('\nLuo shank sensors, by surface (median [min-max]):')
    agg = sh.groupby('surface').agg(duration_s=('duration_s', 'median'), dur_min=('duration_s', 'min'), dur_max=('duration_s', 'max'),
                                    fs=('fs_from_duration', 'median'), missing_pct=('missing_pct', 'max'), nan_pct=('nan_pct', 'max'),
                                    acc_norm=('acc_norm_median', 'median'), gyr_p99=('gyr_norm_p99', 'median'), still=('still_frac', 'median'),
                                    ax_g=('mean_ax_g', 'median'), ay_g=('mean_ay_g', 'median'), az_g=('mean_az_g', 'median'))
    print(agg.round(3).to_string())
    print('\nunits: |acc| median over all trials {:.2f} (m/s^2 if ~9.8); gyro p99 median {:.2f} (rad/s if ~2-8, deg/s if ~100-500)'.format(
        sh.acc_norm_median.median(), sh.gyr_norm_p99.median()))
    print('\nLuo sensor serial -> position (from the first FE trial of each person):')
    if len(M):
        tab = M.groupby(['serial', 'position']).person.nunique().unstack(fill_value=0)
        print(tab.to_string())
        print(f"match r: median {M.r.median():.3f}, min {M.r.min():.3f}; next best r: median {M.second_r.median():.3f}")
        print(f"CSV vs .mat: RMS {M.rms_ms2.median():.3f} m/s^2 (median); 2nd-difference size CSV {M.hf_csv.median():.3f} vs .mat {M.hf_mat.median():.3f} "
              f"(smaller in .mat = .mat is smoothed); rows CSV {int(M.csv_rows.median())} vs .mat {int(M.mat_rows.median())}")
        print(f"after the 6 Hz low-pass on both: r median {M.r_6hz.median():.3f} (min {M.r_6hz.min():.3f}), RMS {M.rms_6hz_ms2.median():.3f} m/s^2, "
              f"lag .mat vs CSV {M.lag_samples_mat_vs_csv.median():.0f} samples (median; range {M.lag_samples_mat_vs_csv.min()}..{M.lag_samples_mat_vs_csv.max()})")
    return D, M


def luo_figure(out, person=1):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    with R.Luo(os.path.join(LUO, 'data.mat')) as L:
        T = {s: L.table(person, s) for s in ('shankR', 'thighR')}
    want = ['CALIB', 'FE', 'StrU', 'StrD', 'SlpU', 'CS']
    fig, ax = plt.subplots(len(want), 1, figsize=(12, 2.0 * len(want)), sharex=False)
    for k, sf in enumerate(want):
        i = T['shankR']['Surface'].index(sf)
        a = T['shankR']['Acc'][i] / G; g = T['thighR']['Gyr'][i]
        t = np.arange(len(a)) / R.LUO_FS
        ax[k].plot(t, np.linalg.norm(a, axis=1), lw=0.6, label='shankR |acc| (g)')
        ax[k].plot(t, a[:, 0], lw=0.6, label='shankR acc x (g)'); ax[k].plot(t, a[:, 1], lw=0.6, label='y'); ax[k].plot(t, a[:, 2], lw=0.6, label='z')
        ax[k].plot(t, g[:, 2] / 3, lw=0.6, color='k', alpha=0.5, label='thighR gyr z / 3 (rad/s)')
        ax[k].set_title(f'Luo person {person}, trial {int(T["shankR"]["Trial"][i])}: {sf} ({R.LUO_SURFACES[sf]})', loc='left', fontsize=9)
    ax[0].legend(fontsize=7, ncol=5); ax[-1].set_xlabel('s'); fig.tight_layout()
    p = os.path.join(out, 'luo_person1_examples.png'); fig.savefig(p, dpi=110); print(f'figure: {p}')


def lencioni(max_subjects, out):
    import openpyxl  # noqa: F401  (Demo_Anthro.xlsx)
    demo = pd.read_excel(os.path.join(LEN, 'Demo_Anthro.xlsx'), sheet_name=0)
    files = R.lencioni_files(LEN)[:max_subjects or None]
    rows, subj = [], []
    for fp in files:
        S = R.lencioni_load(fp)
        fs = S['fs']
        for st in S['strides']:
            side = 'Rx' if st['foot'] == 'RX' else 'Lx'
            m = st['markers']; n = len(m[side + 'FH'])
            gaps = {f'gap_{k}': float(np.mean(~np.isfinite(m[side + k]).all(1) | (np.abs(m[side + k]).sum(1) == 0))) for k in TIBIA}
            mal = m[side + 'LatMal']; psis = m['Psis']
            shank_len = float(np.nanmedian(np.linalg.norm(m[side + 'FH'] - m[side + 'LatMal'], axis=1)))
            rows.append(dict(subject=S['name'], age=S['age'], fs=fs, index=st['index'], task=st['task'], foot=st['foot'],
                             t0=st['t0'], frames=n, duration_s=n / fs, speed=st['speed'], cadence=st['cadence'],
                             stride_length=st['stride_length'], **gaps,
                             rise_malleolus_m=float(mal[-1, 1] - mal[0, 1]) if np.isfinite(mal[[0, -1], 1]).all() else np.nan,
                             rise_psis_m=float(psis[-1, 1] - psis[0, 1]) if np.isfinite(psis[[0, -1], 1]).all() else np.nan,
                             forward_psis_m=float(np.linalg.norm(psis[-1, [0, 2]] - psis[0, [0, 2]])) if np.isfinite(psis[[0, -1]]).all() else np.nan,
                             shank_len_m=shank_len))
        d = demo[demo.Code.astype(str).str.strip() == S['name'].strip()]
        subj.append(dict(subject=S['name'], age=S['age'], sex=S['sex'], height_cm=S['height_cm'], fs=fs,
                         height_xlsx=float(d['Body Height (cm)'].iloc[0]) if len(d) else np.nan, strides=len(S['strides'])))
    D = pd.DataFrame(rows); U = pd.DataFrame(subj)
    D.to_csv(os.path.join(out, 'lencioni_strides.csv'), index=False); U.to_csv(os.path.join(out, 'lencioni_subjects.csv'), index=False)
    print(f'\nLencioni: {len(U)} subjects, {len(D)} strides; rate: {U.fs.value_counts().to_dict()}; age {U.age.min()}-{U.age.max()} '
          f'(children < 18: {(U.age < 18).sum()})')
    print('marker names:', ', '.join(S['marker_names']))
    print('\nby task (median [p10-p90]):')
    q = lambda s: f'{s.median():.2f} [{s.quantile(.1):.2f}-{s.quantile(.9):.2f}]'
    for task, g in D.groupby('task'):
        print(f"  {task:12s} strides {len(g):4d}, people {g.subject.nunique():2d}; speed {q(g.speed)} m/s; duration {q(g.duration_s)} s; "
              f"malleolus rise {q(g.rise_malleolus_m)} m; pelvis rise {q(g.rise_psis_m)} m; pelvis forward {q(g.forward_psis_m)} m")
    print('\ntibia-marker gaps (fraction of frames missing, max over strides):',
          {k: round(float(D[f'gap_{k}'].max()), 3) for k in TIBIA}, '; strides with any gap:',
          int((D[[f'gap_{k}' for k in TIBIA]].sum(axis=1) > 0).sum()))
    print(f"shank length FH-LatMal / body height: median {np.nanmedian(D.shank_len_m.values / U.set_index('subject').loc[D.subject, 'height_cm'].values * 100):.3f}")
    print(f"height in .mat vs xlsx: max difference {np.nanmax(np.abs(U.height_cm - U.height_xlsx)):.1f} cm")
    w = D[D.task == 'Walking']
    print('\nWalking speed per subject: how many distinct speed levels? (min, median, max, range)')
    ws = w.groupby('subject').speed.agg(['count', 'min', 'median', 'max']); ws['range'] = ws['max'] - ws['min']
    print(ws.describe().round(2).to_string())
    print('\nWalking speed, all strides: quantiles', w.speed.quantile([0, .1, .25, .5, .75, .9, 1]).round(2).to_dict())
    print('Walking speed normalised to the subject median: quantiles',
          (w.speed / w.groupby('subject').speed.transform('median')).quantile([0, .1, .25, .5, .75, .9, 1]).round(2).to_dict())
    print('consecutive strides in one pass? walking strides with the same subject+foot and t0 within 3 s of another:',
          int(w.groupby(['subject', 'foot']).t0.apply(lambda s: (np.diff(np.sort(s.values)) < 3).sum()).sum()), 'pairs')
    return D, U


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--luo-people', default='')
    ap.add_argument('--lencioni-max', type=int, default=0)
    ap.add_argument('--skip-luo', action='store_true'); ap.add_argument('--skip-lencioni', action='store_true')
    a = ap.parse_args()
    out = config.out_dir('stepB')
    with S1.Tee(os.path.join(out, 'step_b_log.txt')):
        print(f'\n===== {VERSION} | {R.VERSION} | {config.VERSION} | {time.strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'args: {vars(a)}')
        if not a.skip_luo:
            luo([int(x) for x in a.luo_people.split(',') if x], out)
            luo_figure(out)
        if not a.skip_lencioni:
            lencioni(a.lencioni_max, out)
        print('done')


if __name__ == '__main__':
    main()
