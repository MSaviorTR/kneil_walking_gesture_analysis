# A1 report: walking-aid personas and the cross-validation experiment

## 1. Status

Partly done. Part A (the 462 personas) and Part B (the full CV experiment and the owner summary) are complete; the
external G2 check is **negative**: the 8 AB07 viewer walker personas are still called `still` (Section 4.4). This is the
main result the owner has to decide on.

## 2. Files

Code (new files only; no existing pipeline file changed):
- `pipeline/aid_gait.py` — **new**, `aid_gait 1.0`: measured Camargo stride templates -> walker / rollator / crutches
  personas, rule C labels, chip features, plots, resume.
- `pipeline/cv_aid.py` — **new**, `cv_aid 1.0`: 5-fold CV by source person, 3 seeds, V4half + aid at 0.25/0.5/1.0,
  stairs rule 0.60, all requested metrics, `owner_summary.md`, `G2_check.md`.
- `tasks/A1_report.md` — this file.

Outputs (not committed; all under the allowed `KNEIL_results\v4\stepF\`):
- `stepF\aid_gait\` — `aid_personas.csv`, `aid_windows_W4s.npz`, `streams\` (462 npz), `AID_summary.md`,
  `aid_gait_log.txt`.
- `stepF\aid_gait_test2\` — the 2-persona test: 2 streams, `aid_windows_W4s.npz`, `AID_summary.md`,
  `plots\ab06_p00_pick-upwalker_step-through_full.png`, `plots\ab08_p00_pick-upwalker_step-through_full.png`.
- `stepF\cv_aid\` — `pred_aid_gait\` (3 seeds x 4 variants), `external_viewer_W4s.npz`, `cv_aid_runs.csv`,
  `cv_aid_results.csv`, `cv_aid_summary.md`, `owner_summary.md`, `G2_check.md`, `cv_aid_log.txt`.
- Diagnostic only, not kept: `cv_aid_ab07test\` (AB07 held out of training), log in `cache\cv_aid_ab07test.txt`.

## 3. Commands

```powershell
# 2-persona test first (AB06 and AB08, one persona each, signal + labels plot)
python pipeline/aid_gait.py --out-name aid_gait_test2 --people ab06 ab08 --personas-per-person 1 --plot --force

# full generation: 21 people x 22 personas = 462
python pipeline/aid_gait.py --out-name aid_gait --force

# experiment: 4 variants x 3 seeds
python pipeline/cv_aid.py --aid-name aid_gait --out-name cv_aid --seeds 0 1 2

# diagnostic for the negative external result (AB07 never in training)
python pipeline/cv_aid.py --aid-name aid_gait --out-name cv_aid_ab07test --variants V4half aid1.0 --seeds 0 --holdout-ab07

python -m py_compile pipeline/aid_gait.py pipeline/cv_aid.py
```

## 4. Acceptance checks

### 4.1 The 2-persona test (plots and label counts) — PASS

Two personas from two source people (AB06 and AB08), each a pick-up-walker, step-through, full-weight-bearing persona:

| persona | windows | walking (rule C) | still (rule C) | usable |
|---|---:|---:|---:|---:|
| `ab06_p00_pick-upwalker_step-through_full` | 62 | 34 | 28 | 52 |
| `ab08_p00_pick-upwalker_step-through_full` | 40 | 25 | 15 | 33 |
| **total** | **102** | **59** | **43** | **85** |

Plots (signal, contact ticks, window labels, moving share and steps per window):
- `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results\v4\stepF\aid_gait_test2\plots\ab06_p00_pick-upwalker_step-through_full.png`
- `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results\v4\stepF\aid_gait_test2\plots\ab08_p00_pick-upwalker_step-through_full.png`

The plots show the implant magnitude, the pause/step pattern and the green (walking) / blue (still) rule C windows;
the grey bands mark the walking<->standing transients that are not used for still training.

### 4.2 The persona table (counts and rule C windows) — PASS

21 Camargo source people (AB07 excluded), 462 personas, 19,269 windows: **14,298 walking / 4,971 still** by rule C;
15,469 usable for training (14,298 walking, 1,171 still). Persona and window counts:

| aid | personas | windows | walking | still |
|---|---:|---:|---:|---:|
| pick-up walker | 168 | 7,248 | 4,944 | 2,304 |
| rollator | 147 | 5,841 | 5,370 | 471 |
| crutches | 147 | 6,180 | 3,984 | 2,196 |
| **total** | **462** | **19,269** | **14,298** | **4,971** |

| achieved speed band | personas | windows | walking | still |
|---|---:|---:|---:|---:|
| 0.15-0.25 m/s | 113 | 4,863 | 3,135 | 1,728 |
| 0.25-0.35 m/s | 100 | 4,377 | 3,238 | 1,139 |
| 0.35-0.45 m/s | 125 | 4,955 | 4,356 | 599 |
| 0.45-0.55 m/s | 124 | 5,074 | 3,569 | 1,505 |

| weight bearing | personas | windows | walking | still |
|---|---:|---:|---:|---:|
| full | 189 | 7,989 | 6,210 | 1,779 |
| partial | 147 | 6,055 | 4,691 | 1,364 |
| toe-touch | 105 | 4,244 | 3,294 | 950 |
| non-weight-bearing | 21 | 981 | 103 | 878 |

The full tables, including the aid x speed-band crosstab, are in
`stepF\aid_gait\AID_summary.md`. `Usable` = rule C walking with start/stop windows included, plus clean pauses for
still (no step, <=10 % moving, no transient). The 21 NWB personas are the small set required by the task.

Published ranges used (G2 report section 3): pick-up walker 0.15-0.45 m/s with 20-45 % pauses, rollator 0.25-0.55 m/s
with 5-30 % pauses, crutches 0.15-0.55 m/s with 10-35 % pauses; step-to is used for the slow walker/partial-crutch
cases, step-through for the rollator and the faster cases.

### 4.3 The experiment (all variants) and the owner summary — PASS

Five folds by source person, 3 seeds, 4 s windows / 1 s hop, 8 classes, stairs rule 0.60; aid rows are held out with
their source person. V4half is reproduced exactly: the three V4half base prediction files are **304,349/304,349**
identical to the D2 `pred_V4half_W4s_8cls_seed{0,1,2}.npz` files.

Aid-gait walking recall (held-out, mean (sd) over 3 seeds, %):

| | V4half | aid0.25 | aid0.5 | aid1.0 |
|---|---:|---:|---:|---:|
| all aid | 42.5 (4.1) | 97.1 (0.1) | 98.5 (0.1) | **99.2 (0.1)** |
| pick-up walker | 27.9 (3.2) | 94.8 (0.2) | 97.3 (0.4) | 98.6 (0.2) |
| rollator | 61.0 (6.1) | 99.6 (0.0) | 99.9 (0.0) | 99.9 (0.1) |
| crutches | 35.8 (2.7) | 96.7 (0.2) | 98.1 (0.3) | 99.0 (0.2) |

By speed band (0.15-0.25 / 0.25-0.35 / 0.35-0.45 / 0.45-0.55), V4half -> aid1.0:
13.7 (1.7) -> 99.2 (0.3), 26.2 (3.7) -> 98.5 (0.4), 54.9 (6.8) -> 99.8 (0.1), 67.4 (3.5) -> 99.2 (0.2).
By steps per 4 s window (2 / 3 / 4+), V4half -> aid1.0:
30.0 (2.1) -> 98.8 (0.3), 27.6 (3.6) -> 99.5 (0.1), 59.7 (5.5) -> 99.2 (0.3).

Cost and no-regression (V4half -> aid1.0, mean over seeds):
- real still called walking: **0.7 % -> 1.0 %**; real still precision 64.0 -> 64.2 %.
- walking recall per real dataset: WearGait-PD 86.4 -> 86.1, CeTI 98.9 -> 98.5, Luo 97.7 -> 97.1,
  Lencioni 98.2 -> 98.6, KneE-PAD 71.3 -> 70.7, Marpino 97.4 -> 96.9, PAMAP2 92.3 -> 92.0, MHEALTH 100 -> 100.
- walking called stairs: Lencioni fast 0.6 -> 1.0 %, Luo FE 1.2 -> 1.7 %, WearGait-PD HurriedPace 1.1 -> 1.7 %.
- Luo stairs recall up/down 43.4/89.2 -> 41.5/88.0 %; precision up/down 85.9/69.4 -> 86.6/65.0 %.
- PAMAP2 stairs recall up/down 23.6/38.0 -> 23.1/43.7 %; precision up/down 25.0/35.4 -> 26.7/32.9 %.
- simulated transition event recall 78.1 -> 77.8 %; false events per hour (Camargo) 0.0 -> 0.0 (0 detected events
  in the evaluated streams; this is not proof of zero false events on real data).
- forest size 16,131 -> 15,855 nodes (fold-0 tree; per-variant values in the summary).

The full tables (all datasets, all metrics, mean and sd) are in `stepF\cv_aid\cv_aid_summary.md`; the one-screen
numbers-only summary requested for the owner is `stepF\cv_aid\owner_summary.md` (copied here in condensed form):

| metric | V4half | aid0.25 | aid0.5 | aid1.0 |
|---|---:|---:|---:|---:|
| Aid walking recall, % | 42.5 | 97.1 | 98.5 | 99.2 |
| Aid walking recall: walker / rollator / crutches, % | 27.9 / 61.0 / 35.8 | 94.8 / 99.6 / 96.7 | 97.3 / 99.9 / 98.1 | 98.6 / 99.9 / 99.0 |
| Real still called walking, % | 0.7 | 0.8 | 0.9 | 1.0 |
| Real still precision, % | 64.0 | 64.2 | 64.2 | 64.2 |
| Walking recall WearGait / CeTI / Luo / Lencioni, % | 86.4 / 98.9 / 97.7 / 98.2 | 86.6 / 98.7 / 97.7 / 98.6 | 86.4 / 98.9 / 97.0 / 98.6 | 86.1 / 98.5 / 97.1 / 98.6 |
| Walking recall KneE / Marpino / PAMAP2, % | 71.3 / 97.4 / 92.3 | 71.6 / 97.2 / 94.0 | 71.4 / 97.1 / 94.4 | 70.7 / 96.9 / 92.0 |
| walking->stairs Lencioni fast / Luo FE / WG hurried, % | 0.6 / 1.2 / 1.1 | 0.7 / 1.5 / 1.1 | 0.7 / 1.6 / 0.9 | 1.0 / 1.7 / 1.7 |
| Sim transition recall, % | 78.1 | 77.4 | 75.8 | 77.8 |
| False events / h (Camargo) | 0.0 | 0.0 | 0.0 | 0.0 |
| External 8 viewer personas walking recall, % | 43.3 | 44.8 | 44.0 | 43.3 |
| Forest nodes | 16,131 | 16,705 | 17,085 | 15,855 |

Best variant for the Section 4.4 check: **aid1.0**, chosen as the highest aid recall among the variants whose overall
real-still called-walking cost is within 1.0 point of V4half (0.7 -> 1.0).

### 4.4 Repeat G2's check on the best variant — FAIL (negative result)

Best variant aid1.0, final forest seed 0; the 8 viewer personas are external (never trained on). Walking recall per
persona, `old_14`..`old_21`:

| viewer persona | walking windows | called walking, % (V4half) | called walking, % (aid1.0, mean 3 seeds / seed 0) |
|---|---:|---:|---:|
| `old_14` early walker | 27 | 0.0 | 1.2 / 0.0 |
| `old_15` crutches | 13 | 100.0 | 94.9 / 92.3 |
| `old_16` later no-aid | 14 | 100.0 | 100.0 / 100.0 |
| `old_17` PWB crutches | 13 | 56.4 | 64.1 / 53.8 |
| `old_18` toe-touch walker | 25 | 6.7 | 12.0 / 8.0 |
| `old_19` NWB walker (leg held) | 2 | 0.0 | 0.0 / 0.0 |
| `old_20` static-spacer walker | 27 | 0.0 | 0.0 / 0.0 |
| `old_21` static-spacer crutches | 14 | 83.3 | 73.8 / 57.1 |

Feature medians of the walker viewers vs real still, compared with the G2 V4 cut-offs:

| feature | walker viewers (median) | real still (median) | G2 V4 cut-off |
|---|---:|---:|---:|
| `std_m` | 0.0562 | 0.0065 | 0.062 |
| `mean_m` | 0.9789 | 1.0013 | 1.015 |
| `ptp_m` | 0.4140 | 0.0447 | 0.315 |
| `jerk_m` | 0.6499 | 0.1208 | 0.731 |

Most common root splits of the new aid1.0 forest (seed 0): `hf_ratio <= 0.006` 3/20 trees, `mean_z <= 0.478` 2/20,
`ptp_m <= 0.152` 2/20, `ptp_m <= 0.279` 2/20, `mean_m <= 1.045` 1/20, `jerk_m <= 0.309` 1/20. Real still called
walking for aid1.0 is **0.9 %** (out-of-fold); real still precision 64.2 %.

**Answer:** No, the two ultra-slow walker personas (`old_14`, `old_20`) do **not** pass the still/walking cut-offs:
both are called still 0 % walking before and after; `old_18` improves from 6.7 % to 12.0 % (seed 0: 8 %). The external
8-persona mean is 43.3 % before and 43.3 % at aid1.0 (44.8 % at aid0.25). Real still stays low (0.7 -> 0.9 %), so the
cost is not the problem; the synthetic aid data simply does not transfer to these AB07-derived viewer personas.

### 4.5 Constraints and outputs — PASS

- No chip, library, protocol, class list, window length or export change; no `kneil_tinyml/` change; no model exported.
- Only the new `pipeline/aid_gait.py`, `pipeline/cv_aid.py` and this report are added; existing pipeline files were not
  modified.
- All outputs are under `KNEIL_results\v4\stepF\`; tests/logs in `cache\`; datasets read-only.
- The scripts print a version line first, write a log, save per persona/per run and can resume (existing stream or
  prediction file is loaded; `--force` regenerates).

## 5. Problems and open questions

1. **The external G2 check is negative.** The aid personas reach 99 % CV walking recall (held-out source people), but
   the 8 viewer walker/crutch personas from AB07 do not move: `old_14` and `old_20` remain 0 % walking, `old_18` only
   6.7 -> 12.0 %. This is not a lack of aid examples; it is a domain gap between the Camargo replay (smooth, measured
   IK) and the viewer's AB07 HTML generator (different frame, roughness and 4 s recomposition). The two targets are at
   the low-intensity end (std_m 0.046/0.075, mean_m 0.98/1.01), and the forest still routes them through the
   `mean_m`/`zcr`/`hf_ratio` still paths even though `ptp_m`/`jerk_m` are above the old cut-offs.
2. **Holding AB07 out of training does not fix it.** A diagnostic run with AB07 removed from all training folds and
   from the final model gave 32.6 % external walking recall at aid1.0 seed 0 vs 31.9 % in the main run; the failure is
   not AB07 leakage. The diagnostic folder was deleted; the log is `cache\cv_aid_ab07test.txt`.
3. **The 99 % aid recall is in-domain.** The held-out people are unseen, but the generator is the same for all 21
   people. It is evidence that the aid gait is learnable from the generator, not that it will work on real walker or
   crutch users. Step 6 (owner records real walker/crutch gait) is the only real validation, and the result above
   makes it more necessary.
4. **Generator assumptions** (all marked as assumptions): weight bearing is a gain on the dynamic implant signal
   (full 1.0, partial 0.8, toe-touch 0.55, NWB 0.25) and, for NWB, the right leg is held; step-to vs step-through is
   modelled by the forward distance per cycle and the stride timing; turns are a pelvis yaw ramp, not a curved path;
   pauses are irregular but generated; the stride template is the median of the usable measured strides from two
   level-ground trials per person; a band-limited 2-8 Hz roughness and a random mount yaw/pitch/roll were added to
   cover the G2 feature range and the per-person mount of `kneil_v1.sample_sensor`.
5. **Rule C / usable windows.** Every 4 s window has a rule C label. For training, walking windows with start/stop
   transients are included; still windows only when they are clean pauses (no step, <=10 % moving, no transient).
   Transition windows with 1 step remain labelled still in the audit but are not trained on; without this filter the
   still examples would contain large deceleration spikes.
6. **False events per hour** are 0.0 because no transition event was detected in the evaluated Camargo streams
   (n = 0); this is not a guarantee for real data.
7. **No recommendation** is made here (the task asks for numbers only in the owner summary); the owner decides whether
   to use the aid data, change the label rule, or wait for real walker/crutch recordings. The owner summary is at
   `stepF\cv_aid\owner_summary.md`.
