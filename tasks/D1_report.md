# D1 report: cross-validation of 8 classes x window length x data variant

## 1. Status

Done — 8 full runs + the V3 regression run finished, all tables written. Check 1 does **not** reach 99.5 % (90.81 %);
the cause is diagnosed and is environmental (the V3 predictions cannot be reproduced with this sklearn build, and any
reseed of this code gives the same ~90 %). Checks 2-4 pass.

## 2. Files

- `pipeline/cv_v4.py` (new): 8-class mapping, folds by person, the two data variants, 5-fold CV per (variant, window,
  classes), tables a-g, `D1_results.csv` (long) + `D1_summary.md`.
- `tasks/D1_report.md` (new): this report.

Nothing else changed: `stage3.py`, the D0 files, the chip library and the D0 window caches are untouched.
Results on Drive: `KNEIL_results\v4\stepD\D1\` = `pred_{variant}_W{2,3,4,5}s_{8,9}cls.npz` (9 files),
`D1_results.csv`, `D1_summary.md`, `cv_v4_log.txt`; the smoke test is in `D1\smoke\`.

## 3. Commands

```
# smoke test (check 2), writes stepD\D1\smoke
python pipeline/cv_v4.py --win 2 --variants V3recipe V4data --max-rows 30000

# check 1: V3 regression (9 classes, V3 fold map)
python pipeline/cv_v4.py --win 2 --variants V3recipe --classes 9

# the 8 runs of check 3 (8 classes x 2 variants x 4 window lengths)
python pipeline/cv_v4.py --win 2 3 4 5 --variants V3recipe V4data
```
Environment: Python 3.12.10, numpy 2.5.4, scikit-learn 1.9.1, 12 logical cores. The 8 runs take 1.0 min, the 9-class
run 0.1 min (the forest fits are fast; the window loading is the slow part). Scratch scripts in `cache\` (git-ignored):
`diag_d1.py`, `diag_d1b.py`, `diag_d1c.py`, `check_d1_reg.py`, `d1_numbers.py`.

## 4. Acceptance checks

### 4.1 Regression against V3 — FAIL on the 99.5 % criterion (90.81 %), cause diagnosed

Run `V3recipe`, W = 2 s, 9 classes, folds = the V3 cache map. What is identical to V3:

| item | result |
|---|---|
| fold of every old row | **274,952 / 274,952 equal** to `stage3.assign_folds` on the V3 cache |
| training rows per fold | **identical to the V3 log**: 159,747 / 160,626 / 167,047 / 166,830 / 167,778 |
| test windows per fold | identical to the V3 log: 60,800 / 60,081 / 50,919 / 52,314 / 50,838 |
| labels `y` in the training set | identical (`np.array_equal`) |
| sample weights | identical, `max|dw| = 0.00e+00` |
| training features | 18 of 20 features bit-identical; `tilt_sag_deg` / `tilt_cor_deg` <= 1 float32 ULP (D0) |
| predictions | **249,688 / 274,952 identical = 90.81 %** -> below 99.5 % |

Diagnosis (measured, in this order):

1. Retraining fold 0 on the **V3 cache's own `X`** (not the rebuilt one) gives 90.27 % agreement with the V3
   predictions (`cache\diag_d1.py`). So the rebuilt features are not the cause.
2. The environment is deterministic: two identical fits agree on 100.00 % of windows.
3. Any perturbation of the fit moves the agreement to the same ~90 % band: `random_state=1` 90.02 %,
   `min_samples_leaf` 2 or 4 90.15 / 90.20 %, `max_features=5` 90.92 %, `class_weight='balanced'` 90.12 %,
   10 instead of 20 trees 89.25 %, `max_features=None` 87.08 % (`cache\diag_d1c.py`).
4. Per-class agreement on fold 0: lying 99.0 %, bed_transfer 100 %, walking 94.2 %, standing 93.4 %, sitting 86.6 %,
   stairs 87-91 %. The classes that differ are exactly the ones that overlap at the tibia.
5. Aggregate quality is comparable to the V3 report (V3 value in brackets, from `stage3_results.csv`): simulated
   macro-F1 **80.1** (77.4), CeTI 65.7 (65.4), KneE-PAD 76.5 (85.3), MHEALTH 97.4 (94.9), Marpino 94.0 (89.2),
   PAMAP2 68.5 (68.3), WearGait-PD 79.6 (78.9).

Conclusion: the V3 CV predictions were produced by a different tree-fitting build (Colab at V3 time, scikit-learn
version not recorded in the repo). With 8-9 heavily overlapping classes a 20-tree forest changed in any way — even a
different seed — only agrees window-by-window on ~90 %. The 99.5 % criterion can only be met by bit-identical fitting
code, which this environment does not have. I did not weaken the check; the numbers are as measured.

### 4.2 Smoke test — PASS

`--win 2 --variants V3recipe V4data --max-rows 30000`: 30,000 rows (11 datasets, seed 0, proportional per dataset),
2 runs, 200 table rows, all 9 tables, `D1_results.csv` + `D1_summary.md` written, exit code 0, 0.0 min. Output goes to
`stepD\D1\smoke` and is never resumed from the real cache.

### 4.3 Eight full runs + all tables — PASS

8 runs (2 variants x 4 window lengths) finished; `D1_summary.md` holds tables a-g for **every** run in the merged table
(9 runs, 860 long-format rows; the 9-class run has 107 rows, each 8-class run 100). Fold sizes per run, e.g. V3recipe
2 s: [73,202 71,385 65,192 64,401 60,111]. Random seed fixed inside `stage3.make_model`; runs resume from the npz.

Luo and Lencioni are `src == 'real'` in the D0 files (verified: 51,086 + 8,253 rows) and receive folds like every
other real dataset (30 + 50 groups).

### 4.4 Sanity: 8-class vs 9-class (V3recipe, 2 s) — close for the fold-identical datasets

| dataset | walking 8-class | walking 9-class | delta | folds identical? |
|---|---|---|---|---|
| CeTI | 97.1 | 97.1 | 0.0 | yes |
| KneE-PAD | 63.6 | 61.9 | +1.7 | yes |
| MHEALTH | 100.0 | 100.0 | 0.0 | no (5 groups) |
| Marpino | 82.8 | 86.7 | -3.9 | no (2 groups) |
| PAMAP2 | 82.4 | 87.1 | -4.6 | no (7 groups) |
| WearGait-PD | 84.6 | 84.4 | +0.2 | no (91 groups) |
| simulated | 96.2 | 95.9 | +0.3 | yes |

Where the fold map is identical, merging sitting+standing changes walking by <= 1.7 points. The larger deltas are in
the datasets whose fold map differs between the two runs (see 5.2); PAMAP2 has only 7 people, so a different fold
split alone moves it by several points. Macro-F1 is not comparable across 8/9 classes (CeTI 98.2 vs 65.7) because in
9-class scoring the 22 sitting windows form a class of their own.

### Main tables (2 s and 5 s shown; all four lengths in `D1_summary.md`)

Walking recall, %:

| dataset | V3recipe 2s | V3recipe 5s | V4data 2s | V4data 5s |
|---|---|---|---|---|
| CeTI | 97.1 | 99.8 | 95.5 | 98.9 |
| KneE-PAD | 63.6 | 77.7 | 56.6 | 71.9 |
| Lencioni (test) | 91.4 | 95.1 | 93.2 | 96.4 |
| Luo | 79.0 | 83.7 | 86.1 | 91.4 |
| MHEALTH | 100.0 | 100.0 | 99.7 | 100.0 |
| Marpino | 82.8 | 84.7 | 84.4 | 89.3 |
| PAMAP2 | 82.4 | 74.7 | 85.7 | 65.3 |
| WearGait-PD | 84.6 | 87.5 | 80.6 | 82.0 |

WearGait-PD walking per person (median / p10), controls / Parkinson: 84.8 / 75.5 and 87.8 / 80.8 (V3recipe 2 s),
89.9 / 75.3 and 92.2 / 79.8 (V3recipe 4 s), 81.4 / 70.0 and 84.9 / 77.9 (V4data 2 s).

Stairs, % (recall / precision):

| dataset | activity | V3recipe 2s | V3recipe 5s | V4data 2s | V4data 5s |
|---|---|---|---|---|---|
| Luo | stairs_up | 49.8 / 39.9 | 62.4 / 44.8 | 66.8 / 54.3 | 80.6 / 59.1 |
| Luo | stairs_down | 84.3 / 27.1 | 90.9 / 33.3 | 89.7 / 38.5 | 95.5 / 47.4 |
| PAMAP2 | stairs_up | 38.1 / 26.5 | 64.7 / 27.3 | 37.8 / 22.6 | 67.2 / 28.2 |
| PAMAP2 | stairs_down | 52.1 / 18.8 | 53.9 / 20.7 | 57.4 / 21.9 | 68.4 / 21.1 |

Walking called stairs (% of true walking windows), by speed / surface:

| group | V3recipe 2s | V3recipe 5s | V4data 2s | V4data 5s |
|---|---|---|---|---|
| WearGait-PD rec=SelfPace | 4.5 | 2.9 | 4.6 | 3.1 |
| WearGait-PD rec=HurriedPace | 8.3 | 7.9 | 7.9 | 5.2 |
| Lencioni speed_abs=slow | 3.0 | 0.2 | 0.7 | 0.3 |
| Lencioni speed_abs=fast | 11.9 | 9.0 | 11.4 | 3.0 |
| Luo surface=BnkL | 13.6 | 10.9 | 9.9 | 5.8 |
| Luo surface=CS | 21.9 | 14.1 | 11.6 | 6.4 |
| Luo surface=FE | 18.3 | 16.0 | 11.4 | 6.5 |
| Luo surface=GR | 29.9 | 26.9 | 21.7 | 16.4 |

Still (sitting + standing) and lying recall, % (2 s): CeTI still 99.0, WearGait-PD still 97.6, Marpino still 97.1,
PAMAP2 still 95.2 / lying 93.5, MHEALTH still 99.7 / lying 90.0, Luo still 99.1, Camargo still 54.0,
v1.6 still 85.0 / lying 99.0 (V4data 2 s: Camargo 61.9, v1.6 85.6). Simulated macro-F1: 80.2 / 81.0 / 79.1 / 77.7
(V3recipe 2-5 s), 81.2 / 82.4 / 80.7 / 78.9 (V4data).

Model size (nodes, fold 0): 16,824 / 16,214 / 14,062 / 13,368 (V3recipe 2-5 s), 18,722 / 16,904 / 15,572 / 14,284
(V4data), 18,302 (9-class V3 recipe); see 5.5.

## 5. Problems and open questions

1. **Check 1 cannot pass here.** The criterion needs bit-identical model fitting; this machine has scikit-learn 1.9.1
   and the V3 predictions came from the Colab environment. Even the V3 cache's own training `X` gives 90.27 %, and a
   different seed on the current code gives 90.02 %. Options: (a) accept an aggregate criterion (mean real F1 within
   ~1 point, per-dataset within a few points — met), (b) regenerate a V3 reference in this environment once and use it
   for future regressions, (c) record the sklearn version in `kneil_model_info.h` from now on.
2. **The two fold maps differ.** Task item 2 says use `assign_folds` on the 2 s file; check 1 says the fold of every row
   must equal `assign_folds` on the V3 cache. Those are different: inserting Luo and Lencioni into the sorted
   real-dataset list shifts the RNG stream, which moves **105 old groups** (WearGait-PD 91, PAMAP2 7, MHEALTH 5,
   Marpino 2). I resolved it as written: the 8-class runs use the 2 s-file map, the 9-class regression run uses the V3
   map for the old rows (and the 2 s-file map for the Luo/Lencioni rows, which have no V3 fold). Say if you want the
   8-class runs on the V3 map too — it is a one-flag rerun (`--folds v3`), but then Luo/Lencioni rows would need the
   same extension.
3. **V4data trades old datasets for the new ones.** At 2 s: Luo walking +7.1, Luo stairs_up +17.0, Lencioni +1.8,
   but KneE-PAD -7.0, WearGait-PD -4.0, MHEALTH -0.3. At 5 s: Luo +7.7, PAMAP2 -9.4. The sqrt weighting gives Luo and
   Lencioni together about 24 % of the real-data weight (sqrt(n_d)/sum sqrt(n_d)); a lower weight for them is worth
   testing.
4. **Window length.** Stairs and Luo improve with longer windows (Luo stairs_up 49.8 -> 62.4, PAMAP2 stairs_up
   38.1 -> 64.7), but simulated `still` gets worse (58.4 -> 48.5) and PAMAP2 walking 82.4 -> 74.7; simulated macro-F1
   peaks at 3 s. No single length wins everywhere — the 3 s compromise looks best for the simulation and stairs, 2 s
   for the real walking recall.
5. **Model size.** 16.8 k nodes for the 8-class 2 s forest versus 18.3 k for the 9-class V3 recipe; the V3 forest that
   was deployed is a reference point I did not compare against (not asked here). This becomes a constraint when a V4
   model has to fit the chip, so it is worth comparing with the deployed V3 node count in the next step.
6. **Stairs precision is low** (Luo stairs_down 27 %, PAMAP2 19 %): the model over-predicts stairs on walking, which
   is the same phenomenon as the owner's real-device result. Longer windows help Luo but not the precision on PAMAP2.
7. **Luo slopes**: slope_up is predicted walking 90-95 % of the time (good), slope_down only 54-75 % and
   stairs_down 29-40 % (slopes downhill look like stairs, as expected from the tilt).
8. **Lencioni test stairs (out of training)**: stairs_down 75-88 % recognised, stairs_up mostly called walking
   (31 % at 2 s, 56 % at 5 s with V4data) — stairs up on the tibia remains the weak class.
9. **MHEALTH lying is 90.0 % in every run.** The value is identical to 0.1 % across 9 different models, which is
   plausible (one 613-window protocol) but suspicious; worth a look when the class confusion is examined.
10. `--max-rows` writes to `stepD\D1\smoke` on purpose, so a smoke test can never be resumed as if it were a full run.
