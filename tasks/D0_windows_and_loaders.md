# Task D0: window-length loaders and a check of the C features

Branch: `agent/D0` (worktree `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_agent`). Read `AGENTS.md` first.
Report: `tasks/D0_report.md`. Do not train any model in this task.

## Why
Step D compares window lengths of 2, 3, 4 and 5 s (hop always 1 s, 50 Hz) and adds the new V4 datasets (Luo, Lencioni).
Today the window length is fixed to 2 s in two places (`pipeline/stage3.py`: `W, H = 100, 50`; and
`kneil_tinyml/tools/train_kneil_tinyml.py: load_windows`: `W, H = 2 * fs, fs`), and `stage3.load_stage2` only reads the
old stage 2 folder. You will write NEW files; do not edit those files.

## Part 1: independent check of the C features — `pipeline/features_ref.py` and `pipeline/test_features_window.py`
1. `pipeline/features_ref.py`: a pure numpy (float64) re-implementation of the C function `kneil_features()` in
   `kneil_tinyml/src/kneil_features.c` (20 features, same order as `KF_*` in `kneil_tinyml/include/kneil_tinyml.h`).
   Function: `features_ref(x, y, z, fs) -> np.ndarray (20,)`. Follow the C code line by line (the autocorrelation lags
   are `int(0.5*fs+0.5)` and `int(1.0*fs+0.5)` samples, `q = n // 4`, zero crossings of z - mean(z), etc.). Write the
   feature names as a list `NAMES` (lower case, e.g. `mean_x`, ..., `hf_ratio`).
2. `pipeline/test_features_window.py` (version line, log to `config.out_dir('stepD', 'D0')/test_features_window_log.txt`):
   - Build the C library and get the C features exactly like `stage3.py` does: `import stage3 as S3;
     lib = S3.init_tinyml(config.TINYML); S3.T.features(lib, x, y, z, 50.0)`.
   - Signals: (a) 3 Luo people from `<V4_OUT>/stage2/Luo/*.npz` (keys `<task>|R|implant`, N x 3, g, 50 Hz; take any 10
     trials per person), filtered with `S3.T.apply_lowpass(a, 50, 6.0)` first, like the chip; (b) 200 random windows
     (normal noise std 0.3 g plus 1 g on z); (c) a constant window (all samples (0, 0, 1)) — check nothing is NaN/inf.
   - For each window length n = 100, 150, 200, 250 samples (2, 3, 4, 5 s): at least 300 windows per length, cut with hop
     50 from the filtered streams. Compare C (float32) vs reference (float64) per feature.
   - PASS rule per feature: `max |C - ref| <= 1e-4 + 1e-3 * max(|ref|)` over all windows of that length. `zcr_z` must be
     identical. Print a table (feature x window length: max abs diff, PASS/FAIL) and save it as CSV next to the log.

## Part 2: one window builder for any length — `pipeline/stage3_v4.py`
Version line `stage3_v4 1.0`. Import `config, stage01 as S1, stage2 as S2, stage3 as S3, stage2_v4 as S2V`.
Reuse functions from `stage3.py` where they already accept what you need; copy and adapt the others into this file.
1. `stream_windows(lib, a50, codes=None, W=100, H=50)`: same as `stage3.stream_windows` but with `W`, `H` arguments
   (6 Hz causal filter on the whole stream first, windows from sample 0, label = majority if >= 60 % of the window,
   else -1).
2. `load_sim(root, lib, R, W)`: same as `stage3.load_sim` but windowing like `train_kneil_tinyml.load_windows` with
   window `W` samples, hop 50, `min_share=0.6`, `lowpass=6.0`, at 50 Hz. Write your own `load_windows_w(lib, dirs, fs,
   W, H, min_share, lowpass)` here (copy of `load_windows` with W, H as arguments). NOTE: unlike stream windows, the
   simulation windows below `min_share` are SKIPPED (not kept with -1) — keep that behaviour.
3. `load_caicedo(root, lib, R, W)`: as `stage3.load_caicedo` with the window length.
4. `load_stage2_old(root, lib, R, rng, W)`: as `stage3.load_stage2` (reads `KNEIL_results/virtual_implant/
   stage2_index_*.csv`, skips `_all.csv`, drops not-plausible rows, same `TRUSTED` sets, same `rot_y` tilt copy `Xr`
   with `rng.uniform(-5, 5)`) with the window length.
5. `load_stage2_v4(lib, R, rng, W)`: reads `<config.V4_OUT>/stage2_index_Luo.csv` and `stage2_index_Lencioni.csv`
   (stage 2 npz in `<config.V4_OUT>/stage2/<dataset>/`). Label names are in each npz key `label_names`
   (= `stage2_v4.LABELS`); map them to the chip classes with `stage3.TO_DEVICE`.
   - Luo: trusted chip labels `walking`, `stairs_up`, `stairs_down`, `standing`; all other window labels (slope_up,
     slope_down, calibration, mixed) are kept with y = -1 and their text in `lab`.
   - Lencioni: rows with `role == 'train'` -> trusted `walking`; rows with `role == 'test'` -> y = -1 but keep the text
     label (`stairs_up` / `stairs_down`) in `lab`; rows with `role == 'other'` -> skip them.
   - Group (person) id: `f'{dataset}:{person}'`.
6. Extra per-window metadata (new arrays, same length as X; empty string when not known):
   `rec` (the recording/task key from the index, e.g. `SelfPace`, `16_StrU`, `012_Walking`), `surface` (Luo),
   `speed_abs`, `speed_rel` (Lencioni), `adult` (Lencioni: 'True'/'False'), `role` (Lencioni). For the old stage 2 data
   put the index column `task` into `rec` (WearGait-PD has SelfPace / HurriedPace there; that is needed later).
7. `build(W_s, max_people=None)`: builds everything for window length `W_s` seconds (W = 50 * W_s samples, H = 50) and
   saves `config.out_dir('stepD', 'windows')/windows_W{W_s}s.npz` with the keys of the V3 cache (`X, Xr, y, src, ds, grp,
   task, lab`) plus `rec, surface, speed_abs, speed_rel, adult, role` and a scalar `W`. If the file exists, load it
   instead (resume). `max_people` limits people per dataset for tests. Log to `config.out_dir('stepD', 'D0')`.
8. CLI: `python pipeline/stage3_v4.py --win 2 [--max-people 2]`.

## Acceptance checks (write each one with numbers and PASS/FAIL in the report)
1. Part 1 table: every feature PASS for 2, 3, 4 and 5 s; no NaN/inf for the constant window.
2. `python pipeline/stage3_v4.py --win 2 --max-people 2` runs (with `$env:KNEIL_V4_OUT` set to your cache) and prints
   window counts per dataset.
3. **Regression against V3** (the most important check): full build with `--win 2` (real `KNEIL_V4_OUT` is fine here:
   it writes only `KNEIL_results/v4/stepD/windows/windows_W2s.npz`). Compare with the V3 cache
   `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results\virtual_implant\stage3\stage3_windows.npz` (read-only):
   for each of the 9 old `ds` values (WearGait-PD, CeTI, Camargo simulated, PAMAP2, MHEALTH, v1.6 synthetic, KneE-PAD,
   Marpino, Caicedo older adults) the window count must be identical and `max |X_new - X_v3|` must be <= 1e-5
   (rows in the same order within a dataset). Also `y` identical. Print a table. If a dataset differs, find out why
   (diagnostic) and report it; do not change the comparison to make it pass.
4. Window counts for `--win 3`, `--win 4` and `--win 5` (full builds) per dataset and per label, in one table. Counts
   must fall with the window length roughly as (seconds - W + 1).
5. Luo and Lencioni counts for `--win 2`: Luo should have about 24,800 walking, 3,900 stairs_up, 3,700 stairs_down
   windows (the step C check found these numbers); Lencioni train walking windows > 0 and test stairs windows kept
   with y = -1.

## Not part of this task
No 8-class mapping, no training, no cross-validation, no changes to the chip library. Those are the next tasks.
