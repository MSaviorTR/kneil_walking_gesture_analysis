"""
Step A smoke test (PROMPT_V4.md): the pipeline runs on the local PC.   v1.0, 16 Nov 2026
  part 1  rebuild the chip feature library (C, via gcc) and check the C vs Python 6 Hz low-pass; run the host test
  part 2  Camargo validation for one subject (default ab07): virtual implant from the real shank IMU vs the implant
          signal of the MuJoCo replay of the measured joint angles. Expected: calibrated |a| r about 0.93-0.98.
          The result is compared with the Colab run in KNEIL_results/virtual_implant/stage1a_camargo_trials.csv.
Output: <V4_OUT>/stepA/ (log, trial CSV). Earlier results are only read.

Usage: python pipeline/run_step_a.py [--part 1|2|all] [--subject ab07] [--per-mode 4]
"""
import argparse, os, platform, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import stage01 as S1

VERSION = 'run_step_a 1.0'


def part1():
    import stage3 as S3
    lib_path = os.path.join(config.TINYML, 'tools', 'libkneil_features' + ('.dll' if os.name == 'nt' else '.so'))
    if os.path.exists(lib_path):
        os.remove(lib_path); print(f'removed the old build {lib_path}')
    t0 = time.time()
    S3.init_tinyml(config.TINYML)                        # builds with gcc, asserts the low-pass parity < 1e-4 g
    print(f'built {lib_path} in {time.time() - t0:.1f} s')
    T = S3.T
    import numpy as np
    rng = np.random.default_rng(1)
    a = rng.normal(0, 0.3, (100, 3)).astype(np.float32); a[:, 2] += 1.0
    f = T.features(S3.T.c_features_lib(), a[:, 0], a[:, 1], a[:, 2], 50.0)
    print(f'feature call on one random 2 s window: {len(f)} features, all finite: {bool(np.isfinite(f).all())}')
    # the library in the repo has no model: test a scratch copy with the deployed V3 model files added
    import shutil
    v3 = os.path.join(config.RESULTS, 'tinyml_final_v3_lp6')
    tmp = os.path.join(config.CACHE, 'tinyml_v3_hosttest')
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(config.TINYML, tmp, ignore=shutil.ignore_patterns('*.dll', '*.so', '*.exe', '__pycache__'))
    for f, sub in (('kneil_model_forest.h', 'include'), ('kneil_model_tree.h', 'include'), ('kneil_model_info.h', 'include'),
                   ('kneil_test_vectors.h', 'tests')):
        shutil.copyfile(os.path.join(v3, f), os.path.join(tmp, sub, f))
    print(f'host test on a copy of the library with the V3 model from {v3}')
    test = os.path.join(tmp, 'tests', 'run_host_test.py')
    r = subprocess.run([sys.executable, test], capture_output=True, text=True, cwd=tmp)
    print(r.stdout.strip()); print(r.stderr.strip()) if r.stderr.strip() else None
    print(f'host test exit code {r.returncode}')
    return r.returncode == 0


def part2(subject, per_mode):
    import pandas as pd
    out = config.out_dir('stepA')
    csv = os.path.join(out, 'stage1a_camargo_trials.csv')
    if os.path.exists(csv):
        old = pd.read_csv(csv)
        if (old.subject == subject).any():
            print(f'{subject} is already in {csv}: shown below (delete the file to redo)')
    t0 = time.time()
    df = S1.stage1a(config.DATA_ROOT, out, [subject], per_mode=per_mode)
    print(f'stage1a finished in {time.time() - t0:.0f} s')
    d = df[df.subject == subject]
    if not len(d):
        print('NO TRIALS: see the messages above'); return False
    cols = ['mode', 'trial', 'variant', 'r_mag', 'r_x', 'r_z', 'rms_g', 'implant_tilt_deg', 'plausible']
    print('\nper trial (all variants):'); print(d[cols].round(3).to_string(index=False))
    s = d.groupby('variant')[['r_mag', 'r_x', 'r_z', 'rms_g']].median().round(3); s['trials'] = d.groupby('variant').size()
    print('\nmedian by variant:'); print(s.to_string())
    cal = d[d.variant == 'calibrated']
    print(f"\ncalibrated |a| r per trial: min {cal.r_mag.min():.3f}, median {cal.r_mag.median():.3f}, max {cal.r_mag.max():.3f} "
          f"(expected about 0.93-0.98)")
    ref = os.path.join(config.RESULTS, 'virtual_implant', 'stage1a_camargo_trials.csv')
    if os.path.exists(ref):
        R = pd.read_csv(ref); R = R[R.subject == subject]
        if len(R):
            m = d.merge(R, on=['trial', 'variant'], suffixes=('', '_colab'))
            print(f'\nlocal vs Colab run ({ref}): {len(m)} matching trial/variant rows')
            if len(m):
                for c in ('r_mag', 'r_x', 'r_z', 'rms_g'):
                    print(f'  {c:6s} max |local - Colab| = {(m[c] - m[c + "_colab"]).abs().max():.2e}')
        else:
            print(f'\n{subject} is not in the Colab results file: no comparison')
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--part', default='all', choices=['1', '2', 'all'])
    ap.add_argument('--subject', default='ab07')
    ap.add_argument('--per-mode', type=int, default=4)
    a = ap.parse_args()
    log = os.path.join(config.out_dir('stepA'), 'step_a_log.txt')
    with S1.Tee(log):
        print(f'\n===== {VERSION} | {S1.VERSION} | {config.VERSION} | {time.strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'Python {platform.python_version()} ({sys.executable}), {platform.platform()}')
        config.show()
        ok = True
        if a.part in ('1', 'all'):
            print('\n--- part 1: chip feature library ---'); ok &= part1()
        if a.part in ('2', 'all'):
            print(f'\n--- part 2: Camargo validation, {a.subject} ---'); ok &= part2(a.subject, a.per_mode)
        print(f'\nstep A smoke test: {"OK" if ok else "PROBLEM"}   (log: {log})')


if __name__ == '__main__':
    main()
