# D3 report: transitions as events, and the stairs rule with an F0.5 objective

## 1. Status

Done — both parts finished, all acceptance checks pass. With the F0.5 objective the evidence requirement finally pays
off: `(k, n) > (1, 1)` is chosen in 72 of 180 folds (F1: 18 of 180), and on Luo at 2 s the merged stairs F0.5 goes
62.0 (no rule) -> 64.5 (F1 objective) -> 66.9 (F0.5 objective), while walking-called-stairs falls from 27.5 % to 16.4 %
(Luo GR). The cost is stairs recall (Luo stairs_up 50.4 -> 40.1 %).

## 2. Files

- `pipeline/transition_events.py` (new, **1.0**): events from window predictions (R0/R1), per-sample ground truth for
  the simulation, CeTI s01 and TUG, matching and metrics.
- `pipeline/stairs_rule.py` -> **1.1**: F0.5 objective (F1 kept as an option), theta grid extended to
  {0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80}, merged-class F1/F0.5 metrics, output moved to `stepD/D3`
  (the D2 outputs of v1.0 are untouched; predictions are read from `stepD/D2`).
- `tasks/D3_report.md` (new): this report.

Results on Drive: `stepD\D3\` = `transition_events_{runs,results,summary}`, `transition_events_log.txt`,
`stairs_rule_{runs,results,summary}`, `rule_params.csv`, `stairs_rule_log.txt`; smoke run in `D3\smoke\`.

## 3. Commands

```
# Part A, one run first (V3recipe 2 s seed 0, prints the true counts and examples)
python pipeline/transition_events.py --one
# Part A, all runs
python pipeline/transition_events.py                                        # 3.0 min

# Part B, smoke then all runs (F1 and F0.5 in one pass)
python pipeline/stairs_rule.py --smoke --max-rows 30000
python pipeline/stairs_rule.py                                             # 5.1 min
```
Scratch scripts in `cache\` (git-ignored): `d3_numbers.py` (the tables below).

## 4. Acceptance checks

### 4.1 Part A on one run — PASS (truth counts fit the task's expectation)

| source | recordings | true sit_to_stand | true stand_to_sit |
|---|---|---|---|
| simulation | 3,445 streams (v1.6 + Camargo), 240 true events, 3,385 recordings without a transition | 120 | 120 |
| CeTI s01 | 64 recordings (32 people x 2 tasks) | 4.0 per recording | 4.1 per recording |
| TUG (approx) | 108 recordings | 8.0 per recording | 6.0 per recording |

So CeTI s01 gives about 4 + 4 events per recording and TUG about 8 + 6, in line with "five sit-to-stands"; the exact
count differs between people, it is not a fixed 5.

`CeTI s01` truth needs one clarification: in these recordings the protocol walks between sitting and standing
(`sitting 0.02-0.30 s, transition, walking 0.66-0.94 s, transition, standing 1.00-1.10 s, ...`), so "sitting run ->
standing run with transition samples in between" only works if the walking samples are ignored as well. I take the
sequence of sitting/standing samples, drop posture runs shorter than 0.1 s (labeller jitter; this removes a
single-sample standing at t = 0) and count the changes. That reproduces the expected 4 + 4 per recording; the strict
reading (walking breaks the pair) gives 0 or 1 per recording.

Examples from the single run: `P000_sitstand.csv` true `6.4 sts, 14.7 s2s, 23.1 sts, 31.1 s2s`, R0 detected
`6.5 sts, 14.0 s2s, 24.0 sts, 31.5 sts` (3 matched, 1 direction error); `s01_ses01_run01` true `0.6, 1.4, 5.0, 5.7,
6.4, 7.1 s`, R0 detected nothing (the postures last 0.1-0.3 s, far below one 2 s window).

### 4.2 Part A tables — PASS

Event recall, % (mean over 3 seeds; sd in the summary), R0 = R1 unless stated:

| source | V3recipe 2s | 3s | 4s | 5s | V4data 2s | 3s | 4s | 5s | V4half 2s | 3s | 4s | 5s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| simulation | 86.8 | 80.1 | 75.7 | 64.4 | 85.4 | 80.0 | 77.6 | 64.4 | 83.3 | 81.1 | 78.1 | 64.3 |
| CeTI s01 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| TUG (approx) | 1.1 | 0.1 | 0.0 | 0.0 | 1.3 | 0.2 | 0.0 | 0.0 | 0.9 | 0.0 | 0.1 | 0.0 |

Direction errors, % of true events (simulation): 13.2 / 19.6 / 22.1 / 24.9 (V3recipe 2-5 s), 13.2 / 19.6 / 21.4 / 24.9
(V4data), TUG 0.7 / 0.2 / 0.2 / 0.1, CeTI 0.0 (nothing detected).

Event precision, %: simulation 73.7 / 77.8 / 78.3 / 83.9 (V3recipe R0). R1 improves it slightly (74.3 / 77.9 / 78.3 /
83.9) without changing recall — R1 drops only false detections, because true transitions always have a `still` window
nearby. TUG 91.5 / 100 / - / - (V4data 77.7 / 83.3, V4half 73.6 / 100 / 100), on very few detections.

False events per hour (no-transition recordings, R0 = R1):

| recordings | V3recipe 2s | 3s | 4s | 5s | V4data 2s | 3s | 4s | 5s |
|---|---|---|---|---|---|---|---|---|
| Luo (no CALIB) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| WearGait-PD SelfPace | 2.3 | 1.6 | 1.0 | 0.0 | 3.0 | 1.8 | 0.9 | 0.1 |
| WearGait-PD HurriedPace | 1.9 | 0.3 | 0.0 | 0.0 | 2.1 | 0.9 | 0.0 | 0.0 |
| Camargo (no transition) | 0.3 | 0.1 | 0.0 | 0.0 | 0.4 | 0.0 | 0.0 | 0.0 |

The model never predicts sit_to_stand/stand_to_sit on Luo non-CALIB windows at all (0 of 47,868 windows at 2 s), so
Luo's 0.00 is real, not a missing measurement. Window-level recall on the simulation (from D2) for comparison:
sit_to_stand 77.2 / 81.1 / 75.4 / 82.1, stand_to_sit 83.8 / 75.9 / 78.4 / 77.9 (V3recipe 2-5 s) — the event view is
stricter than the window view at 2 s (86.8 % of events vs 77-84 % of windows).

### 4.3 Part B — PASS (all runs, rule never touches a non-stairs window: 0 in all 36 runs)

The F0.5 objective changes which parameters win: `(k, n) > (1, 1)` in **72 of 180 folds** (F1 objective: 18 of 180).
F0.5 uses theta 0.20-0.50 with (k >= 2, n >= 2) in 72 folds and theta 0.50/0.60 with (1, 1) in the other 108; F1 stays
at theta 0.20-0.40 with (1, 1) in 162 of 180 folds. Full counts in `rule_params.csv` and in `stairs_rule_summary.md`.

Key numbers (mean over seeds; before / v1 F1 / v2 F0.5), 2 s windows:

| quantity | V3recipe | V4data | V4half |
|---|---|---|---|
| WearGait-PD HurriedPace called stairs % | 7.9 / 5.7 / 3.1 | 7.2 / 6.1 / 3.1 | 8.0 / 6.2 / 3.5 |
| Lencioni fast called stairs % | 12.8 / 9.2 / 3.9 | 11.1 / 9.4 / 3.1 | 11.7 / 9.2 / 3.1 |
| Luo FE called stairs % | 17.5 / 13.8 / 10.3 | 10.3 / 9.2 / 4.5 | 11.9 / 9.8 / 5.7 |
| Luo GR called stairs % | 27.5 / 22.3 / 16.4 | 22.0 / 20.1 / 13.1 | 23.5 / 20.1 / 13.7 |
| Luo stairs_up recall % | 50.4 / 46.5 / 40.1 | 69.2 / 66.8 / 59.9 | 63.0 / 59.6 / 54.0 |
| Luo stairs_down recall % | 83.4 / 78.0 / 71.6 | 89.4 / 86.6 / 79.6 | 88.5 / 84.4 / 78.6 |
| Luo stairs_up precision % | 41.3 / 45.7 / 48.8 | 55.7 / 57.8 / 64.7 | 52.6 / 56.0 / 62.9 |
| Luo stairs_down precision % | 28.7 / 30.7 / 34.1 | 38.1 / 38.9 / 46.1 | 34.6 / 36.2 / 41.4 |
| Luo merged stairs F1 % | 69.2 / 69.6 / 68.4 | 78.3 / 77.9 / 78.9 | 76.1 / 76.0 / 76.8 |
| Luo merged stairs F0.5 % | 62.0 / 64.5 / 66.9 | 72.3 / 73.0 / 78.4 | 69.6 / 71.4 / 76.0 |
| PAMAP2 stairs_up recall % | 38.7 / 35.4 / 31.4 | 36.8 / 35.3 / 30.8 | 37.9 / 35.6 / 32.1 |
| PAMAP2 stairs_down recall % | 52.6 / 47.4 / 42.6 | 57.5 / 54.4 / 50.0 | 57.3 / 53.4 / 49.9 |

At 5 s the same table is more favourable to the rule (Luo merged F0.5: 66.7 / 66.9 / 68.5 for V3recipe, 77.9 / 78.5 /
87.8 for V4data, 71.5 / 71.5 / 84.8 for V4half); all variants and lengths are in `stairs_rule_summary.md`.

### 4.4 One-screen summary for the owner (numbers only, mean over 3 seeds, v2 rule)

| W | variant | Luo stairs F0.5 | Luo FE called stairs % | Lencioni fast % | STS event recall % | false events/h (WG SelfPace) | WearGait walking % | KneE-PAD walking % | nodes |
|---|---|---|---|---|---|---|---|---|---|
| 2 s | V3recipe | 66.9 | 10.3 | 3.9 | 86.8 | 2.3 | 87.7 | 67.7 | 17,731 |
| 2 s | V4data | **78.4** | 4.5 | 3.1 | 85.4 | 3.0 | 83.9 | 60.5 | 18,741 |
| 2 s | V4half | 76.0 | 5.7 | 3.1 | 83.3 | 2.4 | 84.5 | 61.6 | 18,665 |
| 3 s | V3recipe | 69.8 | 7.6 | 3.0 | 80.1 | 1.6 | 81.8 | 67.7 | 16,712 |
| 3 s | V4data | **81.4** | 2.6 | 1.9 | 80.0 | 1.8 | 76.6 | 62.5 | 17,353 |
| 3 s | V4half | 78.3 | 4.9 | 2.7 | 81.1 | 1.3 | 77.5 | 63.5 | 17,205 |
| 4 s | V3recipe | 74.7 | 4.1 | 1.9 | 75.7 | 1.0 | 90.2 | 76.6 | 14,825 |
| 4 s | V4data | **83.8** | 1.9 | 0.5 | 77.6 | 0.9 | 85.7 | 68.7 | 16,389 |
| 4 s | V4half | 82.4 | 2.8 | 1.1 | 78.1 | 0.9 | 86.1 | 70.4 | 16,131 |
| 5 s | V3recipe | 68.5 | 4.6 | 1.1 | 64.4 | 0.0 | 89.5 | 83.1 | 14,165 |
| 5 s | V4data | **87.8** | 0.6 | 0.5 | 64.4 | 0.1 | 84.4 | 76.7 | 14,986 |
| 5 s | V4half | 84.8 | 1.2 | 0.4 | 64.3 | 0.0 | 86.3 | 78.1 | 14,733 |

Walking recall here is after the v2 rule (the rule only turns stairs into walking, so it is 0.1-1.5 points above the
no-rule value). V4data has the best Luo stairs F0.5 at every window length (11.5 / 11.6 / 9.1 / 19.3 points above
V3recipe); V3recipe keeps the best WearGait-PD walking recall at every length and the best KneE-PAD recall at 2-3 s.

## 5. Problems and open questions

1. **The CeTI s01 truth needed an interpretation** (4.1): walking samples sit between sitting and standing in those
   recordings, so the literal rule ("transition samples allowed in between") finds almost nothing. I ignored walking
   too and dropped posture runs < 0.1 s. If the manager wants the strict reading, the numbers change completely.
2. **CeTI s01 event recall is 0 % at every window length and variant.** The postures last 0.1-0.3 s, which a 2 s window
   cannot resolve; the recording is 7.6-11.5 s with 4 + 4 transitions. This dataset cannot judge event detection at
   50 Hz/2 s windows — it needs the per-sample classifier or a much shorter window.
3. **TUG truth is approximate** (HAR labeller, macro-F1 0.79) and the numbers are poor: event recall 0.9-1.3 % at 2 s,
   0.0-0.2 % from 3 s; precision 74-92 % but on only a handful of detections. TUG is ~30 s with 8 + 6 sitting
   boundaries, and the model mostly calls the sitting part `still`, so the event rule (which only sees
   sit_to_stand/stand_to_sit windows) almost never fires.
4. **Only the simulation gives usable event recall** (86.8 % at 2 s -> 64.4 % at 5 s, precision 73.7 -> 83.9 %). CeTI
   s01 (0 %) and TUG (~1 %) fail for structural reasons (postures of 0.1-0.3 s; long recordings with one posture change
   in the middle), so the event metrics rest on 240 simulated events, not on real people. A real-data event test needs
   recordings with clear, held postures (the real implant recordings would be the right source, but they are not in the
   workspace).
5. **The rule's F0.5 win is a recall-for-precision trade** and the owner should see both: at 2 s on Luo, stairs_up
   recall falls to 40.1 % (V3recipe) while precision rises to 48.8 %. On V4data at 5 s the trade is much better
   (F0.5 87.8 %, stairs_up recall 56.9 % after the rule) because the model itself is better.
6. **False events per hour**: only WearGait-PD SelfPace is above 1/h at 2 s (2.3-3.0); everything is <= 1/h from 4 s.
   Luo is exactly 0 because the model never predicts a transition class there (measured over 34,634 windows).
7. **Model size** at 5 s (14.2-15.0 k nodes) is below 2 s (17.7-18.7 k), and the seed sd is ~1 k nodes — a window
   length decision should not be made on a node difference below ~7 %.
