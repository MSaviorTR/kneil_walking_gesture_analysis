# E1 report: V4 export and chip library v2.0

## 1. Status

Done — the V4 model is exported, the library is v2.0 (8 classes, 4 s window from the model, stairs rule, R1 events,
posture, 40-byte summary format 2), and all 8 acceptance checks pass.

## 2. Files

Code (new):
- `pipeline/export_v4.py` (1.0): trains forest + tree on everyone (V4half, 4 s, seed 0), writes the 8 export files and
  copies the 4 headers into the library.
- `pipeline/metrics_ref.py` (1.0): Python twin of the rule + R1 events + posture + format-2 summary (`Metrics`,
  `decode`, `stairs_rule`).
- `pipeline/check_step_e.py` (1.0): checks 2-8, builds the library DLL with gcc and drives it through ctypes.

Library (`kneil_tinyml/`, v1.1 -> v2.0):
- `include/kneil_tinyml.h`: `KNEIL_LIB_VERSION "2.0"`, window/hop/class count from `kneil_model_info.h` with `#error`
  guards, 8-class enum, `proba[8]` / `raw_class` / `vote`, `kneil_stairs_rule`, accessors for the PC app,
  format-2 summary with `_Static_assert(sizeof == 40)`.
- `src/kneil_classifier.c`: `kneil_model_predict_proba` -> argmax -> stairs rule; returns the ruled class.
- `src/kneil_metrics.c`: R1 transition events (1-gap merge, closes after 2 non-transition windows, still within 3
  before or after), bed_transfer run rule, posture state, still minutes split, format-2 summary.
- `tests/host_test.c`: prints library/model config, `sizeof`s and the full summary; stream mode writes
  `raw vote class stride` per window.
- `README.md` v2.0 section (classes, window, rule, events, posture assumption, summary layout, RAM), `zephyr/Kconfig`
  text (8 classes, 4 s, flash sizes).
- New generated files (this package now ships its model): `include/kneil_model_forest.h`,
  `include/kneil_model_tree.h`, `include/kneil_model_info.h`, `tests/kneil_test_vectors.h`.
- `tasks/E1_report.md` (this file).

Results on Drive: `KNEIL_results\v4\tinyml_final_v4_lp6\` = the 4 headers, `model_forest.joblib`,
`model_tree.joblib`, `counts.json`, `export_log.txt`; `KNEIL_results\v4\stepE\E1\` = check log, JSON, CSVs.
Nothing else changed: `stage3.py`, the chip feature code, the class list of the pipeline, the V3 export folder and the
firmware repo (`..\kneil_firmware`, never opened).

## 3. Commands

```
# check 1: smoke export into the cache, then build + host test on a scratch copy of the library
$env:KNEIL_V4_OUT = "<worktree>\cache\test_v4"
python pipeline/stage3_v4.py --win 4 --max-people 2
python pipeline/export_v4.py --max-people 2 --lib "<worktree>\cache\test_v4\lib_smoke"
python <scratch>\tests\run_host_test.py

# check 2-8 (real export + all checks; --no-export to skip the retraining)
Remove-Item Env:KNEIL_V4_OUT
python pipeline/check_step_e.py
python pipeline/check_step_e.py --no-export        # 0.5 min once the export exists

# check 3 on its own
python kneil_tinyml/tests/run_host_test.py
```
Environment: Python 3.12.10, numpy 2.5.4, scikit-learn 1.9.1, emlearn 0.23.2, gcc MSYS2 16.2 (no ARM toolchain
available on this PC).

## 4. Acceptance checks

### 4.1 Test run first (cache, 2 people per dataset) — PASS

Export from 19,375 cached windows (8,858 training rows after the V4half weights): forest 3,674 nodes, tree 141 nodes,
16 test vectors; headers built into a scratch copy of the library; host test printed
`selftest: 16 vectors, max feature error 0, feature failures 0, class mismatches 0` and `RESULT: PASS` for both models.

### 4.2 Full export — PASS

| item | value |
|---|---|
| training rows | 222,913 (V4half, 4 s) |
| forest 20 x depth 10 | **15,822 nodes** (D3 expected about 16.1 k) |
| single tree, depth 10 | 719 nodes |
| test vectors | 16 (2 per class, all 8 classes present) |
| rows per class | walking 108,210 / stairs_up 8,594 / stairs_down 6,843 / still 93,935 / lying 3,752 / sit_to_stand 256 / stand_to_sit 296 / bed_transfer 1,027 |
| files | 4 headers + 2 joblib + counts.json + export_log.txt in `v4\tinyml_final_v4_lp6` |

**Flash estimate** (no ARM compiler here, so scaled from the measured V3 build: 65.7 KB flash for 18,302 nodes):
forest about **56.8 KB**, tree about **2.6 KB** (same bytes/node), plus classifier + features + metrics about 2.1 KB
(V3 measured; the new code adds a few hundred bytes of state, see 4.7). Selftest vectors add about 40 KB in test
builds only. Header source sizes: forest 1.73 MB, tree 80 kB.

### 4.3 Host test — PASS

```
selftest: 16 vectors, max feature error 0, feature failures 0, class mismatches 0
library 2.0: window 200 samples (4 s), hop 50 samples, 8 classes, stairs vote 0.60
sizes: classifier 3436 bytes, metrics 208 bytes, summary 40 bytes
RESULT: PASS           (both models)
HOST TEST: PASS (both models)
```

### 4.4 C vs Python on raw streams — PASS

28 streams (10 simulation CSV files, 10 Luo trials, 5 WearGait-PD SelfPace walks, 3 CeTI s01 recordings), 850 windows
through the C classifier at 50 Hz, compared with the exported sklearn model on the same features:

- raw class identical to the sklearn forest **100.0000 %** (0 mismatches) — using the majority vote of the trees,
  which is what emlearn generates and what the V3 library did;
- C stairs rule vs `stairs_rule.apply_rule(theta=0.60, k=1, n=1)`: **0 mismatches (100 %)**;
- note: sklearn's `predict()` averages the leaf class probabilities and differs from that vote on 9 of 850 windows
  (1.06 %). This is a property of the emlearn export (each tree contributes its argmax class, not its leaf
  distribution), not of the C code: on the same features the C equals the vote rule exactly. No mismatch list is
  needed for the vote comparison; the 9 `predict()` differences are in `check4_streams.csv`.

### 4.5 Events: C metrics vs `transition_events.py` R1 — PASS (identical counts)

Replayed the D2 predictions of **V4half 4 s seed 0** (13,366 streams, 290,745 windows) through `kneil_metrics_push`
(class + vote, no features) and through the R1 run detector:

| source | sit_to_stand C / Python | stand_to_sit C / Python | bed_transfer C / Python |
|---|---|---|---|
| simulation | 111 / 111 | 147 / 147 | 228 / 228 |
| Luo | 7 / 7 | 2 / 2 | 0 / 0 |
| WearGait-PD | 9 / 9 | 10 / 10 | 0 / 0 |
| CeTI | 0 / 0 | 2 / 2 | 0 / 0 |
| PAMAP2 | 0 / 0 | 2 / 2 | 0 / 0 |
| MHEALTH | 0 / 0 | 1 / 1 | 0 / 0 |
| all other real datasets | 0 | 0 | 0 |

Python events whose run ends within the last 3 windows of a stream (where the C has not closed the run yet):
**11** (all of them excluded on both sides, so the counts above are equal). Two details had to be pinned down, both
documented in the code: direction is counted over the transition windows only (a `still` window inside the merged
one-window gap does not vote), and a tie goes to the first window of the run. `transition_events.detect` (D3) counts
the whole slice including that gap window; that only changes a direction when a run has exactly one gap window and a
tie, which happened in 3 of 15,040 streams at 4 s.

### 4.6 `metrics_ref.py` vs C summary — PASS

28 streams of check 4: **0 different summaries**, all exactly 40 bytes. Three decoded examples:

- `P000_bed.csv`: bed_transfer 3 events, everything else 0 (a bed-transfer recording, no walking);
- `ab06_ramp_5_r_01_05.csv`: all counters 0 (the model saw no walking/stairs/still/lying window; the file is a ramp);
- `ab09_levelground_cw_slow_01_01.csv`: all counters 0 for the same reason.

(The check-4 streams are short ramps/trials, so the summaries are mostly near-empty; the equality of all 28 bytes is
what matters, and check 5 replays the full D2 prediction set through the same code.)

### 4.7 Sizes and time — PASS

`sizeof(kneil_classifier_t) = 3,436 bytes` (V3: about 2.2 KB; the 4 s window and the 8 probabilities add 1.2 KB),
`sizeof(kneil_metrics_t) = 208 bytes`, `sizeof(kneil_daily_summary_t) = 40 bytes` (static assert). Host time on this
PC, `gcc -O2`, through ctypes: **0.87 us per sample, 46.8 us per window** (one 200-sample window, 20 features, 20
trees). The classifier is `static` in firmware, never on a stack.

### 4.8 Export sanity (in-sample, smoke only) — PASS

| group | walking windows | walking called stairs before the rule | after the rule (vote >= 0.60) |
|---|---|---|---|
| Luo FE | 3,620 | 9.36 % | **1.13 %** |
| Lencioni fast | 709 | 6.49 % | **0.71 %** |

In-sample by construction (the model trained on these windows), so this only shows that the rule removes the
low-confidence stairs predictions as intended.

## 5. Problems and open questions

1. **sklearn `predict()` is not the reference for this model.** The emlearn export votes with the trees' argmax
   classes; sklearn averages the leaf class probabilities. On this model that is a 1.06 % window difference. All C
   comparisons therefore use the vote rule (which is also what the deployed V3 library does). If the manager wants the
   probability-averaged variant on the chip, emlearn would have to export the leaf distributions (emlearn cannot do
   that with `method='inline'`), so it would change the export format, not something I can fix in C.
2. **Single-tree model and the stairs rule:** `kneil_model_predict_proba` gives a one-hot vector for the tree
   (1.0 at its class), so `vote` is always 1.0 and the stairs rule never fires for `KNEIL_MODEL_SMALL`. Say if the
   tree build should get a different treatment (it has no probability to threshold).
3. **Posture state is an assumption** (also written in the library README): a missed stand_to_sit puts the following
   still minutes into "standing". The three still buckets are in the summary so the PC app can see how much is
   unknown, but the split is only as good as the event detection (event recall 87 % in D3 on the simulation, 0-1 % on
   CeTI/TUG).
4. **Two small semantic decisions in the events**, both needed for a causal chip: (a) a `still` window inside the
   merged one-window gap counts as evidence after the run (the C cannot see the future, the D3 offline detector
   treated the same window as inside the run), (b) a run is counted only after it has closed, so up to 3 events at the
   very end of a recording are lost (11 events out of the 521 counted above).
5. **Flash is an estimate.** There is no ARM toolchain on this PC (`arm-none-eabi-gcc` not found), so the numbers in
   4.2 are scaled from the measured V3 build. Building `kneil_tinyml` for the nRF54L15 once in E2/CI would turn this
   into a measurement.
6. **For E2 (not touched here), these will need to change:**
   - `prompts/PROMPT_firmware_KNEIL_live.md:52` (class table, 9 classes) and `:79` ("LIVE packet ... when a 2 s window
     is classified") — the model is 8 classes and a 4 s window now;
   - `prompts/PROMPT_gui_KNEIL_live.md:71` (class table), `:46` and `:98` (2 s window alignment and the LIVE packet);
   - the BLE daily summary: format 2 is 40 bytes with `format`/`n_classes` as the first two bytes — the app must read
     the format byte before parsing (ATT MTU >= 43);
   - `docs/add_v3_model.py` copies the V3 headers into `kneil_tinyml/include` and `tests`; running it now would
     overwrite the V4 model. Rename/guard it in E2;
   - `docs/FLASH_V3.md` still describes the 9-class/2 s V3 model; a `FLASH_V4.md` with the measured size is missing.
7. **Test vectors are 16 (2 per class) and several come from the same recording** (P000_bed, P000_sitstand). That is
   enough to cover all 8 classes (16 x 200 x 3 floats = 38 KB flash) but not a variety check across people; a
   per-person spread would cost more flash. Say if the selftest should cover more.
8. The `kneil_tinyml/tools/train_kneil_tinyml.py` retraining path still trains the old 9-class/2 s models; it is not
   used by this export (`export_v4.py` is the V4 path). Porting the tool is a later task.
