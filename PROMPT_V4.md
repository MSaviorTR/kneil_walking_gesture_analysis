# Task: add two stair datasets and build the V4 activity model

Read `CLAUDE.md` first. Work in the steps below; after each step show me the result and wait for my OK.

## Paths (confirmed 16 Nov 2026)
- Data: `G:\My Drive\Walking_Gesture_Datasets` (Google Drive, available offline; read in place, do not copy), including
  the two new folders `Luo et. al. 2020` and `Lencioni et. al. 2019`.
- Earlier results: `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results` (stage 2 output `virtual_implant/stage2/`, index
  CSVs, the stage 3 window cache `virtual_implant/stage3/stage3_windows.npz`, `kneil_dataset_v1_6.zip`,
  `dataset/ab*.zip`, `external/caicedo_implant_streams.npz`).
- Code: this workspace (`pipeline/`, `kneil_tinyml/`), git remote
  https://github.com/MSaviorTR/kneil_walking_gesture_analysis. Commit after each step and update `README.md`.

## Step A: run locally
Make `pipeline/` run on my PC: one `config.py` (or a JSON) with all paths, no Colab or Drive code, cache folder inside
the workspace. Smoke test: rebuild the chip feature library and repeat the Camargo validation for one subject (ab07):
calibrated |a| r about 0.93-0.98 per trial.

## Step B: inspect the new datasets (report before writing generators)
- **Luo et al. 2020** (Sci Data, doi 10.1038/s41597-020-0563-y): 30 young adults, 6 Xsens MTw IMUs at 100 Hz (wrist,
  both ankles, lower back, ...), outdoor surfaces: flat, stairs up, stairs down, slope up, slope down, grass, banked left,
  banked right, uneven stone; about 6 walks per surface; calibration trials included. Find: file layout, column names,
  units (acceleration m/s^2 or g? gyroscope rad/s or deg/s?), which sensor is where, how surfaces and trials are named.
- **Lencioni et al. 2019** (Sci Data, doi 10.1038/s41597-019-0323-z): 50 healthy people aged 6-72, motion capture at 60 or
  200 Hz; level walking at different speeds, toe/heel walking, stairs up and down; `SubjectX.mat` with Data and
  StandingData, MarkerVarName, KinFreq; Demo_Anthro.xlsx. Find: the marker names (knee and ankle markers, medial ones?),
  how speeds and stair directions are labelled, units.

## Step C: two new stage 2 generators (same output format as stage2.py: one npz per person + index CSV)
- **Luo:** the ankle IMU -> implant point with vimp (lever arm about 0.36 m like PAMAP2's ankle sensor; check the paper
  for the position), one frame per person (standing from the calibration trial, forward from flat walking). Labels: flat,
  grass, banked, uneven stone -> walking; stairs up / down -> stairs_up / stairs_down; slopes -> keep as 'slope_up' /
  'slope_down' (outside the chip classes for now). Keep the wrist signals for the smartwatch work.
- **Lencioni:** markers -> knee and ankle centres -> tibia frame -> implant point (like Caicedo in ext_datasets.py and the
  CeTI method in stage2.py; forward from the walking direction). Labels: walking with its speed class (slow, comfortable,
  fast), stairs_up, stairs_down; toe/heel walking outside the chip classes. Store the age.
- Checks: walking lean plausible; for Lencioni, the lean and features by speed class; run the full generators only after
  the subset looks right.

## Step D: V4 experiments (5-fold cross-validation by person, as stage3.py; nothing exported yet)
1. **8 classes:** sitting + standing -> **still** (class names: walking, stairs_up, stairs_down, still, lying,
   sit_to_stand, stand_to_sit, bed_transfer).
2. **Window length:** 2, 3, 4 and 5 s (hop 1 s). Check first that the C feature code works for any length (autocorrelation
   lags are in seconds) and that the training features equal the C features.
3. **Fast walking vs stairs** (my device problem): report how often walking is called stairs, by speed: Camargo
   treadmill speeds, WearGait-PD SelfPace vs HurriedPace, Lencioni slow/comfortable/fast, Caicedo speed bins, Luo flat.
   Test a **stairs evidence rule** (post-processing): stairs only if the forest vote share is above a threshold and k of
   the last n windows agree, otherwise walking; tune it in the cross-validation and report stairs recall and precision.
4. **Transitions as events:** sit-to-stand and stand-to-sit detected as events (a run of transition windows between still
   periods), direction from the run's majority class; event recall and false events per hour, on the simulated data,
   CeTI s01 (five sit-to-stands) and WearGait-PD TUG. Compare window lengths here too.
5. Variants: V3 recipe vs V3 + Luo + Lencioni, each with the window lengths above. Report per dataset, per class, per
   speed, plus model size (nodes). **Recommend, do not export.**

## Step E (only after I choose): chip changes and export
- Library: 8 classes; the window length from the model (`KNEIL_MODEL_WIN_S` in kneil_model_info.h, #error if the build
  disagrees, like the sampling rate); daily metrics: transitions from transition runs between still periods (direction
  from the run), **posture tracking** (after stand-to-sit = sitting until the next sit-to-stand) to estimate sitting and
  standing time, 'still' time, and the stairs rule if chosen. Update the daily summary format (version byte).
- Export V4: forest + tree (float), model info, test vectors, host test PASS, into `KNEIL_results/tinyml_final_v4_lp6`.
- Update the class table and the protocol version (2) in `prompts/PROMPT_firmware_KNEIL_live.md` and
  `prompts/PROMPT_gui_KNEIL_live.md` (keep their protocol sections identical).
