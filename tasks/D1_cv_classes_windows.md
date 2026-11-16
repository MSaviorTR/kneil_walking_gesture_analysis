# Task D1: cross-validation of 8 classes x window length x data variant

Branch: `agent/D1`, new from `main` (main now contains your D0 work, merged). Read `AGENTS.md` first.
Report: `tasks/D1_report.md`. Nothing is exported to the chip in this task.

## Review of D0 (manager)
Accepted and merged. The tilt features differ from the V3 cache by <= 2 float32 ULP (libm `atan2f`), the other 18
features are bit-identical: from now on regressions on features use a ULP/relative rule. Keep `Xr` for V4 rows (your
assumption 2 is fine). Good work: the diagnostics were exactly what was needed.

## Inputs
`KNEIL_results\v4\stepD\windows\windows_W{2,3,4,5}s.npz` (from D0; load with `allow_pickle=True`).

## What to build: `pipeline/cv_v4.py` (version line `cv_v4 1.0`, log + results under `config.out_dir('stepD', 'D1')`)
1. **8 classes.** `CLASSES8 = ['walking', 'stairs_up', 'stairs_down', 'still', 'lying', 'sit_to_stand', 'stand_to_sit',
   'bed_transfer']`. Map the 9-class `y`: 0->0, 1->1, 2->2, 3 (sitting)->3, 4 (standing)->3, 5->4, 6->5, 7->6, 8->7;
   -1 stays -1. Keep the 9-class `y` too (needed for check 1).
2. **Folds by person, the same for every window length.** Use `stage3.assign_folds` on the **2 s** file to get the
   group -> fold map (`gf`), then apply that map to the 3/4/5 s files (a group missing at 5 s is simply absent).
   Luo and Lencioni groups get folds like every other dataset (they are `src == 'real'` in the D0 files — check this
   and report it).
3. **Two data variants** (write your own `training_set_v4(A, mask, variant, y)`; copy the logic of
   `stage3.training_set` for variant `'V3'`: sim weight 1, Caicedo weight `0.3 * n_sim_walking / n_caicedo`, real
   datasets weighted by `n_sim * sqrt(n_d) / sum_d sqrt(n_d) / n_d`, no tilt copies):
   - `V3recipe`: exactly the V3 training data: sim + Caicedo + the old real datasets. **Luo and Lencioni are NOT in
     training** (but they are tested).
   - `V4data`: the same + Luo + Lencioni (role train only, i.e. rows with y >= 0) as two more real datasets in the same
     sqrt weighting.
4. **Model**: `stage3.make_model('forest 20x d10')` (fixed random_state inside). For each (variant, W, classes) run
   5 folds, predict every window of the test fold (also y = -1 windows: they are needed for the speed and slope
   analysis), save `pred_{variant}_W{W}s_{n}cls.npz` (prediction per row + the fold) after each run; skip runs that
   exist (resume). Runs: classes 8 for both variants and all four W (8 runs), plus check 1 below.
5. **Report tables** (script writes `D1_results.csv` in long format and `D1_summary.md` with the tables):
   a. Per run: macro-F1 on the simulation (`src == 'sim'`), recall per class on the simulation.
   b. Per run and real dataset: recall of every trusted class (y >= 0) and macro-F1 over the classes present;
      WearGait-PD walking also as **median per person** separately for controls and Parkinson (group column of
      `KNEIL_results\virtual_implant\stage2_index_WearGait-PD.csv`, as `stage3._wg_groups` does).
   c. Stairs on real people: Luo and PAMAP2 stairs_up / stairs_down recall **and precision** (precision over all
      windows of that dataset predicted as that class).
   d. **Walking called stairs, by speed** (fraction of true-walking windows predicted stairs_up or stairs_down):
      WearGait-PD by `rec` (SelfPace vs HurriedPace), Lencioni by `speed_abs` and `speed_rel` (train rows), Luo by
      `surface` (FE, CS, GR, BnkL, BnkR) — and what Luo **slopes** (y = -1, `lab` slope_up / slope_down) are predicted as
      (fraction per class).
   e. Lencioni test stairs (y = -1, `lab` stairs_up / stairs_down, `role == 'test'`): fraction predicted walking /
      stairs_up / stairs_down.
   f. `still` recall per dataset (sitting + standing together) and lying recall.
   g. Model size: number of nodes of the fold-0 forest (sum of `tree_.node_count`).
6. CLI: `python pipeline/cv_v4.py --win 2 3 4 5 --variants V3recipe V4data [--max-rows N]`; `--max-rows` subsamples
   rows (stratified by dataset, seed 0) for a smoke test.

## Acceptance checks (numbers + PASS/FAIL in the report)
1. **Regression against V3**: run `V3recipe`, W = 2 s, **9 classes**, and compare the predictions on the 274,952 old
   rows with the V3 cross-validation `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results\virtual_implant\stage3\
   stage3_cv_predictions.npz` key `'V3'` (same row order as the V3 window cache; D0 showed the old rows are in the
   same order in `windows_W2s.npz`). PASS if >= 99.5 % of the predictions are identical (a few may flip from the tilt
   ULP differences) and the fold of every row equals V3's fold (`stage3.assign_folds` on the V3 cache). If it fails,
   find out why before running anything else.
2. Smoke test with `--max-rows 30000` runs end to end and writes all tables.
3. The 8 full runs finish; `D1_summary.md` contains tables a-g for every run. Put the main tables in the report
   (walking recall per dataset, stairs recall/precision, walking-called-stairs by speed, still recall, nodes).
4. Sanity: the 8-class `V3recipe` W = 2 s walking recall per dataset must be close to the 9-class one (merging sitting
   and standing should not change walking much); give both.

## Not part of this task
No stairs evidence rule, no transition events, no export, no new features. Do not change `stage3.py` or the D0 files
(if you find a bug in D0 code, report it; fix it only in a separate commit with a clear message).
