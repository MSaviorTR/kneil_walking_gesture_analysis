"""
Diagnostic: Luo walking windows are ~3x more intense (std |a| 0.57 g) than Camargo (0.20-0.35 g) and Lencioni (0.19 g).
Is it the transfer (lever arm), the raw sensor, or faster walking?   v1.0, 16 Nov 2026
For FE trials of a few people (right and left shank): chip-filtered (6 Hz causal) |a| std, peak-to-peak and the stride
time, for lever arms 0 / 0.10 / 0.20 / 0.28 / 0.36 m, and with the gyroscope low-passed at 6 Hz instead of 15 Hz.
Usage: python pipeline/diag_luo_intensity.py --people 1,2,3
"""
import argparse, os, sys, time
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import stage01 as S1
import stage2 as S2
import stage2_v4 as S
import stage3 as S3
import v4_readers as R
import vimp as V

VERSION = 'diag_luo_intensity 1.0'


def intensity(p50):
    a = S3.T.apply_lowpass(p50, 50, S3.LP)
    m = np.linalg.norm(a, axis=1)
    n = len(m) // 100 * 100
    W = m[:n].reshape(-1, 100)
    W = W[W.std(1) > 0.05]                     # moving windows only
    return float(np.median(W.std(1))), float(np.median(W.max(1) - W.min(1)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--people', default='1,2,3'); a = ap.parse_args()
    people = [int(x) for x in a.people.split(',')]
    S3.init_tinyml(config.TINYML)
    rows = []
    with S1.Tee(os.path.join(config.out_dir('stepC'), 'diag_luo_intensity_log.txt')):
        print(f'\n===== {VERSION} | {time.strftime("%Y-%m-%d %H:%M:%S")} people {people}')
        with R.Luo(os.path.join(S.LUO_ROOT, 'data.mat')) as L:
            trials = {p: S.luo_trial_list(L, p) for p in people}
        for p in people:
            for side in 'RL':
                pos = f'shank{side}'
                cal = [S.luo_read_sensor(p, tr, pos)[:2] for tr, sf in trials[p] if sf == 'CALIB']
                fe = [S.luo_read_sensor(p, tr, pos)[:2] for tr, sf in trials[p] if sf == 'FE']
                T, _ = V.person_frame(cal, fe, R.LUO_FS)
                for k, (f, w) in enumerate(fe[:3]):
                    wy = V.lowpass(w, 6, R.LUO_FS) @ T[1]
                    pk, _ = find_peaks(-wy, distance=60, height=0.5 * np.percentile(-wy, 99))
                    row = dict(person=p, side=side, trial=k, stride_s=float(np.median(np.diff(pk))) / R.LUO_FS if len(pk) > 2 else np.nan,
                               gyr_swing_peak=float(np.percentile(-wy, 99)), raw_sensor_std=intensity(S2.resample(f @ T.T, R.LUO_FS))[0])
                    for d in (0.0, 0.10, 0.20, 0.28, 0.36):
                        p50 = S2.implant(f, w, R.LUO_FS, T, dict(distance=d, anterior=0.0, medial=0.0), side)
                        row[f'std_{d:.2f}'], row[f'ptp_{d:.2f}'] = intensity(p50)
                    pf, _ = V.virtual_implant(f, w, R.LUO_FS, z_up=T[2], T=T, side=side, fc=6.0, **S.LUO_GEOM)
                    row['std_0.36_gyro6Hz'] = intensity(S2.resample(pf, R.LUO_FS))[0]
                    rows.append(row)
        D = pd.DataFrame(rows)
        D.to_csv(os.path.join(config.out_dir('stepC'), 'diag_luo_intensity.csv'), index=False)
        pd.set_option('display.width', 250)
        print(D.groupby(['person', 'side']).median(numeric_only=True).drop(columns='trial').round(3).to_string())
        print('\nmedian all:'); print(D.median(numeric_only=True).drop('trial').round(3).to_string())
        print('\nreference (2 s windows, chip filter): Camargo vimp level ground 0.20 g (stride 1.30 s), treadmill 0.35 g (1.03 s); '
              'Lencioni markers 0.19 g')


if __name__ == '__main__':
    main()
