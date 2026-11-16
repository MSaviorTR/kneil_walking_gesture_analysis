# Task D3: transitions as events, and the stairs rule with a precision-weighted objective

Branch: `agent/D3`, new from `main` (your D2 work is merged). Read `AGENTS.md` first. Report: `tasks/D3_report.md`.
Use the D2 predictions (`stepD\D2\pred_{variant}_W{W}s_8cls_seed{s}.npz`, keys `pred, proba, fold`) and the v1.1 window
files (`stepD\windows_v11`, with `stream`). No new model training is needed.

## Review of D2 (manager)
Accepted and merged; the manager recomputed Luo FE / GR, Lencioni fast and Luo stairs_up for V4data 5 s seed 0 from your
files and got the same numbers. Your point 1 is right: with plain F1 the evidence requirement cannot win. Part B below
changes the objective. V4half vs V4data stays open for the owner.

## Part A: sit-to-stand and stand-to-sit as events (`pipeline/transition_events.py`, version 1.0)
On the chip, a transition is counted once per event, not per window. Detect events from the window predictions of each
stream (time order, hop 1 s):
- **Rule R0**: an event = a maximal run of windows predicted `sit_to_stand` or `stand_to_sit` (merge runs separated by
  one other window); direction = the majority class of the run; event time = centre of the run (window t covers
  seconds t .. t + W).
- **Rule R1**: R0, but keep the event only if a window predicted `still` lies within 3 windows before OR after the run.
**Ground truth** (from the 50 Hz per-sample labels of the source, not from the windows):
- Simulation (`v1.6 synthetic`, `Camargo simulated`): the per-sample `activity` column of the source CSVs (D0's
  `load_windows_w` can return the file per window): every run of `sit_to_stand` / `stand_to_sit` samples = 1 true event.
- CeTI s01 recordings (`rec` starts with `s01`, five sit-to-stands): stage 2 npz labels
  (`KNEIL_results\virtual_implant\stage2\CeTI\*.npz`, key `<rec>|labels`, codes in `label_names`): a change from a
  `sitting` run to a `standing` run (with `transition` samples in between allowed) = 1 sit-to-stand, the reverse =
  1 stand-to-sit. Report how many of each you find per recording (expected about 5 + 5).
- WearGait-PD `TUG` (approximate: its labels come from the HAR labeller, macro-F1 0.79): same sitting <-> non-sitting
  change rule on the stage 2 labels; report the counts per recording and call this truth **approximate**.
**Metrics** per variant x W (mean (sd) over the 3 seeds), per data source and rule:
- event recall = true events matched by a detected event of the same direction with |t_det - t_true| <= W/2 + 2 s
  (each detected event matches at most one true event); direction errors (matched in time, wrong direction) separately;
- precision of the detected events inside these recordings;
- **false events per hour** on recordings without transitions: Luo (all trials except CALIB), WearGait-PD `SelfPace`
  and `HurriedPace`, `Camargo simulated` files without any transition sample.
Also give the window-level recall of sit_to_stand / stand_to_sit on the simulation next to it (from D2) so both views
are in one table.

## Part B: stairs rule v2 (`pipeline/stairs_rule.py` -> version 1.1; keep v1.0 results untouched, new output folder D3)
Same causal rule and same in-CV tuning, with two changes:
1. Objective: mean over {Luo, PAMAP2, simulated} of the **F0.5** of the merged class stairs (precision counts twice as
   much as recall). Keep the F1 objective available as an option for comparison.
2. Grid: theta in {0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80}; (k, n) as in D2.
Report the same tables as D2 section 4.4 (walking called stairs for WearGait-PD HurriedPace, Lencioni fast, Luo FE and
GR; Luo stairs_up / stairs_down recall and precision; PAMAP2 stairs recall and precision) for: no rule / v1 (F1) /
v2 (F0.5), every variant x W, mean (sd) over seeds; and how often (k, n) > (1, 1) is chosen now.

## Acceptance checks
1. Part A on one run first (V3recipe 2 s seed 0): print the true event counts per source (simulation, CeTI s01, TUG)
   and a few example streams with true and detected event times; then all runs.
2. Part A table: event recall, direction errors, precision, false events per hour, for R0 and R1, all variants x W.
3. Part B: all runs; the rule still never changes a non-stairs window (count = 0); the table above.
4. Report a one-screen summary for the owner: for each window length, the best variant by (a) stairs F0.5 on Luo after
   the v2 rule, (b) walking-called-stairs on Luo FE / Lencioni fast, (c) sit-to-stand event recall + false events per
   hour, (d) WearGait-PD and KneE-PAD walking recall, (e) model size. Numbers only; no recommendation needed.

## Not part of this task
No export, no posture tracking on the chip, no changes to earlier output files, `stage3.py` or `kneil_tinyml/`.
