# KNEIL walking and gesture analysis (V4 workspace)

Activity recognition for **KNEIL**, an implantable BLE sensor in the tibial insert of an articulating knee spacer
(two-stage revision for periprosthetic joint infection). The sensor has a 3-axis accelerometer (50 Hz, ±8 g) on an
nRF54L15. This repository holds the training pipeline (virtual implant from public gait datasets) and the on-chip
classifier library.

**For agents:** read [CLAUDE.md](CLAUDE.md) first (project context, rules, pitfalls already found), then
[PROMPT_V4.md](PROMPT_V4.md) (the current task, steps A-E). **Update this README after every change**: the status
table, the changelog and any path or file that changed.

**Two agents:** Claude Code is the manager (writes tasks, reviews, merges, keeps this README). A worker agent
(OpenCode with DeepSeek V4.1 Flash) follows [AGENTS.md](AGENTS.md) and the task files in [tasks/](tasks/README.md); it
works in its own worktree `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_agent` on branches `agent/<task id>`.

## Current status

| Step (PROMPT_V4.md) | State |
|---|---|
| A: run `pipeline/` locally (config with paths, no Colab/Drive code) | **done** (waiting for owner's OK): C library + host test PASS; Camargo ab07 equals the Colab run |
| B: inspect Luo 2020 and Lencioni 2019 | **done** (waiting for owner's decisions): [docs/STEP_B_REPORT.md](docs/STEP_B_REPORT.md) |
| C: stage 2 generators for Luo and Lencioni | **done** (waiting for owner's OK): full run, 0 flagged; [docs/STEP_C_NOTES.md](docs/STEP_C_NOTES.md) |
| D: V4 experiments (8 classes, window length, fast walking vs stairs, transition events) | **in progress** via the worker agent, see [tasks/README.md](tasks/README.md): D0 merged (window builder for 2-5 s + V4 data, V3 regression passed), D1 merged (8-class CV x window x data), D2 merged (3 seeds, V4half, stairs rule v1), D3 merged (transition events, stairs rule v2). **Done; waiting for the owner's choice**: [docs/STEP_D_SUMMARY.md](docs/STEP_D_SUMMARY.md) (recommended: 8 classes, 4 s, V4half, stairs vote share >= 0.6) |
| E: chip changes and V4 export | owner chose 8 classes, 4 s, V4half, stairs vote >= 0.6 (17 Nov). **E1 merged** (export + library v2.0, host test PASS); **E2 merged** ([kneil_firmware](https://github.com/MSaviorTR/kneil_firmware), main `718301d`, pushed): library 2.0 + V4 in the firmware, BLE protocol v2, PC app v2. **Next: owner flashes and tests on the device** |

Deployed candidate: **model V3** (9 classes, 2 s windows). Summary in [docs/MODEL_V3_SUMMARY.md](docs/MODEL_V3_SUMMARY.md).
Open problem from the real-device test: fast walking is classified as stairs up/down; sitting and standing are confused.

## Repository layout

| Path | Content |
|---|---|
| `CLAUDE.md` | project context for Claude Code / agents |
| `PROMPT_V4.md` | the V4 task in steps with checkpoints |
| `pipeline/` | virtual implant and stages 1-3 (now run locally; written first for Colab) |
| `pipeline/config.py` | **all paths** (data, results, V4 output, cache, chip library, OpenSim model); each can be overridden by an environment variable of the same name, e.g. `KNEIL_DATA_ROOT` |
| `pipeline/v4_readers.py` | readers for Luo (`data.mat` tables via h5py, one table at a time; raw CSVs) and Lencioni (`SubjectN.mat` strides) |
| `pipeline/inspect_step_b.py` | step B inspection of Luo and Lencioni (`--luo-people 1,2 --lencioni-max 3` for a quick test) |
| `docs/STEP_B_REPORT.md` | step B findings and the decisions needed for step C |
| `pipeline/stage2_v4.py` | step C generators: Luo (raw CSV -> vimp) and Lencioni (markers -> periodised strides); output `KNEIL_results\v4\stage2\<dataset>\*.npz` + `stage2_index_<dataset>.csv`; V4 labels appended to `stage2.LABELS` |
| `pipeline/check_step_c.py` | chip features of the new stage 2 output by label, surface, speed class |
| `pipeline/check_periodise.py` | Camargo: one repeated gait cycle vs real windows (is periodising Lencioni safe?) |
| `pipeline/diag_luo_lean.py`, `diag_luo_intensity.py`, `diag_lever_arm_camargo.py` | step C diagnostics (Luo lean, Luo intensity vs lever arm, lever-arm truth on Camargo) |
| `docs/STEP_C_NOTES.md` | step C subset results and open decisions |
| `pipeline/stage3_v4.py` | (D0) window builder for any window length (2-5 s, hop 1 s) incl. Luo/Lencioni and metadata (`rec`, `surface`, `speed_abs`, `speed_rel`, `adult`, `role`); output `KNEIL_results\v4\stepD\windows\windows_W{2,3,4,5}s.npz` |
| `pipeline/cv_v4.py` | (D1) 5-fold CV by person: 8 classes, window 2-5 s, variants V3recipe / V4data; results `KNEIL_results\v4\stepD\D1\` (`D1_summary.md`) |
| `pipeline/stairs_rule.py` | (D2) causal stairs evidence rule (vote share >= theta and k of the last n windows), tuned inside the CV |
| `pipeline/transition_events.py` | (D3) sit-to-stand / stand-to-sit events from window predictions vs per-sample truth; false events per hour |
| `docs/STEP_D_SUMMARY.md` | step D comparison and recommendation |
| `pipeline/features_ref.py`, `test_features_window.py` | (D0) numpy reference of the 20 C features; C vs reference check at 2-5 s (all PASS) |
| `pipeline/run_step_a.py` | step A smoke test: rebuild the C feature library + host test with V3; Camargo validation of one subject |
| `pipeline/vimp.py` | rigid-body transfer shank IMU -> implant point, per-person tibia frame |
| `pipeline/stage01.py` | readers, plausibility rule, Camargo validation |
| `pipeline/stage2.py` | implant-site data per person (npz + index CSV) for WearGait-PD, KneE-PAD, Marpino, PAMAP2, MHEALTH, CeTI |
| `pipeline/stage3.py` | chip features, 5-fold cross-validation by person, report, export |
| `pipeline/ext_datasets.py` | marker-based tibia signals (Caicedo) |
| `pipeline/camargo_replay.py`, `pipeline/kneil_v1.py` | replay of measured joint angles in the KNEIL MuJoCo model |
| `kneil_tinyml/` | chip library v1.1 (C features, classifier, daily metrics, self-test, Zephyr module, training tools); no model inside |
| `notebooks/` | the Colab notebooks of stages 1-3, for reference only |
| `prompts/` | firmware and PC-app prompts (class table and BLE protocol) |
| `docs/` | V3 summary, V3 flashing guide, `add_v3_model.py` |

## Data and results (not in git)

All data and earlier results are on Google Drive, synced **offline** to this PC. Read them in place; do not copy them.

| What | Path |
|---|---|
| Dataset root | `G:\My Drive\Walking_Gesture_Datasets` |
| Earlier results (V1-V3; never overwrite) | `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results` |
| Stage 2 output, index CSVs | `KNEIL_results\virtual_implant\` (`stage2\`, `stage2_index_*.csv`) |
| Stage 3 window cache | `KNEIL_results\virtual_implant\stage3\` |
| Simulated data | `KNEIL_results\kneil_dataset_v1_6.zip`, `KNEIL_results\dataset\ab*.zip` |
| Caicedo implant streams | `KNEIL_results\external\caicedo_implant_streams.npz` |
| V3 chip model | `KNEIL_results\tinyml_final_v3_lp6\` |
| New: Lencioni et al. 2019 | `Walking_Gesture_Datasets\Lencioni et. al. 2019\` (`All_Subjects\Subject1-50.mat`, `Demo_Anthro.xlsx`) |
| New: Luo et al. 2020 | `Walking_Gesture_Datasets\Luo et. al. 2020\` (`input data_SD\input data_SD\1..30\*.txt.csv`, `*.mtb`, `data.mat` 3.8 GB) |
| Other datasets | `Camargo et. al. 2021`, `WearGait-PD`, `PAMAP2`, `MHEALTH`, `CeTI-Age-Kinematics`, `MarpinoWalking-dataset`, `har70`, `harth`, ... in the dataset root |

New V4 results go to `KNEIL_results\v4\<step>\` (`config.out_dir()` refuses any other place); the final V4 chip
export will go to `KNEIL_results\tinyml_final_v4_lp6`. V1-V3 results are only read.

Local scratch: `cache\` in the workspace (git-ignored, safe to delete): Camargo trials extracted from the zips (deleted
after each subject), the OpenSim model `cache\opensim\subject01_simbody.osim` (downloaded once by `kneil_v1.fetch`),
and the host-test copy of the chip library.

## Environment

Windows 11, Python 3.12 (system install `C:\Users\Mehdi\AppData\Local\Programs\Python\Python312`, no venv): numpy,
scipy, pandas 3, scikit-learn, matplotlib, openpyxl, emlearn 0.23.2 with setuptools, mujoco 3.17, **mat-io** (import
name `matio`, reads the Camargo MATLAB tables; pulls in h5py). gcc from MSYS2 UCRT64 on the PATH (builds the C feature
library used in training via ctypes; the DLL goes to `kneil_tinyml/tools/`, git-ignored). Git for Windows 2.56.

## How to run

```
python pipeline/run_step_a.py --part 1            # C feature library + host test with the V3 model (about 10 s)
python pipeline/run_step_a.py --part 2 --subject ab07   # Camargo validation of one subject
```
From v2.0 (step E1) the library contains the V4 model; host test: `python kneil_tinyml/tests/run_host_test.py`
(must print `HOST TEST: PASS (both models)`). `run_step_a.py` part 1 and `docs/add_v3_model.py` are for the V3 library
only: do not run `add_v3_model.py` now (it would overwrite the V4 model).

## Changelog

- **2026-11-24 L1 result (flexion, loosening):** seated knee angle from tibia tilt works (1-point foot-flat calibration,
  6 Hz LP, 0.05 g gate: P95 error < 4 deg in MuJoCo); daily-life knee flexion from the tibia alone does not (Camargo
  R^2 0.01, sit-to-stand shows only 28 of 96 deg). Loosening by vibration needs kHz sampling (out of reach at 50 Hz);
  standing coronal tilt drift is detectable from about 3 deg (same-day MDC95 1.5-2.8 deg), sagittal only from 4-10 deg.
  Candidate SUMMARY v3 fields: 12 bytes (not implemented). Two of the report's DOIs are wrong (noted in the report).

- **2026-11-24 Owner's decision on S1:** keep V4 as it is (stairs classes stay stairs only; ramps not added).

- **2026-11-24 S1 result (stairs + ramps):** merging all ramps into going up/down (M-all) raises up/down recall
  (up 14 -> 49 %, down 32 -> 71 %) but 13 % of real walking becomes up/down (Luo level walking 41 %, Luo walking
  recall 98 -> 55 %). Merging only steep ramps (>= 8 or 10 deg) changes almost nothing (steep real ramps 18-38 %).
  Ramps look like walking at the tibia. Nothing exported; owner decides. Next: L1 (Gemini).

- **2026-11-24 Physiotherapist input + stairs/ramps idea.** Tasks: S1 (Gemini) tests merging stairs and ramps into
  going up / going down (V4 has never seen ramps; no export until the owner decides); T1 (DeepSeek) a home therapy mode
  on the watch: seated knee extension / bend with the angle from the RAW stream, rep counter, voice prompts through the
  ES8311 + NS4150B speaker, SD log of flexion trends (no chip or protocol change); L1 (Gemini, next) feasibility of knee
  flexion and spacer-loosening metrics from the implant accelerometer.

- **2026-11-24 Viewer 1.6, own repo:** the viewer is also published at https://github.com/MSaviorTR/kneil_viewer
  (viewer/, the 3 pipeline modules it imports, kneil_tinyml C source, the 50 pre-built motions under `bundled_data/`).
  Viewer changes are made here first and copied there. No CAD or meshes made from it. The viewer now also looks for
  `<repo>/bundled_data`, so a fresh clone runs without G:.

- **2026-11-24 Viewer 1.5 camera fix:** the interactive 3D window could tilt down but not up (the model is Y-up, MuJoCo's
  mouse camera assumes Z-up). The interactive model is now wrapped in a Z-up root body; the PNG/Blender renders are
  unchanged. Exe rebuilt.

- **2026-11-24 Viewer V3e (Gemini):** `viewer/launcher.py` 1.0, a motion picker (50 motions by source, search, speed,
  CAD and see-through switches; open 3D viewer, save PNG, Blender clip). `viewer/build_exe.ps1` builds a one-folder
  exe `dist\KNEIL_viewer\KNEIL_viewer.exe` (259 MB) that runs without Python, G: or sims_html. The bundle holds meshes
  made from the owner's CAD: local only, never in git.

- **2026-11-24 G3 merged (aid-gait domain gap)**: not noise, roughness, mount or AB07. The gap is kinematic: the old
  viewer personas have a restricted/locked knee (small swing: std_z 0.066 g, corr_xz -0.18) and a pause after every
  stride; the A1 generator uses full healthy knee swing in 4-8-stride bursts. Scaling the old personas' dynamic
  acceleration x1.5 moves old_14 from 0 % to 100 % walking. Real slow walking sits closer to A1 on swing features but
  closer to the old personas on zcr/hf_ratio; neither is validated for walker or stiff-knee gait. Also found: a
  2.2 g blend spike at stand->walk in `aid_gait.py`. Recording checklist for the owner in `tasks/G3_report.md` 4.5.

- **2026-11-24 A1 merged (aid gait, rule C)**: 462 aid personas from 21 Camargo people (AB07 out). CV by person,
  3 seeds: aid walking recall 42.5 % (V4half) -> 97.1 / 98.5 / 99.2 % (aid weight 0.25 / 0.5 / 1.0); cost small
  (real still called walking 0.7 -> 1.0 %, walking recall per dataset within 0.6 points, walking->stairs +0.4-0.6
  points). **But the external test fails**: the 8 viewer personas (old HTML generator, AB07) stay at 43 % walking;
  the ultra-slow walkers old_14/old_20 stay 0 %. A domain gap between the two synthetic sources; the 99 % is
  in-domain only. Not exported; no chip change. Real walker/crutch recordings (plan step 6) decide.

- **2026-11-24 Viewer V3d merged**: owner keeps the implant CAD; the right leg is now a closed see-through shell
  (Blender alpha 0.22-0.62 with a rim, MuJoCo alpha 0.28) with the femoral component, insert, tibial component and the
  KNEIL chip + axes visible inside; ~1.2 s per 1920x1080 frame. Bones (Body46/Body32) off; `INCLUDE_BONES` in
  `viewer/implant_cad.py` switches them on.

- **2026-11-24 Viewer V3c merged**: the owner's implant CAD (femoral component, spacer insert, tibial component from
  `sims_html\j_a_j_model.obj`, read at run time, never committed) on the right knee in Blender and MuJoCo
  (`viewer/implant_cad.py`; anterior = -Y_cad found from the flange, groove, tray cut-out and PS post). The KNEIL
  implant point falls inside the insert. Femoral-insert overlap: max 1.9 mm over a gait cycle, 6.9 mm at 103 deg
  (generic OpenSim knee kinematics). Open: full-body view shows a gap at the knee; owner decides whether the CAD stays.

- **2026-11-23 Owner chose label rule C** for walking-aid gait (>= 2 steps and >= 50 % moving per 4 s window).
  Task A1 (DeepSeek): aid-gait personas from 21 Camargo people (AB07 kept out as the independent viewer test set) and
  the CV experiment (V4half + aid gait at 0.25 / 0.5 / 1.0). Output folder `KNEIL_results\v4\stepF`.

- **2026-11-23 G2 merged (walker gait diagnosis)**: walker personas (0.20-0.23 m/s, 33-41 % pauses, 1-2.7 steps per
  4 s) fall just under the forest's still/walking cut-offs (ptp_m 0.315 g, jerk_m 0.73 g/s, std_m 0.062 g) because
  no training walking is slower than ~0.5 m/s, yet their intensity is 4-8x above real still -> fixable with aid-gait
  training data. Crutch personas (0.41-0.44 m/s) are already `walking` 77-100 %. Proposed label rule: >= 2 steps in
  4 s (B) or >= 2 steps and >= 50 % moving (C). Public aid-gait data with shank signals: scarce (GAITEX, NC-ND).

- **2026-11-23 Plan: walker / crutch gait called still** (`docs/PLAN_walker_gait.md`): 1 diagnose (Gemini, G2),
  2 generate aid-gait personas, 3 CV experiment (DeepSeek), 4 owner decides, 5 export V4.1 (model only; same classes,
  window and protocol), 6 owner records walker/crutch gait with the truth keys (the real validation).

- **2026-11-23 Viewer V3b merged**: floor, chair, stairs and ramp fitted to the stance-foot trajectories (median
  foot-to-surface error 0.03-1.26 cm on all 48 non-bed motions, was up to 55 cm); Blender figure with arms (decorative),
  spacer and implant; every motion labelled in-sample or out-of-sample. **Out-of-sample finding**: the 8 spacer-period
  personas (walker / crutches, recomposed AB07 strides, not in training) -> ultra-slow walker gait called `still`
  96-100 %. Ramps were never trained (person AB07 in-sample) -> steep ramp called stairs 75 %.

- **2026-11-23 Motion viewer V3 merged** (Gemini): `viewer/kneil_viewer.py` (MuJoCo, 50 motions: 38 of the old
  HTML viewer, 8 Camargo replays incl. ramps and walking speeds, 4 generator walks), the chip library v2.0 decision
  per 4 s window (C = Python on 3 motions), headless `--render`, Blender 5.2 renders (`viewer/blender_render.py`,
  0.35 s/frame). Findings (in-sample, indication only): ultra-slow walker personas -> `still` 96-100 %; steep ramps
  -> stairs 75 %; stairs rule turns half of synthetic healthy stairs-up into walking. Open: props not aligned with the
  feet, Blender figure without arms, in-sample labels (task V3b).

- **2026-11-23 Watch W6 merged and pushed** (kneil_smartwatch main `545d31b`): all 9 findings of Gemini's review
  fixed (console crash, CONTROL queue lock and order, centrals switched off before on, scan/connect races, LIVE
  without CCCD dropped, buffer sizes, page lifecycle). Host tests 75 + 35 + 155 PASS (manager rerun); build +1.5 kB.
  Not yet on hardware. Open (cosmetic): Diagnostics still lists phone/sensor roles in KNEIL mode.

- **2026-11-23 Gemini review G1 merged**: 9 findings in the watch's KNEIL code (1 crash: the `status` console
  command in KNEIL mode reads past a 3-entry array; CONTROL queue race; Guder-sensor scan can stay idle after leaving
  KNEIL mode; ...). Manager confirmed F1-F3 and F6 in the code. Fixes -> DeepSeek (W6); the MuJoCo/Blender viewer
  -> Gemini (V3). The watch should not be used in KNEIL mode with the `status` command until W6 is merged.

- **2026-11-23 Gemini G0 passed** (model: Gemini 4 Neon in Antigravity). Git, Python and the wait loop work, but
  only outside Antigravity's sandbox: the worktree's `.git` lives in `kneil_v4_workspace` and the data are on `G:`.
  The owner must allow those two paths (or "Always Allow" `git` and the wait script) so Gemini can work unattended.

- **2026-11-23 Second worker: Gemini in Antigravity.** Worktree `..\kneil_v4_gemini`, order file
  `tasks/NEXT_gemini.md`, branches `gemini/<id>`; `GEMINI.md` points it to `AGENTS.md` (now with a worker table);
  `tasks/wait_for_task.ps1` 1.1 takes `-Worker gemini`. DeepSeek keeps `tasks/NEXT.md` and `kneil_v4_agent`. Rule:
  no two workers on the same files at the same time. First Gemini task: G0, setup check only.

- **2026-11-20 Overview figure polished** (V2b + V2c): same numbers and text; uniform panel letters, roomier
  virtual-implant panel, status band no longer cut by its boxes. `check_layout()` now enforces a 20 mil (6 px at
  300 dpi) minimum gap between texts, to card edges and to drawn boxes, and fails the run otherwise.

- **2026-11-20 Overview figure merged** (task V2 + fix): `docs/figures/OVERVIEW_kneil_v4.{png,svg,pdf}`, one 16:9
  slide (data, virtual implant, chip, live view, key numbers, walking per dataset, stairs trade-off, window length,
  status). Same numbers as A1-A4 (`make_figures.py` 1.1, `--only overview`); layout checked in code; SVGs now
  reproducible; PDF with embedded TrueType. People count: a dot = one CV group with a 4 s window (312 real + 82 sim.);
  the V3 "265 people" counted Marpino's 78 recording files as people (CV uses 5 Marpino recording groups);
  WearGait-PD is 109 in V3 and V4.

- **2026-11-18 Figures merged** (task V1 + fix): nine figures in `docs/figures/` (PNG 300 dpi + SVG), captions,
  sources and limits in `docs/FIGURES.md`, script `pipeline/make_figures.py` (reads the step D results, ~8 s).
  **Correction** in `docs/STEP_D_SUMMARY.md`: its rule tables were the tuned rule (theta 0.5); at the chip's 0.6:
  Luo FE walking-called-stairs 1.2 %, Lencioni fast 0.6 %, Luo stairs up recall/precision 43 / 86 %, down 89 / 69 %,
  PAMAP2 up 24 / 25 %, down 38 / 35 %. Simulated still -> walking 32 % comes from the Camargo replay's standing windows.

- **2026-11-17 Watch W5 merged and pushed** (kneil_smartwatch main `6096726`). Third hardware test: W4 passed value+1
  as the start of `ble_gattc_disc_all_dscs()` (NimBLE wants the value handle), so find-info 23..22 failed (rc=3).
  Fixed, host-tested (107 KNEIL checks), and every NimBLE call in `kneil_central.c` checked against the ESP-IDF 6.1
  headers (all PASS). Lesson: BLE API misuse is invisible to host tests; each new BLE call needs a header check.

- **2026-11-17 Watch W4 merged and pushed** (kneil_smartwatch main `787af53`). Second hardware test: link stable after
  W3, but all three subscriptions wrote the last CCCD of the service (handle 33, SUMMARY), so LIVE/INFO never arrived.
  Now each characteristic is searched in its own handle range, first CCCD (host test with the real layout: 22/30/33;
  fails on the old rule). New log lines: `subscribed <name>: value <h> cccd <h>` and `first LIVE packet`.

- **2026-11-17 Watch W3 merged and pushed** (kneil_smartwatch main `16d6579`). First hardware test: the watch found
  KNEIL-7AD1 by name but dropped the link ("KNEIL service not found"): one byte of the hand-typed service UUID was
  swapped (0x94 for 0x49). Now one UUID array in `kneil_state.c` plus a host test against the protocol text (85 KNEIL
  checks, fails on the old byte). Other protocol constants checked: all PASS. Waiting for the owner's re-flash.

- **2026-11-17 Watch W1/W2 merged and pushed** to github.com/MSaviorTR/kneil_smartwatch (main `864632a`).
  Builds with ESP-IDF **v6.1** (EIM install; use `C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1`, not
  `export.ps1`); Korhan's unchanged code also builds with 6.1. +15 kB image, +960 B DIRAM. Old pages pixel-identical in
  the simulator; default mode dispatches exactly as upstream. Host tests 75 + 35 + 76 PASS. Not yet run on hardware.
  Possible upstream issue (not fixed, tell Korhan): the face may not refresh until the first swipe (LVGL has no active
  tile before the first scroll). `dependencies.lock` is rewritten by 6.1 builds; not committed.

- **2026-11-17 W1 code accepted** (watch, branch `agent/W1` in `..\guder_watch_agent`, not merged, not pushed).
  KNEIL mode, page and console commands; protocol component = KNEIL firmware `kneil_proto` (verbatim). Manager reran
  the host tests: 75 + 35 existing PASS, 76 new KNEIL checks PASS (no ASan on MSYS2). Review fix: page 1 rebuilt
  safely when the mode changes at run time; `apply_roles()` back to upstream. **Not compiled for the watch yet**:
  task W2 (build, sizes, screenshots) waits for ESP-IDF v5.5.5 on this PC.

- **2026-11-17 Watch task W1 given.** The Güder lab watch (ESP32-S3, ESP-IDF 5.5.5;
  github.com/korhankaradere/guder_watch, no license) is cloned to `..\guder_watch` (remote `upstream`); the owner's
  public copy is `origin` = https://github.com/MSaviorTR/kneil_smartwatch (Korhan's history as is, no license added). Worker worktree `..\guder_watch_agent`, branch `agent/W1`: a new BLE mode "KNEIL
  device" that shows the forest's live decisions (class after the rule, raw class and vote, posture, events, daily
  summary) without saving data; the existing watch functions must stay unchanged.

- **2026-11-17 E2 merged** (worker + one fix; manager reran host, protocol and PC tests: PASS / PASS / 38 OK).
  Firmware repo (main `718301d`, pushed): library 2.0 + V4 model, `kneil_live.c` on the library's rule,
  events and daily metrics (FW 0.5.0), LIVE v2 (22 B), SUMMARY characteristic (41 B), commands Q/Z, bridge and PC app
  v2 with v1 back-compatibility; v2 still windows with unknown posture get their own confusion column. Measured
  (NCS 3.1.0): KNEIL live forest V4 386.7 kB flash / 51.6 kB RAM (V3: 409.7 / 48.7); forest symbol 157 kB (V3 194 kB);
  single tree 238.9 kB. Workspace: prompts updated, `docs/add_v3_model.py` refuses to overwrite V4. Not tested on
  hardware yet; PC app needs `pip install pyserial` for a live session. Worker told STOP.

- **2026-11-17 Step E2 given** (owner approved firmware and BLE changes). Task `tasks/E2_firmware_protocol_v2.md`:
  library v2.0 into the firmware repo, `kneil_live.c` on the library's rule/events/metrics, LIVE v2 (22 bytes: ruled
  class, raw class, event flags, posture), new SUMMARY characteristic (40-byte format 2), commands Q/Z, PC app v2 with
  v1 back-compatibility, measured flash/RAM with NCS v3.1.0. The worker uses a firmware worktree
  `..\kneil_firmware_agent` (branch `agent/E2`); the manager's clone `..\kneil_firmware` is for review and merge.

- **2026-11-17 E1 merged** (worker; manager reran the host test: PASS both models). V4 model in
  `KNEIL_results\v4\tinyml_final_v4_lp6` and now inside `kneil_tinyml/` (the library ships its model from v2.0):
  forest 15,822 nodes, tree 719; 222,913 training rows. Library v2.0: classifier 3,436 B RAM, metrics 208 B, summary
  format 2 = 40 B. C = sklearn tree vote on 850 windows (100 %); stairs rule = Python (100 %); R1 events C = Python on
  290,745 replayed windows (end-of-stream runs excluded). **Flash: the worker's 57 KB estimate is wrong** (scaled from
  the V1 build); from the V3 forest (18,900 nodes, about 192 KB) expect **about 160 KB** for the V4 forest; to be
  measured in the firmware build. Known limits: the single-tree build has no vote share, so the stairs rule never acts
  there; posture split (sitting / standing / unknown) depends on event detection; `docs/add_v3_model.py` would now
  overwrite the V4 model (do not run it).

- **2026-11-17 Step E started.** Owner's choice: 8 classes, window 4 s / hop 1 s, V4half, stairs rule "vote share
  >= 0.6", transition events by rule R1. Task E1 (`tasks/E1_v4_export_library_v2.md`): V4 export to
  `KNEIL_results\v4\tinyml_final_v4_lp6`, `kneil_tinyml` v2.0 (window from the model with a build check, events,
  posture state, 40-byte summary format 2), Python twin `metrics_ref.py`. AGENTS.md: step E output folders allowed;
  a task may allow `kneil_tinyml/` changes. The firmware repo is cloned read-only next to this one
  (`..\kneil_firmware`) for E2.

- **2026-11-16 D3 merged; step D summary.** Transition events: simulation event recall 87 / 80 / 77 / 64 % at
  2 / 3 / 4 / 5 s, false events per hour <= 1 from 4 s; CeTI s01 and TUG unusable as event truth (postures 0.1-0.3 s;
  labeller truth). Stairs rule v2 (F0.5): at 4-5 s it becomes "vote share >= 0.5-0.6"; Luo walking-called-stairs
  (flat) 17.5 % today -> 2.8 % (V4half 4 s + rule). Recommendation in `docs/STEP_D_SUMMARY.md`; step E waits for the owner.

- **2026-11-16 D2 merged** (worker; all numbers mean over 3 seeds). Window files v1.1 with `stream` ids
  (`stepD\windows_v11`). Seed noise: walking recall sd 0-3 points on big datasets, 5-8 on PAMAP2. V4half (new data at
  half weight) sits between V3recipe and V4data (2 s walking: KneE-PAD 64.3 / 58.4 / 57.4, WearGait-PD 85.0 / 81.5 /
  81.0, Luo 80.2 / 84.9 / 86.6). Stairs rule v1 (F1-tuned) picks almost always theta 0.30 with no evidence window:
  walking-called-stairs falls 20-30 % relative at 2 s, stairs recall -2 to -5 points; at 3-5 s it barely acts.
  Next: D3 (transition events, rule v2 with F0.5).

- **2026-11-16 D1 merged** (worker; one seed, so small datasets are uncertain by +-12 points). 8 classes, CV by person.
  V3 regression: same folds/rows/weights; predictions agree 90.8 % (forest-to-forest level; V3 sklearn version unknown).
  Main measured effects (V3recipe 2 s -> V4data 5 s): Luo stairs_up recall 50 -> 81 % (precision 40 -> 59 %), Luo
  stairs_down 84 -> 96 % (27 -> 47 %); walking called stairs: Lencioni fast 11.9 -> 3.0 %, Luo flat 18.3 -> 6.5 %,
  WearGait-PD HurriedPace 8.3 -> 5.2 %. Costs: KneE-PAD and WearGait-PD walking -4 to -7 points with V4data at 2 s;
  simulated still 58 -> 49 % at 5 s. Stairs precision stays low (PAMAP2 ~20 %). Next: D2.

- **2026-11-16 D0 merged** (worker). `stage3_v4.py` builds windows for 2/3/4/5 s: 334,291 / 318,602 / 304,349 /
  290,745 windows (incl. Luo 51,086 and Lencioni 8,253 at 2 s). Regression against the V3 cache at 2 s: same counts,
  labels and groups for all 9 old datasets; 18 features bit-identical, the 2 tilt features within 2 float32 ULP
  (`atan2f` of Colab's glibc vs MSYS2) — accepted. C features vs numpy reference: all 20 PASS at 2-5 s (manager reran).
  Next: D1 (8-class CV x window length x V3/V4 data).

- **2026-11-16 Step D setup.** Added `AGENTS.md` (rules for the worker agent), `tasks/README.md` (task board) and task
  D0 (window-length loaders `pipeline/stage3_v4.py`, numpy reference of the C features, regression against the V3
  window cache). Worker worktree `..\kneil_v4_agent` on branch `agent/D0`.

- **2026-11-16 Step C (full)** (`stage2_v4 1.1`). Owner decisions: Luo lever arm 0.26 m; Lencioni stairs test only
  (`role` column). Full run: Luo 30 people / 3,420 trial-legs / 51,086 windows (7,670 stairs), Lencioni 50 people /
  3,230 stride-legs; 0 flagged, 0 failures. Output `KNEIL_results\v4\stage2\` + `stage2_index_{Luo,Lencioni}.csv`.
  Note for step D: `stage3.load_stage2` reads only `KNEIL_results\virtual_implant`; the V4 indexes are in `KNEIL_results\v4`.

- **2026-11-16 Step C (subset)** (`stage2_v4 1.0` + checks). Generators for Luo and Lencioni written and tested on
  Luo 1-2 and Lencioni 1-3 (output in `cache\test_v4`, logs copied to `KNEIL_results\v4\stepC\subset_test`).
  Findings: periodising one gait cycle is safe for walking windows of 2-5 s (Camargo, 3 people), not proven for stairs;
  the lean rule must apply to level walking only; Luo walking is ~50 % too intense with the 0.36 m lever arm — Camargo
  shows the true lever arm sits 0.04-0.08 m above the lowest-intensity point, which puts Luo near 0.22-0.28 m.
  Tip for agents: set `$env:KNEIL_V4_OUT` to a folder in `cache\` for test runs; the generators skip people already done.

- **2026-11-16 Step B** (`inspect_step_b 1.0`, `v4_readers 1.0`). Inspected both new datasets in full; report in
  `docs/STEP_B_REPORT.md`. Key facts: Luo has **shank** sensors 5 cm above the ankle (fixed serial map), surfaces in a
  `Surface` column, raw CSV = signal, `data.mat` = 6 Hz low-passed copy; Lencioni holds **single strides** (not
  continuous trials), no speed labels, lateral tibia markers only, 21 of 50 are children. Step C waits for decisions.

- **2026-11-16 Step A** (`stage01 1.5`, `stage3 1.3`, `config 1.0`, `run_step_a 1.0`). Pipeline runs locally:
  new `pipeline/config.py` holds every path; Colab code removed (Drive remount, `/content` paths, copies of Drive
  files to a local disk: `stage01.local_copy` now returns the path unchanged, logs are written directly).
  `camargo_replay` keeps the OpenSim model in `cache\opensim`. Installed `mat-io` (+ h5py).
  Smoke test (log: `KNEIL_results\v4\stepA\step_a_log.txt`):
  - C feature library rebuilt with gcc; C vs Python 6 Hz low-pass max difference 5.2e-7 g; host test with the V3
    model PASS for forest and tree (27 vectors, max feature error 3.8e-6, 0 class mismatches).
  - Camargo ab07, 12 trials (4 treadmill, 4 level ground, 4 stair): calibrated |a| r median 0.965 (treadmill
    0.96-0.97, stair 0.98-0.99, level ground 0.71-0.92); no calibration 0.878; no transfer 0.271. Identical to the
    Colab run (max difference 2e-14). Two level-ground trials (ccw normal 0.71, ccw slow 0.75) are below the 0.93-0.98
    range in Colab too: a property of these trials, not of the port; not yet explained.

- **2026-11-16** Repository created from the V4 workspace (code as delivered from the Colab work, unchanged).
  Added this README and `.gitignore`. Data paths in `PROMPT_V4.md` corrected to `G:\My Drive\Walking_Gesture_Datasets`.
