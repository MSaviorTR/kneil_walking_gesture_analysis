"""
Diagnostic: why is the Luo walking lean 22-27 deg (Camargo 12, Caicedo 17)?   v1.0, 16 Nov 2026
For flat-even (FE) trials of a few people and both legs, the mean implant lean while moving with:
  a  up from the CALIB standing (as stage2_v4), lever arm 0.36 m
  b  up from the still start (first ~1.5 s) of the same FE trial, lever arm 0.36 m
  c  as a, no transfer (lever arm 0)
  d  as a, lever arm 0.20 m
plus the angle between the CALIB 'up' and the trial-start 'up' (if the sensor moved on the leg or the posture differs).
Usage: python pipeline/diag_luo_lean.py --people 1,2,3,4,5
"""
import argparse, os, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import stage01 as S1
import stage2 as S2
import stage2_v4 as S
import v4_readers as R
import vimp as V

VERSION = 'diag_luo_lean 1.0'


def lean(f, w, T, dist):
    p = S2.implant(f, w, R.LUO_FS, T, dict(distance=dist, anterior=0.0, medial=0.0), 'R')
    return S2.walk_check(p)[0]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--people', default='1,2,3,4,5'); a = ap.parse_args()
    people = [int(x) for x in a.people.split(',')]
    rows = []
    with S1.Tee(os.path.join(config.out_dir('stepC'), 'diag_luo_lean_log.txt')):
        print(f'\n===== {VERSION} | {time.strftime("%Y-%m-%d %H:%M:%S")} people {people}')
        with R.Luo(os.path.join(S.LUO_ROOT, 'data.mat')) as L:
            trials = {p: S.luo_trial_list(L, p) for p in people}
        for p in people:
            for side in 'RL':
                pos = f'shank{side}'
                cal = [S.luo_read_sensor(p, tr, pos)[:2] for tr, sf in trials[p] if sf == 'CALIB']
                fe = [S.luo_read_sensor(p, tr, pos)[:2] for tr, sf in trials[p] if sf == 'FE']
                T, _ = V.person_frame(cal, fe, R.LUO_FS)
                z_cal = T[2]
                for k, (f, w) in enumerate(fe):
                    st = V.still_mask(V.lowpass(f, 15, R.LUO_FS), V.lowpass(w, 15, R.LUO_FS), R.LUO_FS)
                    first = np.flatnonzero(~st)
                    n0 = first[0] if len(first) else 0
                    z_tr = V.unit(f[:max(n0, 20)].mean(0)) if n0 >= 50 else None
                    row = dict(person=p, side=side, trial=k, still_start_s=n0 / R.LUO_FS,
                               lean_a_calib=lean(f, w, T, 0.36), lean_c_no_transfer=lean(f, w, T, 0.0), lean_d_020=lean(f, w, T, 0.20))
                    if z_tr is not None:
                        Tb = V.tibia_frame_pca(np.vstack([x[1] for x in fe]), R.LUO_FS, z_tr)
                        row.update(lean_b_trial_start=lean(f, w, Tb, 0.36),
                                   up_angle_calib_vs_start_deg=float(np.degrees(np.arccos(np.clip(z_cal @ z_tr, -1, 1)))))
                    # the raw sensor: lean of the long axis (sensor x) from vertical in the trial-start standing, for reference
                    rows.append(row)
        D = pd.DataFrame(rows)
        D.to_csv(os.path.join(config.out_dir('stepC'), 'diag_luo_lean.csv'), index=False)
        print(D.groupby(['person', 'side']).median(numeric_only=True).drop(columns='trial').round(1).to_string())
        print('\nall people and legs (median):'); print(D.median(numeric_only=True).drop('trial').round(1).to_string())


if __name__ == '__main__':
    main()
