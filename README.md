# KNEIL walking and gesture analysis (V4 workspace)

Activity recognition for **KNEIL**, an implantable BLE sensor in the tibial insert of an articulating knee spacer
(two-stage revision for periprosthetic joint infection). The sensor has a 3-axis accelerometer (50 Hz, ±8 g) on an
nRF54L15. This repository holds the training pipeline (virtual implant from public gait datasets) and the on-chip
classifier library.

**For agents:** read [CLAUDE.md](CLAUDE.md) first (project context, rules, pitfalls already found), then
[PROMPT_V4.md](PROMPT_V4.md) (the current task, steps A-E). **Update this README after every change**: the status
table, the changelog and any path or file that changed.

## Current status

| Step (PROMPT_V4.md) | State |
|---|---|
| A: run `pipeline/` locally (config with paths, no Colab/Drive code) | **done** (waiting for owner's OK): C library + host test PASS; Camargo ab07 equals the Colab run |
| B: inspect Luo 2020 and Lencioni 2019 | not started (data downloaded, see below) |
| C: stage 2 generators for Luo and Lencioni | not started |
| D: V4 experiments (8 classes, window length, fast walking vs stairs, transition events) | not started |
| E: chip changes and V4 export | only after the owner chooses |

Deployed candidate: **model V3** (9 classes, 2 s windows). Summary in [docs/MODEL_V3_SUMMARY.md](docs/MODEL_V3_SUMMARY.md).
Open problem from the real-device test: fast walking is classified as stairs up/down; sitting and standing are confused.

## Repository layout

| Path | Content |
|---|---|
| `CLAUDE.md` | project context for Claude Code / agents |
| `PROMPT_V4.md` | the V4 task in steps with checkpoints |
| `pipeline/` | virtual implant and stages 1-3 (now run locally; written first for Colab) |
| `pipeline/config.py` | **all paths** (data, results, V4 output, cache, chip library, OpenSim model); each can be overridden by an environment variable of the same name, e.g. `KNEIL_DATA_ROOT` |
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
The library in the repo has no model inside (by design). The host test runs on a copy in `cache\` with the four V3
files from `KNEIL_results\tinyml_final_v3_lp6` added; to put V3 into the real library use `docs/add_v3_model.py`.

## Changelog

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
