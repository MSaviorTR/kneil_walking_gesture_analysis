# Task V3 Report (worker gemini)

## 1. Status
done

## 2. Files
- `viewer/kneil_viewer.py` (added: MuJoCo 3D viewer, 50 motions, real `kneil_tinyml` v2.0 C library via ctypes, interactive + headless `--render` / `--frames` / `--list` / `--summary-table` / `--verify-c`)
- `viewer/export_motion.py` (added: exports per-frame MuJoCo body poses, implant triad, scene objects, and V4 forest decisions to JSON under `cache/viewer/`)
- `viewer/blender_render.py` (added: headless Blender 5.2 Eevee 1920x1080 studio renderer using `bpy` only)
- `viewer/README.md` (added: usage, keyboard controls, aliases, Blender workflow)
- `tasks/V3_report.md` (added: this report)

## 3. Commands
```powershell
git switch -c gemini/V3 main
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py --list
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py walk_healthy --render cache/viewer/render_walk_healthy.png --t 10.0
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py --verify-c
# 6 headless --render PNGs (walk_healthy, walk_fast, stairs_up, ramp_up, sit_to_stand, bed_transfer):
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py walk_fast --render cache/viewer/render_walk_fast.png --t 10.0
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py stairs_up --render cache/viewer/render_stairs_up.png --t 10.0
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py ramp_up --render cache/viewer/render_ramp_up.png --t 6.5
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py sit_to_stand --render cache/viewer/render_sit_to_stand.png --t 7.5
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py bed_transfer --render cache/viewer/render_bed_transfer.png --t 38.0
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py --summary-table --summary-json cache/viewer/summary_all.json
# Part C: Blender export + headless 1920x1080 Eevee renders
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/export_motion.py walk_healthy --t0 8.0 --max-s 3.0 --fps 25 --out cache/viewer/blender_walk_healthy.json
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P viewer/blender_render.py -- cache/viewer/blender_walk_healthy.json cache/viewer/blender_walk_healthy --step 1 --samples 16
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/export_motion.py walk_fast --t0 8.0 --max-s 2.0 --fps 25 --out cache/viewer/blender_walk_fast.json
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/export_motion.py stairs_up --t0 8.0 --max-s 2.0 --fps 25 --out cache/viewer/blender_stairs_up.json
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/export_motion.py sit_to_stand --t0 4.0 --max-s 3.0 --fps 25 --out cache/viewer/blender_sit_to_stand.json
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P viewer/blender_render.py -- cache/viewer/blender_walk_fast.json cache/viewer/blender_walk_fast --step 1 --samples 16
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P viewer/blender_render.py -- cache/viewer/blender_stairs_up.json cache/viewer/blender_stairs_up --step 1 --samples 16
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P viewer/blender_render.py -- cache/viewer/blender_sit_to_stand.json cache/viewer/blender_sit_to_stand --step 1 --samples 16
```

## 4. Acceptance checks

### Check 1: Part A — audit of the old HTML viewer (`KNEIL motion viewer.html`) — **PASS**

#### A.1 Motions in the old HTML viewer
Measured count: **38 motions** in 4 groups (not 23). Every trial stores 20 3D points at **50 Hz** (`pelvis`, `hip_{r,l}`, `knee_{r,l}`, `ankle_{r,l}`, `toe_{r,l}`, `heel_{r,l}`, `chest`, `head`, `imu`, `shoulder_{r,l}`, `elbow_{r,l}`, `hand_{r,l}`) + implant 3x3 orientation `AX` at 50 Hz, projected onto a 2D canvas. Signals plotted: `x anterior [g]`, `y left [g]`, `z superior [g]` (at **100 Hz**, optional dashed `lf` low-pass on groups 1–3 only), `knee flexion [deg]` (50 Hz), and on group 1 only `shank IMU |omega| [rad/s]: real vs replay`.

| # | Group / probable source | Name | Dur (s) | Env | Labels |
|---|---|---|---|---|---|
| 0 | Camargo AB07 (pipeline v1.3) | Treadmill walking, 0.50 m/s (slow): real motion | 16.0 | treadmill | walking |
| 1 | Camargo AB07 (pipeline v1.3) | Treadmill walking, 1.20 m/s (normal): real motion | 16.0 | treadmill | walking |
| 2 | Camargo AB07 (pipeline v1.3) | Treadmill walking, 1.55 m/s (fast): real motion | 16.0 | treadmill | walking |
| 3 | Camargo AB07 (pipeline v1.3) | Level-ground walking with a turn: real motion | 23.8 | floor | standing, walking |
| 4 | Camargo AB07 (pipeline v1.3) | Stairs up and down, 10 cm steps: real motion | 15.2 | stairs | stairs_up, stairs_down, standing, walking |
| 5 | Camargo AB07 (pipeline v1.3) | Stairs up and down, 18 cm steps: real motion | 15.9 | stairs | stairs_up, stairs_down, standing, walking |
| 6 | Caicedo 2020 (Vicon markers) | Older adult 0.60 m/s (subject 26, SPPB 8.0) | 8.5 | floor | walking |
| 7 | Caicedo 2020 (Vicon markers) | Older adult 0.96 m/s (subject 14, SPPB 10.0) | 5.2 | floor | walking |
| 8 | Caicedo 2020 (Vicon markers) | Older adult 1.04 m/s (subject 29, SPPB 10.0) | 4.8 | floor | walking |
| 9 | Caicedo 2020 (Vicon markers) | Older adult 1.09 m/s (subject 22, SPPB 12.0) | 4.8 | floor | walking |
| 10 | Caicedo 2020 (Vicon markers) | Older adult 1.15 m/s (subject 22, SPPB 12.0) | 4.5 | floor | walking |
| 11 | Caicedo 2020 (Vicon markers) | Older adult 1.25 m/s (subject 35, SPPB 11.0) | 3.7 | floor | walking |
| 12 | Caicedo 2020 (Vicon markers) | Older adult 1.45 m/s (subject 24, SPPB 12.0) | 3.8 | floor | walking |
| 13 | Caicedo 2020 (Vicon markers) | Older adult 0.99 m/s (subject 5, SPPB 8.0) | 3.8 | floor | walking |
| 14 | Spacer personas (AB07 strides) | Your protocol, early: walker | 30.0 | floor + aid | standing, walking |
| 15 | Spacer personas (AB07 strides) | Your protocol: crutches | 16.2 | floor + aid | standing, walking |
| 16 | Spacer personas (AB07 strides) | Your protocol, later: no aid | 17.1 | floor | walking |
| 17 | Spacer personas (AB07 strides) | Partial weight-bearing: crutches | 16.6 | floor + aid | standing, walking |
| 18 | Spacer personas (AB07 strides) | Toe-touch: walker | 30.0 | floor + aid | standing, walking |
| 19 | Spacer personas (AB07 strides) | Non-weight-bearing: walker (leg held) | 30.0 | floor + aid | standing, walking |
| 20 | Spacer personas (AB07 strides) | Static spacer, partial: walker | 30.0 | floor + aid | standing, walking |
| 21 | Spacer personas (AB07 strides) | Static spacer, as tolerated: crutches | 17.5 | floor + aid | standing, walking |
| 22 | Synthetic v1.6 (`kneil_v1.py`) | Walking: Healthy older adult (1.10 m/s) | 20.0 | floor | walking |
| 23 | Synthetic v1.6 | Sit/stand: Healthy older adult (2.6 s) | 16.0 | chair | sitting, sit_to_stand, standing, stand_to_sit |
| 24 | Synthetic v1.6 (`kneil_v1.py`) | Walking: Limp, severity 0.8 (0.78 m/s) | 20.0 | floor | walking |
| 25 | Synthetic v1.6 | Sit/stand: Limp, severity 0.8 (3.8 s) | 18.7 | chair | sitting, sit_to_stand, standing, stand_to_sit |
| 26 | Synthetic v1.6 (`kneil_v1.py`) | Walking: Locked knee (static spacer, 0.71 m/s) | 20.0 | floor | walking |
| 27 | Synthetic v1.6 | Sit/stand: Locked knee (static spacer, 4.1 s) | 19.8 | chair | sitting, sit_to_stand, standing, stand_to_sit |
| 28 | Synthetic v1.6 | Stairs up: Healthy older adult (riser 19 cm) | 20.0 | stairs | stairs_up |
| 29 | Synthetic v1.6 | Stairs down: Healthy older adult (riser 14 cm) | 20.0 | stairs | stairs_down |
| 30 | Synthetic v1.6 | Stairs up (step-to): Locked knee (riser 14 cm) | 19.2 | stairs | stairs_up, standing |
| 31 | Synthetic v1.6 | Stairs down (step-to): Locked knee (riser 14 cm) | 17.5 | stairs | stairs_down, standing |
| 32 | Synthetic v1.6 | Stairs up: Limp, severity 0.4 (riser 17 cm) | 20.0 | stairs | stairs_up |
| 33 | Synthetic v1.6 | Stairs down: Limp, severity 0.4 (riser 16 cm) | 20.0 | stairs | stairs_down |
| 34 | Synthetic v1.6 | Stairs up (step-to): Limp, severity 0.8 (riser 16 cm) | 21.5 | stairs | stairs_up, standing |
| 35 | Synthetic v1.6 | Stairs down (step-to): Limp, severity 0.8 (riser 16 cm) | 19.6 | stairs | stairs_down, standing |
| 36 | Synthetic v1.6 | Bed: Healthy older adult (bed 49 cm) | 53.9 | bed | lying_supine, rolling, lying_side, sit_up, sitting, lie_down |
| 37 | Synthetic v1.6 | Bed: Locked knee (static spacer, bed 46 cm) | 64.3 | bed | lying_supine, rolling, lying_side, sit_up, sitting, lie_down |

#### A.2 Fact-check against `CLAUDE.md`
- **Device frame**: Matches (`x` anterior, `y` left, `z` superior; `det(AX) = +1.0`; standing reads ~`(0, 0, +1 g)`, e.g. Trial 23 standing mean `(+0.047, +0.055, +1.008) g`).
- **Implant point**: `CLAUDE.md` states **2.5 cm below knee centre, 5 mm anterior**. Caicedo trials (6–13) place it **3.0 cm below, 0 mm anterior** (`(-0.1, -0.1, -30.5) mm` measured, and stated in `cond`). Synthetic v1.6 and Camargo trials include random mounting jitter (`sample_sensor()`): e.g. Trial 0 `(+1.3, +1.4, -26.9) mm`, Trial 14 `(+3.9, -1.2, -20.4) mm`, Trial 22 `(+4.8, -2.4, -30.4) mm`.
- **Sampling rate**: Kinematics are 50 Hz (`fk=50`), but embedded `acc` is **100 Hz (`fa=100`)**, not 50 Hz, and the 16 synthetic v1.6 trials have no `lf` 6 Hz low-pass trace at all.
- **Missing classifier strips**: The JS code has rendering support for `T.preds` and Caicedo `cond` text explicitly advertises *"Strips under the activity band: what the on-device model says each second"*, but `preds` is `None` in **all 38 trials**.
- **Decorative upper body**: Trunk and arms are drawn for orientation only (no real upper-body IK).

#### A.3 Missing motions that exist in our data / generators
- **Ramps up & down** (`Camargo et. al. 2021\Data\AB07.zip`, `ramp/ik/ramp_{1..6}_*.mat`, 70 trials, measured OpenSim IK): completely absent from old viewer. Added `camargo_ramp_gentle` (~5 deg) and `camargo_ramp_steep` (~11 deg).
- **Overground level-ground walking at slow / normal / fast speeds** (`AB07.zip`, `levelground/ik/levelground_*_{slow,normal,fast}_*.mat`, 31 trials, measured IK): added `camargo_walk_slow`, `camargo_walk_normal`, `camargo_walk_fast`.
- **Fast walking** (synthetic `pipeline/kneil_v1.py` `make_trial()` at ~1.72 m/s, plus Camargo `treadmill_07_01.mat` ~1.7 m/s): added `v16_walk_fast` and `camargo_treadmill_fast`.
- **Stairs at multiple step heights** (`AB07.zip`, `stair_{1..4}` = 10.2, 12.7, 15.2, 17.8 cm, measured IK): added `camargo_stairs_low` (10.2 cm) and `camargo_stairs_high` (17.8 cm) directly from OpenSim IK.
- **Additional v1.6 generator conditions** (`pipeline/kneil_v1.py` `make_trial()`): added `v16_walk_healthy` (1.25 m/s), `v16_walk_limp_mild` (severity 0.4), `v16_walk_crutches` (severity 0.5, crutches).
- Note: Standalone lying / additional bed-transfer variants beyond Trials 36–37 do not have joint-angle files in the repo (`kneil_dataset_v1_6.zip` contains accelerometer CSVs only, not joint angles).

---

### Check 2: `--list` shows all motions with source and duration — **PASS**
- `python viewer/kneil_viewer.py --list` lists **50 motions** (38 `old viewer`, 8 `Camargo replay`, 4 `v1.6 generator`) with ID, source, duration, name, and 7 friendly aliases (`walk_healthy`, `walk_fast`, `stairs_up`, `stairs_down`, `ramp_up`, `sit_to_stand`, `bed_transfer`).

### Check 3: Headless `--render` PNGs — **PASS**
Tested on `walk_healthy` first and visually inspected, then rendered all 6 required motions (all visually verified):
- `cache/viewer/render_walk_healthy.png` (`old_22_walk_healthy`, t=10.0 s)
- `cache/viewer/render_walk_fast.png` (`v16_walk_fast`, t=10.0 s)
- `cache/viewer/render_stairs_up.png` (`old_28_stairs_up_healthy`, t=10.0 s — shows stairs-rule overrides)
- `cache/viewer/render_ramp_up.png` (`camargo_ramp_steep`, t=6.5 s — shows ramp classified as stairs)
- `cache/viewer/render_sit_to_stand.png` (`old_23_sitstand_healthy`, t=7.5 s — chair + STS timeline)
- `cache/viewer/render_bed_transfer.png` (`old_36_bed_healthy`, t=38.0 s — bed + 4 detected bed-transfer events)

### Check 4: Forest V4 class shares (% of windows) vs true class — **PASS**
Computed by `python viewer/kneil_viewer.py --summary-table --summary-json cache/viewer/summary_all.json` (all 50 motions; note 3 Caicedo trials < 4 s have 0 windows). Key highlight on fast walking called stairs: `camargo_walk_fast` (raw stairs 10% -> rule 0%), `camargo_treadmill_fast` (raw stairs 6% -> rule 0%), `camargo_walk_normal` (raw stairs 5% -> rule 0%), `v16_walk_fast` (0% stairs).

| ID | Source | Dur | True | Forest V4 class shares (% of windows) |
|---|---|---|---|---|
| `old_00_treadmill_walking_0_50` | old viewer | 16.0s | walking | walking:92%, still:8% |
| `old_01_treadmill_walking_1_20` | old viewer | 16.0s | walking | walking:100% |
| `old_02_treadmill_walking_1_55` | old viewer | 16.0s | walking | walking:100% |
| `old_03_level_ground_walking_w` | old viewer | 23.8s | standing, walking | walking:60%, still:40% |
| `old_04_stairs_up_and_down_10` | old viewer | 15.2s | stairs_up/down, stand, walk | stairs_up:33%, still:33%, walking:25%, stairs_down:8% (raw stairs 58% -> 42%) |
| `old_05_stairs_up_and_down_18` | old viewer | 15.9s | stairs_up/down, stand, walk | stairs_up:42%, still:33%, stairs_down:17%, walking:8% |
| `old_06_older_adult_0_60_m_s_s` | old viewer | 8.5s | walking | walking:100% |
| `old_07_older_adult_0_96_m_s_s` | old viewer | 5.2s | walking | walking:50%, stairs_down:50% (raw stairs 100% -> 50%) |
| `old_08_older_adult_1_04_m_s_s` | old viewer | 4.8s | walking | walking:100% |
| `old_09_older_adult_1_09_m_s_s` | old viewer | 4.8s | walking | walking:100% |
| `old_10_older_adult_1_15_m_s_s` | old viewer | 4.5s | walking | walking:100% |
| `old_11..13` (Caicedo < 4 s) | old viewer | 3.7–3.8s | walking | 0 windows (shorter than 4 s V4 window) |
| `old_14_your_protocol_early_wa` | old viewer | 30.0s | standing, walking | still:100% |
| `old_15_your_protocol_crutches` | old viewer | 16.2s | standing, walking | walking:100% |
| `old_16_your_protocol_later_no` | old viewer | 17.1s | walking | walking:100% |
| `old_17_partial_weight_bearing` | old viewer | 16.6s | standing, walking | walking:77%, still:23% |
| `old_18_toe_touch_walker` | old viewer | 30.0s | standing, walking | still:96%, walking:4% |
| `old_19_non_weight_bearing_wal` | old viewer | 30.0s | standing, walking | still:100% |
| `old_20_static_spacer_partial` | old viewer | 30.0s | standing, walking | still:100% |
| `old_21_static_spacer_as_toler` | old viewer | 17.5s | standing, walking | walking:86%, still:14% |
| `old_22_walk_healthy` | old viewer | 20.0s | walking | walking:100% |
| `old_23_sitstand_healthy` | old viewer | 16.0s | sit/stand + transitions | sit_to_stand:54%, stand_to_sit:31%, still:15% |
| `old_24_walking_limp_severity` | old viewer | 20.0s | walking | walking:100% |
| `old_25_sit_stand_limp_severit` | old viewer | 18.7s | sit/stand + transitions | sit_to_stand:60%, still:20%, stand_to_sit:20% |
| `old_26_walking_locked_knee_st` | old viewer | 20.0s | walking | walking:100% |
| `old_27_sit_stand_locked_knee` | old viewer | 19.8s | sit/stand + transitions | still:38%, sit_to_stand:31%, stand_to_sit:31% |
| `old_28_stairs_up_healthy` | old viewer | 20.0s | stairs_up | walking:50%, stairs_up:50% (raw stairs 100% -> 50%) |
| `old_29_stairs_down_healthy` | old viewer | 20.0s | stairs_down | stairs_down:100% |
| `old_30_stairs_up_step_to_lock` | old viewer | 19.2s | stairs_up, standing | stairs_up:100% |
| `old_31_stairs_down_step_to_lo` | old viewer | 17.5s | stairs_down, standing | stairs_down:100% |
| `old_32_stairs_up_limp_severit` | old viewer | 20.0s | stairs_up | stairs_up:88%, walking:12% (raw stairs 94% -> 88%) |
| `old_33_stairs_down_limp_sever` | old viewer | 20.0s | stairs_down | stairs_down:100% |
| `old_34_stairs_up_step_to_limp` | old viewer | 21.5s | stairs_up, standing | stairs_up:100% |
| `old_35_stairs_down_step_to_li` | old viewer | 19.6s | stairs_down, standing | stairs_down:81%, walking:19% (raw stairs 100% -> 81%) |
| `old_36_bed_healthy` | old viewer | 53.9s | lying, bed_transfer, sitting | lying:48%, bed_transfer:36%, still:16% |
| `old_37_bed_locked_knee_static` | old viewer | 64.3s | lying, bed_transfer, sitting | lying:44%, bed_transfer:38%, still:18% |
| `camargo_walk_slow` | Camargo replay | 27.9s | standing, walking | walking:62%, still:38% |
| `camargo_walk_normal` | Camargo replay | 23.9s | standing, walking | walking:60%, still:40% (raw stairs 5% -> 0%) |
| `camargo_walk_fast` | Camargo replay | 23.3s | standing, walking | walking:60%, still:40% (raw stairs 10% -> 0%) |
| `camargo_treadmill_fast` | Camargo replay | 20.0s | walking | walking:100% (raw stairs 6% -> 0%) |
| `camargo_ramp_gentle` | Camargo replay | 19.1s | ramp_up/down, stand, walk | walking:38%, stairs_down:25%, stairs_up:19%, still:19% (raw stairs 69% -> 44%) |
| `camargo_ramp_steep` | Camargo replay | 19.2s | ramp_up/down, stand, walk | stairs_up:38%, stairs_down:38%, walking:12%, still:12% (raw stairs 81% -> 75%) |
| `camargo_stairs_low` | Camargo replay | 15.3s | stairs_up/down, stand, walk | stairs_up:33%, walking:25%, still:25%, stairs_down:17% (raw stairs 75% -> 50%) |
| `camargo_stairs_high` | Camargo replay | 16.0s | stairs_up/down, stand, walk | stairs_up:38%, still:31%, stairs_down:23%, walking:8% (raw stairs 69% -> 62%) |
| `v16_walk_healthy` | v1.6 generator | 20.0s | walking | walking:100% |
| `v16_walk_fast` | v1.6 generator | 20.0s | walking | walking:100% |
| `v16_walk_limp_mild` | v1.6 generator | 20.0s | walking | walking:100% |
| `v16_walk_crutches` | v1.6 generator | 20.0s | walking | walking:100% |

### Check 5: C library (`kneil_tinyml` v2.0) == `metrics_ref.py` + sklearn on 3 motions — **PASS**
Measured output of `python viewer/kneil_viewer.py --verify-c`:
- `old_22_walk_healthy`: 16 windows, `raw_mism=0`, `rule_mism=0`, events C/Py `STS 0/0, S2S 0/0, Bed 0/0`, posture `2/2` — **PASS**
- `v16_walk_fast`: 17 windows, `raw_mism=0`, `rule_mism=0`, events C/Py `STS 0/0, S2S 0/0, Bed 0/0`, posture `2/2` — **PASS**
- `old_23_sitstand_healthy`: 13 windows, `raw_mism=0`, `rule_mism=0`, events C/Py `STS 0/0, S2S 0/0, Bed 0/0`, posture `0/0` — **PASS**

### Part C: Blender 5.2 headless renders (Eevee, 1920x1080) — **PASS**
All rendered with `Blender 5.2.0 LTS` (`BLENDER_EEVEE`, 16 samples, `bpy` only, no external assets):
- **Test clip — Healthy walking (3.0 s, 76 frames @ 25 fps)**: 26.99 s total (**0.36 s/frame**). Inspected frames:
  - `cache/viewer/blender_walk_healthy/frame_0000.png`
  - `cache/viewer/blender_walk_healthy/frame_0025.png`
- **Fast walking (2.0 s, 51 frames @ 25 fps)**: 17.30 s (**0.34 s/frame**) -> `cache/viewer/blender_walk_fast/frame_0000.png..frame_0050.png`
- **Stairs up (2.0 s, 51 frames @ 25 fps)**: 17.91 s (**0.35 s/frame**) -> `cache/viewer/blender_stairs_up/frame_0000.png..frame_0050.png` (inspected `frame_0025.png`)
- **Sit-to-stand (3.0 s, 76 frames @ 25 fps)**: 28.28 s (**0.37 s/frame**) -> `cache/viewer/blender_sit_to_stand/frame_0000.png..frame_0075.png` (inspected `frame_0035.png`)
- If MP4 video is desired for talks, Blender's built-in FFmpeg output (`scene.render.image_settings.file_format = 'FFMPEG'`, H.264/MP4) can encode directly with no extra packages.

## 5. Problems and open questions
- Interactive GUI (`mujoco.viewer.launch_passive` + live matplotlib window) was not opened on screen in this headless session; all rendering, camera tracking, kinematics, and classifier code paths were verified via `--render`, `--verify-c`, and `--summary-table`.
- In the old HTML viewer, ultra-slow walker personas (`old_14`, `old_18`–`old_20`, 0.26–0.33 m/s with 33–39% pauses) are classified as `still` 96–100% by the V4 forest, and steep Camargo ramps (`camargo_ramp_steep`, ~11 deg) are classified as `stairs_up`/`stairs_down` 75% (ramps are not a separate V4 class).
- `pipeline/kneil_v1.py`, `pipeline/camargo_replay.py`, and `kneil_tinyml/` were not modified; `viewer/kneil_viewer.py` imports them directly and builds its own visual MuJoCo XML with the same joint structure/dimensions to add floor/chair/stairs/ramp/bed props and the device-axis triad.
