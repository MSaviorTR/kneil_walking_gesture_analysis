# D2 report: seed noise, weight of the new data, and the stairs evidence rule

## 1. Status

Done — parts A, B and C all finished and all acceptance checks pass. Main finding: with the prescribed tuning
objective the evidence requirement (k, n) never wins; only the low confidence thresholds with (k, n) = (1, 1) do, so the
rule removes low-confidence stairs windows and leaves the rest — it lowers "walking called stairs" by 20-30 % relative
but costs 2-5 points of stairs recall (numbers in 4.4).

## 2. Files

- `pipeline/stage3_v4.py` -> **1.1**: new int array `stream` (one id per recording and leg, one `R.add` call each),
  `load_sim` now adds one stream per CSV file (it added all simulation windows in one call before), output folder
  `stepD/windows_v11`; `load_windows_w` returns the source file per window when asked (`files_out=True`).
- `pipeline/cv_v4.py` -> **1.1**: `--seeds`, variant `V4half`, `predict_proba` saved, filenames
  `pred_{variant}_W{W}s_8cls_seed{s}.npz`, tables aggregated as mean (sd) over the seeds, reads `windows_v11`,
  outputs `D2_runs.csv` (per seed) + `D2_results.csv` + `D2_summary.md` under `stepD/D2`.
- `pipeline/stairs_rule.py` (new, **1.0**): the causal rule, in-CV tuning of (theta, k, n), before/after tables.
- `tasks/D2_report.md` (new): this report.

Nothing else changed. The D0 files (`stepD/windows/`), the D1 predictions and D1/D0 results were not touched (the new
prediction names include the seed; the new windows live in `windows_v11`).

Results on Drive: `stepD\windows_v11\windows_W{2,3,4,5}s.npz`; `stepD\D2\` = 36 `pred_*.npz`, `D2_runs.csv`,
`D2_results.csv`, `D2_summary.md`, `rule_params.csv`, `stairs_rule_runs.csv`, `stairs_rule_results.csv`,
`stairs_rule_summary.md`, the two logs; smoke run in `D2\smoke\`.

## 3. Commands

```
# Part A: rebuild with stream ids (4 files)
python pipeline/stage3_v4.py --win 2      # 1.2 min, 334,291 windows
python pipeline/stage3_v4.py --win 3
python pipeline/stage3_v4.py --win 4
python pipeline/stage3_v4.py --win 5

# Part B: smoke, then the 36 runs
python pipeline/cv_v4.py --win 2 --variants V3recipe V4data V4half --seeds 0 1 --max-rows 30000
python pipeline/cv_v4.py --win 2 3 4 5 --seeds 0 1 2 --variants V3recipe V4data V4half      # 4.5 min

# Part C: smoke, then all runs
python pipeline/stairs_rule.py --smoke --max-rows 30000
python pipeline/stairs_rule.py                                                              # 1.8 min
```
Environment: Python 3.12.10, numpy 2.5.4, scikit-learn 1.9.1, 12 cores. Scratch checks in `cache\` (git-ignored):
`check_v11.py` (part A), `diag_rule.py` (objective grid), `d2_numbers.py`, `d2b_numbers.py`.

## 4. Acceptance checks

### 4.1 Part A: stream ids — PASS

| window | rows | X | Xr | y | ds | grp | lab | `stream` | W |
|---|---|---|---|---|---|---|---|---|---|
| 2 s | 334,291 | = | = | = | = | = | = | present | 100 |
| 3 s | 318,602 | = | = | = | = | = | = | present | 150 |
| 4 s | 304,349 | = | = | = | = | = | = | present | 200 |
| 5 s | 290,745 | = | = | = | = | = | = | present | 250 |

(`np.array_equal` against the D0 files; `Xr` compared with `equal_nan=True`.) Stream ids are non-decreasing, never span
two datasets or two people, and there are 15,040 streams at 2 s:

| dataset | rows | streams | rows/stream |
|---|---|---|---|
| Caicedo older adults | 1,434 | 440 | 3.3 |
| Camargo simulated | 50,415 | 3,145 | 16.0 |
| CeTI | 72,412 | 3,054 | 23.7 |
| KneE-PAD | 5,559 | 2,052 | 2.7 |
| Lencioni | 8,253 | 1,159 | 7.1 |
| Luo | 51,086 | 3,420 | 14.9 |
| MHEALTH | 24,301 | 10 | 2,430.1 |
| Marpino | 4,404 | 153 | 28.8 |
| PAMAP2 | 24,551 | 7 | 3,507.3 |
| WearGait-PD | 82,250 | 1,300 | 63.3 |
| v1.6 synthetic | 9,626 | 300 | 32.1 |

(MHEALTH and PAMAP2 store their whole protocol under one npz key per person, so one row of the stage 2 index = one
stream there; that is the data, not a loader choice.) **Time order** was checked by recomputing 12 sampled streams from
the source and comparing `X` row by row — all equal: 2 v1.6 CSVs, 2 Camargo CSVs, 2 Caicedo keys, WearGait-PD
`Balance|R` and `Balance|L` (two different ids for the two legs of the same recording), Luo `01_CALIB|R` and
`02_CALIB|R`, Lencioni `000_Walking|R` and `001_Walking|R`.

### 4.2 Part B: seeds, V4half, probabilities — PASS

- **Seed 0 reproduces D1 exactly**: `pred_V3recipe_W2s_8cls_seed0.npz` vs D1's `pred_V3recipe_W2s_8cls.npz`
  (D0 window files) — 334,291 / 334,291 predictions identical. Probabilities have shape (334,291, 8), float16, row
  sums 0.9995-1.0.
- 36 runs finished (3 variants x 4 window lengths x 3 seeds), `D2_summary.md` has tables a-g for all 12 variant x
  window combinations as mean (sd); `D2_runs.csv` keeps the per-seed values.

Walking recall, % (mean (sd) over 3 seeds), and simulated macro-F1:

| dataset | V3recipe 2s | V4data 2s | V4half 2s | V3recipe 5s | V4data 5s | V4half 5s |
|---|---|---|---|---|---|---|
| CeTI | 97.2 (0.1) | 95.8 (0.3) | 96.3 (0.2) | 99.7 (0.1) | 98.9 (0.1) | 99.2 (0.1) |
| KneE-PAD | 64.3 (1.1) | 57.4 (1.0) | 58.4 (1.3) | 78.5 (1.8) | 72.5 (0.5) | 73.5 (0.6) |
| Lencioni | 91.4 (0.1) | 93.2 (0.2) | 92.6 (0.3) | 95.6 (0.5) | 96.4 (0.0) | 95.7 (0.2) |
| Luo | 80.2 (1.3) | 86.6 (0.5) | 84.9 (0.5) | 84.7 (2.7) | 90.4 (0.8) | 86.6 (1.7) |
| MHEALTH | 100.0 (0.0) | 99.8 (0.1) | 99.3 (0.3) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) |
| Marpino | 84.3 (1.5) | 85.4 (0.9) | 85.7 (0.3) | 84.3 (0.4) | 88.6 (2.1) | 87.7 (1.8) |
| PAMAP2 | 82.1 (0.3) | 85.5 (2.5) | 84.9 (2.6) | 74.4 (5.7) | 71.7 (7.9) | 74.7 (3.4) |
| WearGait-PD | 85.0 (0.4) | 81.0 (0.4) | 81.5 (0.4) | 87.3 (0.5) | 82.0 (0.0) | 83.8 (0.6) |
| **simulated macro-F1** | 80.8 (0.5) | 81.3 (0.1) | 80.9 (0.3) | 77.2 (0.7) | 79.3 (0.5) | 78.5 (0.8) |

Luo macro-F1 71.5 -> 79.4 (V4data) / 76.8 (V4half) at 2 s, 77.6 -> 86.5 / 82.8 at 5 s. Model size: 17,731 (1232) /
18,741 (701) / 18,665 (931) nodes at 2 s (V3recipe / V4data / V4half) — the seed spread is ~7 %, so node counts also
need the seeds.

**V4half is the compromise the manager asked for**: it keeps most of the old-dataset walking recall (KneE-PAD 58.4 vs
57.4 for V4data and 64.3 for V3recipe; WearGait-PD 81.5 vs 81.0 vs 85.0) while taking most of the Luo gain
(84.9 vs 86.6 vs 80.2). Stairs at 2 s: Luo stairs_up 50.4 (V3recipe) / 69.2 (V4data) / 63.0 (V4half).

### 4.3 Part C: stairs evidence rule — PASS

Smoke test first on 6 runs (3 variants x 2 seeds, 30,000 rows): 246 table rows, rule applied, no error. Then all 36
runs: 984 table rows, 1.8 min. **The rule never changed a non-stairs prediction** (the script counts them per run and
prints an ERROR otherwise): 0 in all 36 runs. Windows changed: 175-6,596 per run (more with longer windows).

Parameters chosen per fold (5 folds x 3 seeds = 15 per variant x W): `(0.30, 1, 1)` in 138 of 180 folds,
`(0.40, 1, 1)` in 24, `(0.30, 2, 3)` in 18. **The evidence requirement (k >= 2, n >= 2) is only chosen in 18 of 180
folds**, and only at the lowest theta; `rule_params.csv` has every fold. The objective grid on V3recipe 2 s seed 0
(fold 0 training folds) shows why: best `(0.30,1,1)` = 0.6870, best with evidence `(0.30,2,3)` = 0.6867, then
`(0.40,2,3)` = 0.6760, `(0.50,2,2)` = 0.6082, `(0.70,4,5)` = 0.2676 — every extra window of required evidence removes
true stairs windows faster than it removes false ones.

Effect (V3recipe 2 s, mean over seeds): stairs recall 83.4 -> 78.0 (Luo down), 50.4 -> 46.5 (Luo up),
73.7 -> 69.1 (simulated down); stairs precision 28.7 -> 30.7 (Luo down), 41.3 -> 45.7 (Luo up),
68.4 -> 76.9 (simulated down); walking recall 80.2 -> 84.0 (Luo), 82.1 -> 84.5 (PAMAP2), 85.0 -> 86.3 (WearGait-PD).
So the rule trades a little stairs recall for precision and for fewer walking windows that are sent to stairs.

### 4.4 The owner's question: fast walking called stairs (before -> after), %

| group | V3recipe 2s | 3s | 4s | 5s | V4data 2s | 3s | 4s | 5s | V4half 2s | 3s | 4s | 5s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WearGait-PD HurriedPace | 7.9 -> 5.7 | 7.4 -> 7.2 | 6.5 -> 6.5 | 7.5 -> 7.3 | 7.2 -> 6.1 | 6.5 -> 6.5 | 4.9 -> 4.9 | 5.3 -> 5.1 | 8.0 -> 6.2 | 7.2 -> 7.1 | 6.2 -> 6.2 | 5.8 -> 5.8 |
| Lencioni fast | 12.8 -> 9.2 | 9.3 -> 9.0 | 6.4 -> 5.8 | 7.2 -> 7.0 | 11.1 -> 9.4 | 6.4 -> 6.4 | 4.5 -> 4.5 | 4.8 -> 4.1 | 11.7 -> 9.2 | 7.8 -> 7.3 | 4.9 -> 4.9 | 5.7 -> 5.7 |
| Luo FE | 17.5 -> 13.8 | 15.5 -> 15.1 | 15.8 -> 15.5 | 14.7 -> 14.3 | 10.3 -> 9.2 | 6.6 -> 6.6 | 7.9 -> 7.9 | 7.6 -> 6.9 | 11.9 -> 9.8 | 11.0 -> 10.5 | 11.0 -> 11.0 | 11.7 -> 11.7 |
| Luo GR | 27.5 -> 22.3 | 26.5 -> 25.9 | 23.5 -> 23.3 | 25.3 -> 24.6 | 22.0 -> 20.1 | 18.3 -> 18.3 | 18.1 -> 18.0 | 17.4 -> 16.4 | 23.5 -> 20.1 | 23.3 -> 22.5 | 21.4 -> 21.4 | 21.8 -> 21.8 |

Luo stairs recall after the rule (same columns): stairs_up 46.5 / 50.3 / 56.1 / 60.1 (V3recipe), 66.8 / 73.3 / 76.3 /
82.2 (V4data), 59.6 / 63.6 / 71.5 / 77.0 (V4half); stairs_down 78.0 / 91.1 / 92.6 / 88.7, 86.6 / 94.6 / 95.7 / 95.3,
84.4 / 94.2 / 95.5 / 95.5. Today's recipe (V3recipe 2 s) plus the rule: HurriedPace 5.7 %, Luo GR 22.3 %, Luo stairs_up
46.5 %; the V4data variants do better on both sides (Luo GR 20.1 %, stairs_up 66.8 %).

## 5. Problems and open questions

1. **The rule's evidence requirement does not pay off.** With the objective as specified (mean stairs F1 over Luo,
   PAMAP2, simulated), (k, n) > (1, 1) wins only 18 of 180 folds and never above theta 0.30. The stairs windows in
   these datasets are short bursts, so requiring two or more windows of evidence removes true stairs faster than false
   ones. If the rule should bite harder, the objective needs a precision weight (F0.5, or a penalty on walking-called-
   stairs), or the grid needs a smaller theta (0.20 is below the current edge and may win).
2. **The choice is dominated by PAMAP2**, whose stairs F1 is lower than Luo's and the simulation's, and which has only
   7 people (walking recall sd 5-8 points at 5 s). An unweighted mean over the three datasets lets it decide.
3. **V4half vs V4data** (open decision for the owner): V4half keeps 1-5 points more on the old real datasets
   (KneE-PAD 58.4 vs 57.4, WearGait-PD 81.5 vs 81.0) and gives up 1-2 points on Luo (84.9 vs 86.6). Both beat
   V3recipe on Luo by 5-6 points.
4. **Window length** (same conclusion as D1, now with seed noise): 3 s is the best simulation macro-F1 (80.9 / 82.2 /
   81.6), 4-5 s are best for stairs (Luo up 56.7-83.2, PAMAP2 up 53.8-67.4) and for still in the simulation it gets
   worse (v1.6 still 86.6 -> 77.4). No single length wins everywhere.
5. **Seed noise is real**: walking recall sd 0.0-2.7 points on the big datasets, 5-8 on PAMAP2 at 5 s; the node count
   sd is ~7 %. Comparisons below ~2 points are not meaningful; every number in this report is a 3-seed mean.
6. **Part C needs `--max-rows`** when run on the smoke predictions (`stairs_rule.py --smoke --max-rows 30000`),
   otherwise the row counts do not match; the script now stops with a clear message instead of crashing.
7. **MHEALTH lying is 90.0 (0.0) in all 12 configurations** (613 windows): the same windows are missed by every forest.
   Worth a look when the confusion is examined, but it is a property of that recording, not of the rule.
