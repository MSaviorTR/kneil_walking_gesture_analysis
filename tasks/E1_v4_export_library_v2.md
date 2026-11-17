# Task E1: export the V4 model and make the chip library v2.0

Branch: `agent/E1`, new from `main`. Read `AGENTS.md` first (it changed: step E output folders). Report:
`tasks/E1_report.md`. This task **may change `kneil_tinyml/`** (all files in it). It must not change anything else
listed in AGENTS.md. The firmware repository (`..\kneil_firmware`) is **not** part of this task: do not touch it.

## Owner's decision (17 Nov 2026, from docs/STEP_D_SUMMARY.md)
- **8 classes**, ids: 0 walking, 1 stairs_up, 2 stairs_down, 3 still, 4 lying, 5 sit_to_stand, 6 stand_to_sit,
  7 bed_transfer (same order as `cv_v4.CLASSES8`).
- **Window 4 s, hop 1 s**, 50 Hz, input low-pass 6 Hz (as V3).
- **V4half** training data (as in D1-D3), forest 20 trees x depth 10 plus the single-tree option, float thresholds.
- **Stairs rule**: a window predicted stairs_up or stairs_down stays stairs only if the vote share of the predicted
  class is >= 0.60; otherwise it becomes walking (`stairs_rule.apply_rule` with theta 0.6, k = n = 1).
- **Transition events by rule R1** of D3 (`transition_events.py`), counted once per event.

## Part A: export (`pipeline/export_v4.py`, version 1.0)
1. Train the forest and the single tree on **all** people (no CV), V4half, 4 s, 8 classes, seed 0, same settings as
   D2. Reuse `cv_v4.py` / `stage3_v4.py` functions; reuse the emlearn export of `stage3.export_final` (copy the logic,
   do not edit `stage3.py`).
2. Write to `KNEIL_results\v4\tinyml_final_v4_lp6\` (`config.out_dir('tinyml_final_v4_lp6')`): `kneil_model_forest.h`,
   `kneil_model_tree.h`, `kneil_model_info.h`, `kneil_test_vectors.h`, the joblib models, a JSON with the training
   counts per dataset and class, and the log. Then copy the 4 headers into `kneil_tinyml/include/` and
   `kneil_tinyml/tests/` as V3 did.
3. `kneil_model_info.h` gets, in addition to the V3 lines: `KNEIL_MODEL_WIN_S 4`, `KNEIL_MODEL_HOP_S 1`,
   `KNEIL_MODEL_N_CLASSES 8`, `KNEIL_MODEL_STAIRS_MIN_VOTE 0.60f`, `KNEIL_MODEL_NAME "V4half 4s"` and the dataset line.
4. Test vectors: 4 s windows (200 samples), at least one per class from the simulation, like V3's 27 vectors.

## Part B: library v2.0 (`kneil_tinyml/`)
1. `kneil_tinyml.h`: `KNEIL_LIB_VERSION "2.0"`; window length from the model: `KNEIL_WIN_N = KNEIL_MODEL_WIN_S *
   KNEIL_FS_HZ`, hop from `KNEIL_MODEL_HOP_S`. `#error` if `KNEIL_MODEL_WIN_S`, `KNEIL_MODEL_HOP_S` or
   `KNEIL_MODEL_N_CLASSES` is missing, or `KNEIL_MODEL_N_CLASSES != KNEIL_N_CLASSES` (8). New 8-class enum.
2. Classifier: after each window store `c->proba[8]` (forest: vote shares; single tree: what emlearn gives, say what in
   the report), `c->raw_class` (argmax), `c->vote` (share of the raw class). `kneil_classifier_push()` returns the class
   **after the stairs rule**. Keep the stride-period history.
3. Metrics, in this order per window: rule output -> events (unsmoothed) and posture state -> majority-of-3 smoothing
   (as V3, optional) -> minutes and the other counters.
   - **Events, R1, causal**: a run of sit_to_stand / stand_to_sit windows (runs separated by one other window merged)
     ends when 2 non-transition windows follow; it is counted when a `still` window lies within 3 windows before the run
     or within 3 windows after its end (so a count can come up to 3 s late). Direction = majority class of the run
     (tie: the first window's class). bed_transfer: same run rule, no `still` condition.
   - **Posture state** (splits the still minutes): unknown after reset; sitting after a stand_to_sit event; standing
     after a sit_to_stand event or any walking/stairs window; unknown after lying or a bed_transfer event. Still minutes
     go to sitting / standing / unknown by the state. This is an assumption (a missed event gives wrong minutes): say so in
     the README.
   - Seated tilt: mean sagittal tilt of still windows in the sitting state.
4. Daily summary **format 2**, 40 bytes, little-endian, packed:
   `uint8 format = 2; uint8 n_classes = 8; uint16 minutes_by_class[8]; uint16 minutes_sitting, minutes_standing,
   minutes_still_unknown; uint16 n_sit_to_stand, n_stand_to_sit, n_bed_transfer; uint16 sts_seconds_x10 (mean
   sit-to-stand run length); uint16 steps; uint16 cadence_x10; uint16 stairs_cadence_x10; int16 sit_tilt_x10`.
   `_Static_assert(sizeof(kneil_daily_summary_t) == 40)`.
5. Self-test and host test for the new vectors. `kneil_tinyml/README.md`: v2.0 section (classes, window, rule, events,
   posture, summary layout, RAM). Zephyr Kconfig/CMake: only what the change needs.

## Part C: Python twin and checks (`pipeline/metrics_ref.py` 1.0, `pipeline/check_step_e.py` 1.0)
`metrics_ref.py`: the same rule + R1 events + posture + summary in Python, for the PC app and for the checks.
`check_step_e.py` runs the C library through ctypes (rebuild the DLL from `kneil_tinyml/src`, like `run_step_a.py`).

## Acceptance checks (all results under `KNEIL_results\v4\stepE\E1\`)
1. Test run first with `$env:KNEIL_V4_OUT` set to your cache (`--max-people` small): export, headers build, host test.
2. Full export: forest and tree node counts (forest expected near 16.1 k nodes from D3), flash estimate in KB.
3. `tests/run_host_test.py`: `HOST TEST: PASS (both models)`.
4. C vs Python on raw streams (at least 10 simulation files, 10 Luo trials, 5 WearGait-PD walks, 3 CeTI recordings):
   per window raw class identical to the sklearn forest on the same features >= 99.9 %; the rule output identical to
   `stairs_rule.apply_rule(theta=0.6, k=1, n=1)` (100 %); list every mismatch with its vote shares.
5. Events: replay the D2 prediction streams of V4half 4 s seed 0 (8-class predictions + proba) through the C metrics
   (add a test entry point that takes class + proba, no features) and through `transition_events.py` R1: per source,
   event counts identical, except events within the last 3 windows of a stream (report them).
6. `metrics_ref.py` vs C: identical 40-byte summaries on the streams of check 4 (print 3 decoded examples).
7. `sizeof(kneil_classifier_t)` and `sizeof(kneil_metrics_t)` (V3: about 2.2 KB classifier); host time per window.
8. Sanity on the export (in-sample, so only a smoke test): Luo FE walking called stairs %, Lencioni fast walking called
   stairs %, with and without the rule.

## Not part of this task
The firmware repository, BLE protocol v2, the PC app, `PROMPT_*.md`, the V3 export and its folder (read-only).
Report anything in those that will need to change in the next task (E2), with file and line.
