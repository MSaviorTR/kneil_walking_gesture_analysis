# Task D2: seed noise, weight of the new data, and the stairs evidence rule

Branch: `agent/D2`, new from `main` (your D1 work is merged). Read `AGENTS.md` first. Report: `tasks/D2_report.md`.

## Review of D1 (manager)
Accepted and merged. Check 1: the inputs (folds, rows, weights, labels) are identical to V3 and the remaining gap is
forest-to-forest variation — accepted. Your open question 2 (two fold maps): keep the 2 s-file map for all 8-class
work. The manager compared walking recall V3 vs your 9-class rebuild: KneE-PAD 74.4 -> 61.9, Marpino 74.2 -> 86.7,
WearGait-PD 87.0 -> 84.4, the big datasets within 1-3 points. **Small datasets move by +-12 points between forests**,
so from now on every comparison is repeated with 3 seeds and reported as mean (sd).

## Part A: stream id in the window files (`pipeline/stage3_v4.py` -> version 1.1)
The stairs rule needs the time order of the windows within one recording. Add an int array `stream` to every window
file: one id per call of `R.add` / per recording **and leg** (Luo R and L of the same trial are different streams),
increasing in the order the rows are added; rows of one stream are contiguous and in time order (check both).
Rebuild `windows_W{2,3,4,5}s.npz` into `config.out_dir('stepD', 'windows_v11')` (do NOT overwrite the D0 files) and
verify for every file: `X`, `y`, `ds`, `grp`, `lab` identical to the D0 file (`np.array_equal`), and the number of
streams per dataset (report it).

## Part B: seeds and weight (`pipeline/cv_v4.py` -> version 1.1)
1. `--seeds 0 1 2`: set `random_state=seed` on the forest (fit otherwise unchanged). Seed 0 must give exactly the D1
   predictions (check it on one run).
2. New variant `V4half`: like `V4data` but the weights of the Luo and Lencioni rows multiplied by 0.5.
3. Save the class probabilities (`predict_proba`, float16 is fine, columns = the 8 classes in order) next to the
   predictions: `pred_{variant}_W{W}s_8cls_seed{s}.npz` with keys `pred, proba, fold`.
4. Runs: 8 classes x variants `V3recipe V4data V4half` x W 2 3 4 5 x seeds 0 1 2 (36 runs). Read the v1.1 window files.
5. Tables as in D1 (a-g) but as **mean (sd) over the 3 seeds**. Write `D2_summary.md` and `D2_results.csv` under
   `config.out_dir('stepD', 'D2')`.

## Part C: stairs evidence rule (`pipeline/stairs_rule.py`, version 1.0)
Post-processing of the window predictions, **causal** (the chip can only look back):
for each window t of a stream (time order): if the raw prediction is stairs_up or stairs_down, keep it only if
(1) `proba[t, predicted class] >= theta` and (2) at least `k` of the last `n` windows (t-n+1 .. t, same stream,
raw predictions) are stairs_up or stairs_down; otherwise replace it by `walking`. Other classes are not touched.
- Grid: theta in {0.30, 0.40, 0.50, 0.60, 0.70}; (k, n) in {(1,1), (2,2), (2,3), (3,3), (3,4), (4,5)}.
- **Tuning inside the cross-validation**: for test fold f, choose (theta, k, n) on the windows of the other 4 folds
  (their out-of-fold predictions) by the objective `mean of stairs F1 over {Luo, PAMAP2, simulated}`, where stairs F1 =
  F1 of the merged class "stairs" (up or down) vs everything else, over windows with y >= 0. Apply the chosen
  parameters to fold f. Do this per run (variant, W, seed).
- Report per variant and W (mean (sd) over seeds), before -> after the rule:
  stairs_up and stairs_down recall and precision on Luo, PAMAP2, simulated; walking recall on every real dataset;
  **walking called stairs** by WearGait-PD `rec`, Lencioni `speed_abs`, Luo `surface`; Luo slopes predicted as stairs;
  Lencioni test stairs recognised as stairs; and the parameters chosen per fold.

## Acceptance checks
1. Part A: all equality checks PASS for the four files; streams contiguous and in time order.
2. Part B: seed 0 reproduces the D1 predictions exactly on one run (say which); 36 runs done; tables with mean (sd).
3. Part C: smoke test on one run first; then all runs. The rule never changes non-stairs predictions (count them: 0).
4. In the report, a short table for the owner's question "fast walking is called stairs": walking-called-stairs for
   WearGait-PD HurriedPace, Lencioni fast, Luo FE and GR — for V3recipe 2 s (today's recipe), and for every variant x W
   before and after the rule; plus Luo stairs_up / stairs_down recall after the rule next to it.

## Not part of this task
No transition events (that is D3), no export, no changes to `stage3.py`, `kneil_tinyml/`, or the D0/D1 output files.
