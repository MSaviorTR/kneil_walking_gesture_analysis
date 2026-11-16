"""
Diagnostic: how does the implant signal from a shank IMU depend on the assumed lever arm, where the truth is known?
Camargo: real shank IMU -> vimp with lever arm d vs the implant signal of the MuJoCo replay of the measured joint angles
(the stage 1 validation, true d from the model geometry).   v1.0, 16 Nov 2026
Reports per d: |a| correlation with the replay, RMS, and the chip-filtered |a| std of the vimp signal and of the replay.
Question for Luo: is the true lever arm where the vimp intensity equals the replay intensity, or near its minimum?
Usage: python pipeline/diag_lever_arm_camargo.py --subjects ab07,ab08 --per-mode 3
"""
import argparse, os, shutil, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import stage01 as S1
import stage2 as S2
import stage3 as S3
import vimp as V

VERSION = 'diag_lever_arm_camargo 1.0'
DS = np.round(np.arange(0.0, 0.49, 0.04), 2)


def chip_std(p, fs):
    a = S3.T.apply_lowpass(S2.resample(p, fs), 50, S3.LP)
    m = np.linalg.norm(a, axis=1); n = len(m) // 100 * 100
    W = m[:n].reshape(-1, 100); W = W[W.std(1) > 0.05]
    return float(np.median(W.std(1))) if len(W) else np.nan


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--subjects', default='ab07,ab08'); ap.add_argument('--per-mode', type=int, default=3)
    a = ap.parse_args()
    import camargo_replay as C
    S3.init_tinyml(config.TINYML)
    rows = []
    with S1.Tee(os.path.join(config.out_dir('stepC'), 'diag_lever_arm_camargo_log.txt')):
        print(f'\n===== {VERSION} | {time.strftime("%Y-%m-%d %H:%M:%S")} | {vars(a)}')
        d = S1.find_dir(config.DATA_ROOT, 'Camargo*/Data', 'Camargo*')
        zips = {f[:4].lower(): os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith('.zip')}
        local = os.path.join(config.CACHE, 'camargo_lever')
        for subj in a.subjects.split(','):
            S1._extract(zips[subj], subj, local, ('treadmill', 'levelground', 'stair'))
            m, info = C.model_for(subj); fs = C.FS_DATA
            dpos = m.site_pos[m.site('imu').id] - m.site_pos[m.site('shin_r').id]
            true_d, ant = float(dpos[1]), float(dpos[0])
            cols = lambda kind: [f'shank_{kind}_{x}' for x in 'XYZ']
            z_up = None
            for _, _, pimu in C.find_trials(local, subj, 'levelground') + C.find_trials(local, subj, 'treadmill'):
                imu = C.load_table(pimu); z_up = V.calibrate_up(imu[cols('Accel')].values, imu[cols('Gyro')].values, fs)
                if z_up is not None:
                    break
            for mode in ('treadmill', 'levelground', 'stair'):
                tr = C.find_trials(local, subj, mode)
                for name, pik, pimu in tr[::max(1, len(tr) // a.per_mode)][:a.per_mode]:
                    ik, imu = C.load_table(pik), C.load_table(pimu)
                    t, Q = C.ik_to_Q(m, info, ik)
                    o = C.replay(m, Q, fs, sensors=('acc_imu', 'gyr_shin_r'))
                    n = min(len(t), len(imu))
                    f, w = imu[cols('Accel')].values[:n], imu[cols('Gyro')].values[:n]
                    tgt, ws = o['acc_imu'][:n], o['gyr_shin_r'][:n]
                    L = S1._lag(np.linalg.norm(V.lowpass(w, 6, fs), axis=1), np.linalg.norm(V.lowpass(ws, 6, fs), axis=1), int(fs))
                    sr, ss = (slice(L, None), slice(None, n - L)) if L >= 0 else (slice(None, n + L), slice(-L, None))
                    f, w, tgt = f[sr], w[sr], tgt[ss]
                    rep_std = chip_std(tgt, fs)
                    for dd in DS:
                        p, _ = V.virtual_implant(f, w, fs, z_up=z_up, distance=float(dd), anterior=ant)
                        mt = S1.metrics(p, tgt, fs)
                        rows.append(dict(subject=subj, mode=mode, trial=name, true_d=round(true_d, 3), d=dd, r_mag=mt['r_mag'],
                                         rms_g=mt['rms_g'], vimp_std=chip_std(p, fs), replay_std=rep_std))
                    print(f'  {subj} {name}: done', flush=True)
            shutil.rmtree(os.path.join(local, subj), ignore_errors=True)
        D = pd.DataFrame(rows); D.to_csv(os.path.join(config.out_dir('stepC'), 'diag_lever_arm_camargo.csv'), index=False)
        pd.set_option('display.width', 250)
        print('\nmedian over trials, by mode and assumed lever arm d (true d per subject: '
              f'{D.groupby("subject").true_d.first().to_dict()}):')
        print(D.groupby(['mode', 'd'])[['r_mag', 'rms_g', 'vimp_std', 'replay_std']].median().round(3).unstack('mode').to_string())
        g = D.groupby(['subject', 'mode', 'trial'])
        best = g.apply(lambda x: pd.Series(dict(true_d=x.true_d.iloc[0], d_best_r=x.loc[x.r_mag.idxmax(), 'd'], d_min_rms=x.loc[x.rms_g.idxmin(), 'd'],
                                                d_min_std=x.loc[x.vimp_std.idxmin(), 'd'],
                                                d_std_match=x.loc[(x.vimp_std - x.replay_std).abs().idxmin(), 'd'])), include_groups=False)
        print('\nper trial: d with the best r, the lowest RMS, the lowest vimp intensity, and vimp intensity = replay intensity:')
        print(best.groupby('mode').median().round(3).to_string())


if __name__ == '__main__':
    main()
