"""
Check before using Lencioni (single strides): does a window made of ONE repeated gait cycle have the same chip features
as a real window of continuous walking / stairs?   v1.0, 16 Nov 2026
Data: Camargo real shank IMU -> virtual implant (vimp, as the stage 1 validation), labels from the 'conditions' tables.
Per trial: cycles between consecutive forward-swing peaks of the shank gyroscope (pure label >= 90 %, 0.7-2.0 s).
For each cycle c:   real      = window of W s centred on c, cut from the continuous stream (chip 6 Hz causal filter first)
                    periodic  = cycle c repeated 7 times, same filter, window of W s in the middle
                    neighbour = the next real window that does not overlap (>= W s later, same label): the natural
                                variability between two real windows
Score per feature: median |periodic - real| / median |neighbour - real|  (1 = as different as two real neighbour windows).
Usage: python pipeline/check_periodise.py --subjects ab07,ab08,ab09 [--per-mode 6]
"""
import argparse, os, shutil, sys, time
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import stage01 as S1
import stage2 as S2
import stage3 as S3
import vimp as V

VERSION = 'check_periodise 1.0'
FEATS = ['mean_x', 'mean_y', 'mean_z', 'std_x', 'std_y', 'std_z', 'std_m', 'mean_m', 'ptp_m', 'max_m', 'jerk_m', 'tilt_sag',
         'tilt_cor', 'ac_m_05s', 'ac_m_10s', 'zcr_z', 'trend_x', 'trend_z', 'corr_xz', 'hf_ratio']
NAMES = ('standing', 'walking', 'stairs_up', 'stairs_down', 'ramp_up', 'ramp_down')


def feats(lib, a50, centre, W):
    s = int(round(centre - W * 50 / 2))
    if s < 0 or s + W * 50 > len(a50):
        return None
    w = a50[s:s + W * 50]
    return S3.T.features(lib, w[:, 0], w[:, 1], w[:, 2], 50.0)


def subject(subj, zp, lib, modes, per_mode, wins, log):
    import camargo_replay as C
    local = os.path.join(config.CACHE, 'camargo_periodise')
    S1._extract(zp, subj, local, modes, sensors=('imu', 'conditions'))
    m, _ = C.model_for(subj)
    dpos = m.site_pos[m.site('imu').id] - m.site_pos[m.site('shin_r').id]
    geom = dict(distance=float(dpos[1]), anterior=float(dpos[0]))
    fs = C.FS_DATA
    cols = lambda kind: [f'shank_{kind}_{a}' for a in 'XYZ']
    import glob
    trials = {md: sorted(glob.glob(os.path.join(local, subj, md, 'imu', '*.mat'))) for md in modes}
    z_up = None
    for p in trials.get('levelground', []) + trials.get('treadmill', []):
        imu = C.load_table(p); z_up = V.calibrate_up(imu[cols('Accel')].values, imu[cols('Gyro')].values, fs)
        if z_up is not None:
            break
    rows = []
    for md in modes:
        for p in trials[md][::max(1, len(trials[md]) // per_mode)][:per_mode]:
            try:
                imu = C.load_table(p)
                f, w = imu[cols('Accel')].values, imu[cols('Gyro')].values
                cp = p.replace(os.sep + 'imu' + os.sep, os.sep + 'conditions' + os.sep)
                lab, _ = C.conditions_labels(cp, imu['Header'].values) if os.path.exists(cp) else (None, '')
                if lab is None:
                    lab = np.full(len(f), 2 if md == 'stair' else 1)
                pimp, g = V.virtual_implant(f, w, fs, z_up=z_up, **geom)
                T = g['T']
                wy = V.lowpass(w, 6, fs) @ T[1]
                pk, _ = find_peaks(-wy, distance=int(0.6 * fs), height=0.5 * np.percentile(-wy, 99))
                a50 = S3.T.apply_lowpass(S2.resample(pimp, fs), 50, S3.LP).astype(np.float32)
                centres = (pk[:-1] + pk[1:]) / 2
                for k in range(len(pk) - 2):
                    a, b = pk[k], pk[k + 1]
                    dur = (b - a) / fs
                    if not 0.7 <= dur <= 2.0:
                        continue
                    v, c = np.unique(lab[a:b], return_counts=True)
                    if c.max() < 0.9 * (b - a) or v[np.argmax(c)] < 0:
                        continue
                    L = NAMES[int(v[np.argmax(c)])]
                    rep = S2.resample(np.tile(pimp[a:b], (7, 1)), fs)
                    rep = S3.T.apply_lowpass(rep, 50, S3.LP).astype(np.float32)
                    for W in wins:
                        fr = feats(lib, a50, (a + b) / 2 * 50 / fs, W)
                        far = np.flatnonzero(centres >= (a + b) / 2 + W * fs)      # next real window that does not overlap
                        if not len(far) or np.any(lab[int(centres[k]):int(centres[far[0]])] != lab[a]):
                            continue
                        fn = feats(lib, a50, centres[far[0]] * 50 / fs, W)
                        fp = feats(lib, rep, len(rep) / 2, W)
                        if fr is None or fn is None:
                            continue
                        rows.append(dict(subject=subj, mode=md, trial=os.path.basename(p), label=L, W=W, cycle_s=dur,
                                         **{f'real_{n}': x for n, x in zip(FEATS, fr)}, **{f'per_{n}': x for n, x in zip(FEATS, fp)},
                                         **{f'nb_{n}': x for n, x in zip(FEATS, fn)}))
            except Exception as e:
                log(f'  {subj} {os.path.basename(p)}: FAILED {e!r}')
    shutil.rmtree(os.path.join(local, subj), ignore_errors=True)
    log(f'  {subj}: {len(rows)} cycle windows ({geom["distance"]:.3f} m lever arm)')
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--subjects', default='ab07,ab08,ab09'); ap.add_argument('--per-mode', type=int, default=6)
    ap.add_argument('--windows', default='2,4')
    a = ap.parse_args()
    out = config.out_dir('stepC')
    with S1.Tee(os.path.join(out, 'check_periodise_log.txt')):
        print(f'\n===== {VERSION} | {S1.VERSION} | {time.strftime("%Y-%m-%d %H:%M:%S")} | args {vars(a)}')
        lib = S3.init_tinyml(config.TINYML)
        d = S1.find_dir(config.DATA_ROOT, 'Camargo*/Data', 'Camargo*')
        zips = {f[:4].lower(): os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith('.zip')}
        rows = []
        for s in a.subjects.split(','):
            t0 = time.time()
            rows += subject(s, zips[s], lib, ('treadmill', 'levelground', 'stair'), a.per_mode, [int(x) for x in a.windows.split(',')], print)
            print(f'    {time.time() - t0:.0f} s', flush=True)
        D = pd.DataFrame(rows)
        D.to_csv(os.path.join(out, 'check_periodise.csv'), index=False)
        print(f'\n{len(D)} windows; by label and window length:'); print(D.groupby(['label', 'W']).size().unstack().to_string())
        res = []
        for (L, W), g in D.groupby(['label', 'W']):
            if len(g) < 10:
                continue
            for n in FEATS:
                dp = np.median(np.abs(g[f'per_{n}'] - g[f'real_{n}'])); dn = np.median(np.abs(g[f'nb_{n}'] - g[f'real_{n}']))
                bias = np.median(g[f'per_{n}'] - g[f'real_{n}'])
                res.append(dict(label=L, W=W, feature=n, score=dp / (dn + 1e-9), bias=bias, real_median=np.median(g[f'real_{n}']),
                                spread_real_iqr=np.subtract(*np.percentile(g[f'real_{n}'], [75, 25]))))
        Rz = pd.DataFrame(res)
        Rz.to_csv(os.path.join(out, 'check_periodise_scores.csv'), index=False)
        print('\nscore = median |periodic - real| / median |neighbour - real|  (<= ~1.5: periodising changes a feature no more than'
              ' going to the next real window)')
        print(Rz.pivot_table(index='feature', columns=['label', 'W'], values='score').round(2).to_string())
        print('\nbias (median periodic - real) relative to the real IQR:')
        Rz['bias_rel'] = Rz.bias / (Rz.spread_real_iqr + 1e-9)
        print(Rz.pivot_table(index='feature', columns=['label', 'W'], values='bias_rel').round(2).to_string())


if __name__ == '__main__':
    main()
