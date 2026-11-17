# kneil_tinyml v2.0: on-device activity classifier and daily mobility metrics (nRF54L15)

## v2.0 (17 November 2026) — this package
Owner decision after step D (`docs/STEP_D_SUMMARY.md`): **8 classes, 4 s windows every 1 s**, 50 Hz, 6 Hz input
low-pass, **V4half** training data, forest 20 x depth 10 plus the single tree (float thresholds), **stairs evidence
rule** vote >= 0.60, **transition events counted once per event** (rule R1), **daily summary format 2 (40 bytes)**.

- **This package now contains its model**: `include/kneil_model_forest.h`, `include/kneil_model_tree.h`,
  `include/kneil_model_info.h` and `tests/kneil_test_vectors.h` come from
  `KNEIL_results/v4/tinyml_final_v4_lp6` (written by `pipeline/export_v4.py`). The library builds and self-tests on
  its own; the V3 model in `KNEIL_results/tinyml_final_v3_lp6` is untouched (read-only).
- **Window and hop come from the model**: `kneil_model_info.h` defines `KNEIL_MODEL_WIN_S` (4) and
  `KNEIL_MODEL_HOP_S` (1); `KNEIL_WIN_N = WIN_S * FS`, `KNEIL_HOP_N = HOP_S * FS`. A build stops with `#error` if
  `KNEIL_MODEL_WIN_S`, `KNEIL_MODEL_HOP_S` or `KNEIL_MODEL_N_CLASSES` is missing or if the class count is not 8.
- **Classes (8)**: 0 walking, 1 stairs_up, 2 stairs_down, 3 still (sitting and standing together), 4 lying,
  5 sit_to_stand, 6 stand_to_sit, 7 bed_transfer.
- **Stairs rule** (`kneil_stairs_rule`, applied in `kneil_classifier_push`): a window predicted stairs_up or
  stairs_down stays stairs only if the vote share of the predicted class is >= `KNEIL_MODEL_STAIRS_MIN_VOTE` (0.60);
  otherwise it becomes walking. `c.raw_class`, `c.vote` and `c.proba[8]` keep the values before the rule.
  The forest gives vote shares (20 trees); the single tree gives a one-hot vector (1.0 for its class), so the rule
  never fires for the tree model.
- **Transition events (rule R1, causal)**: a run of sit_to_stand / stand_to_sit windows (a single other window between
  two transition windows keeps the run together) ends when 2 non-transition windows follow; it is counted when a
  `still` window lies within 3 windows before the run or within 3 windows after its end (a count can come up to 3 s
  late). Direction = majority class of the run; a tie goes to the first window. `bed_transfer` uses the same run rule
  without the still condition.
- **Posture state** splits the still minutes: unknown after reset, sitting after a stand_to_sit event, standing after a
  sit_to_stand event or any walking/stairs window, unknown after lying or a bed_transfer event. This is an
  assumption: a missed event puts the following still minutes in the wrong bucket.
- **Daily summary format 2, 40 bytes** (little-endian, packed): `uint8 format=2; uint8 n_classes=8;
  uint16 minutes_by_class[8]; uint16 minutes_sitting, minutes_standing, minutes_still_unknown; uint16 n_sit_to_stand,
  n_stand_to_sit, n_bed_transfer; uint16 sts_seconds_x10; uint16 steps; uint16 cadence_x10; uint16 stairs_cadence_x10;
  int16 sit_tilt_x10`. `_Static_assert` checks the size.
- **RAM**: classifier about 3.3 KB (200-sample window, 4 s magnitude history, 8 probabilities), metrics about 0.2 KB.
  Host test prints the exact `sizeof` values.
- **Behaviour per window** (`kneil_metrics_update`): rule output -> events and posture (unsmoothed) -> majority-of-3
  smoothing (`KNEIL_SMOOTH`, one window of delay) -> minutes and the other counters.

Model V3 (`KNEIL_results/tinyml_final_v3_lp6`, 9 classes, 2 s) stays as deployed history; the v1/v1.1 sections below
describe it.

## v1.1 (November 2026)
- **Optional input low-pass.** `tools/train_kneil_tinyml.py --lowpass 6` trains on signals filtered by a causal
  2nd-order Butterworth at 6 Hz and writes `KNEIL_MODEL_LOWPASS_HZ` into `kneil_model_info.h`; the classifier
  then applies the same filter to every incoming sample (C and Python filters agree to 5e-7 g). Default 0 = off.
  Reason: the simulated training data cannot contain fast (> 6 Hz) motion, and features that depend on it transfer
  poorly from simulation to real sensors (Camargo comparison, Nov 2026).
- **Smoothed daily metrics.** `kneil_metrics_update()` uses a majority vote of 3 consecutive windows (a window
  changes only if both neighbours agree on another class), with one window of delay. Switch: `KNEIL_SMOOTH`
  (Zephyr: `CONFIG_KNEIL_TINYML_SMOOTH`, default y).

The device classifies one accelerometer window every 1 s and adds the result to a daily summary that is sent over BLE
instead of raw data (v2.0: 4 s window, 40-byte summary).

Input: one sample at a time, in g, device frame: **x anterior, y subject's left, z superior**
(upright standing gives about (0, 0, +1 g)), at **50 Hz** (the rate the model was trained for).

## Results (v1, synthetic data only)
| | forest (default) | single tree (`KNEIL_TINYML_MODEL_SMALL`) |
|---|---|---|
| Flash, Cortex-M33 `-Os` (model + classifier / features + metrics) | 65.7 KB / 2.1 KB | 2.9 KB / 2.1 KB |
| RAM (classifier + metrics state) | 2.2 KB | 2.2 KB |
| macro-F1, 9 classes, unseen virtual patients, 50 Hz | 0.884 (accuracy 92 %) | 0.867 |
| C vs Python agreement, all 9,626 windows | 99.0 % (C uses majority voting; scores above use that rule) | 100 % |
| Sit/stand events detected (unseen patients) | 75 % / 68 % | 72 % / 60 % |

Sampling rate barely matters for classification (forest: 0.885 at 100 Hz, 0.887 at 50 Hz, 0.885 at 25 Hz).
These numbers come from synthetic data. Real accuracy will be lower until real recordings are added
(earlier experiment: synthetic-only 0.65 vs real-trained 0.87 on real shin data).

## Folder
```
include/kneil_tinyml.h        public API (only header the application needs)
include/kneil_model*.h        generated by emlearn (do not edit); kneil_model_info.h = training rate
src/kneil_features.c          20 features per window (also used for training, so firmware = training)
src/kneil_classifier.c        streaming buffer, model call, stride period
src/kneil_metrics.c           daily counters and the 34-byte summary
src/kneil_selftest.c          test vectors check (test builds only)
tests/                        host test (gcc) and generated test vectors
tools/train_kneil_tinyml.py   retraining and export; tools/gen_test_vectors.py
zephyr/                       module.yml, CMakeLists.txt, Kconfig (nRF Connect SDK / Zephyr module)
reports/kneil_tinyml_report.png
PROMPT_vscode.md              prompt for an AI coding assistant in VS Code
```

## Use in firmware
```c
#include "kneil_tinyml.h"

static kneil_classifier_t clf;   /* v2.0: about 3.3 KB: keep static, not on a stack */
static kneil_metrics_t day;

void kneil_app_init(void) { kneil_classifier_init(&clf); kneil_metrics_reset(&day); }

/* call from a work item / thread (not an ISR) with each FIFO batch, already in g and in the device frame */
void kneil_app_on_samples(const float (*a)[3], int n)
{
	for (int i = 0; i < n; i++) {
		int cls = kneil_classifier_push(&clf, a[i][0], a[i][1], a[i][2]);
		if (cls >= 0) kneil_metrics_update(&day, &clf, cls);   /* once per second */
	}
}

/* if samples were lost (FIFO overflow): kneil_classifier_init(&clf); never glue non-contiguous data */

void kneil_app_end_of_day(void)
{
	kneil_daily_summary_t s;          /* format 2: 40 bytes, packed, little-endian */
	kneil_metrics_summary(&day, &s);
	/* store and/or notify s over BLE (ATT MTU >= 43 or split) */
	kneil_metrics_reset(&day);
}
```

## Add to an nRF Connect SDK project
1. Copy this folder to `<app>/modules/kneil_tinyml`.
2. In the application `CMakeLists.txt`, before `find_package(Zephyr ...)`:
   `list(APPEND ZEPHYR_EXTRA_MODULES ${CMAKE_CURRENT_SOURCE_DIR}/modules/kneil_tinyml)`
3. `prj.conf`: `CONFIG_KNEIL_TINYML=y` and `CONFIG_FPU=y` (`CONFIG_FPU_SHARING=y` if several threads use floats).
   Optional: `CONFIG_KNEIL_TINYML_MODEL_SMALL=y`, `CONFIG_KNEIL_TINYML_SELFTEST=y` (test builds).
4. The build stops with an error if `CONFIG_KNEIL_TINYML_FS_HZ` differs from the training rate.
   The math functions used are `sqrtf`, `atan2f`, `fabsf` (picolibc, the NCS default, provides them).

## Tests
- Host: `sh tests/run_host_test.sh [stream.txt]` must print `RESULT: PASS` for both models.
- Target: build with `CONFIG_KNEIL_TINYML_SELFTEST=y`, call `kneil_selftest()` at boot and log the result.
  Pass = `n_class_mismatch == 0` and `n_feature_fail == 0`.

## Retrain (for example with your volunteer recordings)
CSV files with columns `time_s, acc_x_g, acc_y_g, acc_z_g, activity` at 100 Hz, device frame, labels as in
the synthetic dataset (`walking, stairs_up, stairs_down, sitting, standing, sit_to_stand, stand_to_sit,
lying_supine, lying_side, rolling, sit_up, lie_down`); the file name starts with a subject id and `_`.
```
pip install emlearn scikit-learn scipy pandas
python tools/train_kneil_tinyml.py --data <kneil_dataset_v1_6> --compare            # rates x models
python tools/train_kneil_tinyml.py --data <kneil_dataset_v1_6> --extra <real_csv_dir> --fs 50
sh tests/run_host_test.sh
```
`--fs` accepts any integer rate (for example 52 for ST sensors); then set `CONFIG_KNEIL_TINYML_FS_HZ` to the same value.

## Limits (v1)
- Trained on synthetic data only; sitting vs standing (F1 0.82 / 0.74) and the two sit/stand transitions are the weakest classes.
- The event counter misses about 30 % of sit/stand events but rarely invents them (3 % of patients over-counted).
- Steps and cadence come from the stride period (autocorrelation over 4 s); not yet checked against real step counts.
- The accelerometer frame must be mapped correctly (sensor axes to x anterior, y left, z superior), or accuracy collapses.

