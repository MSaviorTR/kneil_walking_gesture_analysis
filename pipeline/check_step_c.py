"""
Step C checks on the new stage 2 output (Luo, Lencioni): chip features (C code, 6 Hz causal filter, 2 s windows,
1 s hop) per recording, summarised by label, surface, speed class and leg.   v1.0, 16 Nov 2026
Usage: python pipeline/check_step_c.py      (reads <V4_OUT>/stage2_index_{Luo,Lencioni}.csv)
"""
import os, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import stage01 as S1
import stage3 as S3

VERSION = 'check_step_c 1.0'
SHOW = ['tilt_sag', 'mean_x', 'mean_z', 'std_m', 'ptp_m', 'jerk_m', 'ac_m_05s', 'ac_m_10s', 'zcr_z', 'trend_x', 'corr_xz']
FEATS = ['mean_x', 'mean_y', 'mean_z', 'std_x', 'std_y', 'std_z', 'std_m', 'mean_m', 'ptp_m', 'max_m', 'jerk_m', 'tilt_sag',
         'tilt_cor', 'ac_m_05s', 'ac_m_10s', 'zcr_z', 'trend_x', 'trend_z', 'corr_xz', 'hf_ratio']


def windows(lib, ds, I, label_names):
    rows = []
    for fn, g in I.groupby('file'):
        Z = np.load(os.path.join(config.V4_OUT, 'stage2', ds, fn))
        for r in g.itertuples():
            a = Z[f'{r.task}|{r.side}|implant']
            codes = Z[f'{r.task}|labels'][:len(a)]
            X, lab = S3.stream_windows(lib, a, codes)
            for x, c in zip(X, lab):
                d = r._asdict(); d.pop('Index', None)
                d['window_label'] = label_names[c] if c >= 0 else 'mixed'
                d.update(dict(zip(FEATS, x)))
                rows.append(d)
    return pd.DataFrame(rows)


def main():
    out = config.out_dir('stepC')
    with S1.Tee(os.path.join(out, 'check_step_c_log.txt')):
        print(f'\n===== {VERSION} | {time.strftime("%Y-%m-%d %H:%M:%S")} | V4_OUT {config.V4_OUT}')
        lib = S3.init_tinyml(config.TINYML)
        import stage2_v4 as S
        names = S.LABELS
        pd.set_option('display.width', 250)
        p = os.path.join(config.V4_OUT, 'stage2_index_Luo.csv')
        if os.path.exists(p):
            I = pd.read_csv(p)
            D = windows(lib, 'Luo', I[I.plausible], names)
            D.to_csv(os.path.join(out, 'check_luo_windows.csv'), index=False)
            print(f'\nLuo: {I.person.nunique()} people, {len(I)} recordings ({(~I.plausible).sum()} flagged), {len(D)} windows')
            print('windows by label:', D.window_label.value_counts().to_dict())
            print('\nLuo chip features by surface (windows labelled with the surface, standing parts excluded; medians):')
            M = D[D.window_label == D.task_label]
            print(M.groupby('surface')[SHOW].median().round(3).to_string())
            print('\nLuo walking lean per leg (deg, median over people):', I.groupby('side').leg_walking_tilt_deg.median().round(1).to_dict(),
                  '; range over people and legs', I.leg_walking_tilt_deg.min(), '-', I.leg_walking_tilt_deg.max())
        p = os.path.join(config.V4_OUT, 'stage2_index_Lencioni.csv')
        if os.path.exists(p):
            I = pd.read_csv(p)
            D = windows(lib, 'Lencioni', I[I.plausible], names)
            D.to_csv(os.path.join(out, 'check_lencioni_windows.csv'), index=False)
            print(f'\nLencioni: {I.person.nunique()} people, {len(I)} stride-legs ({(~I.plausible).sum()} flagged), {len(D)} windows '
                  '(periodised streams: several windows per stride)')
            S2 = I.drop_duplicates(['person', 'task', 'side'])
            print('\nlean (deg) and loop kink (m/s) by task and leg (stride leg = the leg that defines the cycle):')
            print(S2.groupby(['task_label', 'stride_leg'])[['walk_tilt_deg', 'loop_kink_ms']].median().round(2).to_string())
            W = D[(D.task_label == 'walking') & D.stride_leg]
            print('\nLencioni walking, stride leg: features by ABSOLUTE speed class (< 1.0 slow, > 1.4 m/s fast):')
            print(W.groupby('speed_abs')[['speed'] + SHOW].median().round(3).to_string())
            print('\nby RELATIVE speed class (< 0.85x, > 1.15x the person median):')
            print(W.groupby('speed_rel')[['speed'] + SHOW].median().round(3).to_string())
            print('\nstairs vs walking (stride leg):')
            print(D[D.stride_leg].groupby('task_label')[['speed'] + SHOW].median().round(3).to_string())


if __name__ == '__main__':
    main()
