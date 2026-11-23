# Task V3b Report (worker gemini)

## 1. Status
done

## 2. Files
- `viewer/kneil_viewer.py` (changed -> v1.1: horizontal travel-axis alignment for Camargo trials, stance-foot fitting for floor/chair/stairs/ramp props, `--check-feet` diagnostic, `in_sample_status()` labels in `--list`, `--summary-table`, and HUD)
- `viewer/export_motion.py` (changed -> v1.1: exports `hip_flex` per frame for decorative arms and `in_sample` / `in_sample_label` metadata)
- `viewer/blender_render.py` (changed -> v1.1: human-proportioned sculpted figure with pelvis, tapered torso, shoulders, neck, decorative asymmetric-swing arms [not measured], visible metallic femoral cap + white articulating tibial spacer + glowing cyan implant chip + 3 axes, exact foot bottom matching MuJoCo `0.056 m`, fitted ramp deck + top landing, in-sample tag in HUD)
- `viewer/README.md` (changed: added "How to start" interactive viewer guide for the owner with exact commands, window descriptions, keyboard controls, and in-sample note)
- `tasks/V3b_report.md` (added: this report)

## 3. Commands
```powershell
git switch -c gemini/V3b main
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py --check-feet
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py --verify-c
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py stairs_up --render cache/viewer/render_stairs_up.png --t 10.0
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py ramp_up --render cache/viewer/render_ramp_up.png --t 4.2
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py sit_to_stand --render cache/viewer/render_sit_to_stand.png --t 5.4
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/export_motion.py stairs_up --t0 8.0 --max-s 2.0 --fps 25 --out cache/viewer/blender_stairs_up.json
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/export_motion.py ramp_up --t0 3.0 --max-s 2.0 --fps 25 --out cache/viewer/blender_ramp_up.json
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/export_motion.py sit_to_stand --t0 4.0 --max-s 3.0 --fps 25 --out cache/viewer/blender_sit_to_stand.json
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P viewer/blender_render.py -- cache/viewer/blender_stairs_up.json cache/viewer/blender_stairs_up --step 1 --samples 16
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P viewer/blender_render.py -- cache/viewer/blender_ramp_up.json cache/viewer/blender_ramp_up --step 1 --samples 16
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P viewer/blender_render.py -- cache/viewer/blender_sit_to_stand.json cache/viewer/blender_sit_to_stand --step 1 --samples 16
```

## 4. Acceptance checks

### Check 1: Foot-to-prop contact error (before vs after) — **PASS**
Metric: `|foot_bottom_y - prop_surface_y|` during stance (`|dy/dt| < 0.12 m/s`, `foot_bottom_y = min(ankle_r_y, ankle_l_y) - 0.056 m`, identical in MuJoCo and Blender). Root causes fixed: (a) Camargo lab trajectories ran along `+Z` near `x = -7.15 m`, so rotating horizontal travel to `+X` centered at `z = 0` aligned body and props (leaving gravity and implant signals invariant); (b) floor, chair, stairs treads, and ramp deck + top landing are now fitted directly to stance-foot trajectories. **All 48 non-bed motions pass `median |err| < 2.0 cm`** (`0.03–1.26 cm`).

| Motion ID | Env | BEFORE med \|err\| (cm) | BEFORE p95 (cm) | AFTER med \|err\| (cm) | AFTER p95 (cm) |
|---|---|---:|---:|---:|---:|
| `old_00_treadmill_walking_0_50` | treadmill | 0.68 | 1.20 | **0.23** | 0.52 |
| `old_01_treadmill_walking_1_20` | treadmill | 0.91 | 2.00 | **0.28** | 0.67 |
| `old_03_level_ground_walking_w` | floor | 1.24 | 2.48 | **0.63** | 1.18 |
| `old_04_stairs_up_and_down_10` | stairs | 2.36 | 10.09 | **0.13** | 0.68 |
| `old_05_stairs_up_and_down_18` | stairs | 4.51 | 21.42 | **0.10** | 0.50 |
| `old_22_walk_healthy` | floor | 2.11 | 4.57 | **0.18** | 2.68 |
| `old_23_sitstand_healthy` | chair | 1.69 | 1.82 | **0.13** | 1.74 |
| `old_28_stairs_up_healthy` | stairs | 19.65 | 23.55 | **0.08** | 0.38 |
| `old_29_stairs_down_healthy` | stairs | 11.90 | 13.33 | **0.10** | 0.38 |
| `camargo_walk_slow` | floor | 5.03 | 5.90 | **0.77** | 4.66 |
| `camargo_walk_normal` | floor | 5.03 | 5.93 | **0.49** | 3.26 |
| `camargo_walk_fast` | floor | 5.41 | 5.88 | **0.75** | 2.85 |
| `camargo_treadmill_fast` | treadmill | 5.33 | 5.97 | **0.24** | 0.68 |
| `camargo_ramp_gentle` | ramp | 21.85 | 65.36 | **1.26** | 5.03 |
| `camargo_ramp_steep` | ramp | 55.13 | 113.73 | **1.06** | 2.37 |
| `camargo_stairs_low` | stairs | 29.89 | 65.54 | **0.40** | 2.00 |
| `camargo_stairs_high` | stairs | 35.66 | 105.42 | **0.34** | 2.33 |
| `v16_walk_healthy` | floor | 5.47 | 5.81 | **0.12** | 0.59 |
| `v16_walk_fast` | floor | 5.52 | 6.28 | **0.25** | 1.18 |

### Check 2: Updated `--render` PNGs and Blender 5.2 frames — **PASS**
All visually inspected after rendering:
- **MuJoCo `--render` PNGs**:
  - `cache/viewer/render_stairs_up.png` (`old_28_stairs_up_healthy`, t=10.0 s — feet flat on step tread, handrail, in-sample HUD)
  - `cache/viewer/render_ramp_up.png` (`camargo_ramp_steep`, t=4.2 s — teal sloped ramp directly under feet with shadow, in-sample HUD)
  - `cache/viewer/render_sit_to_stand.png` (`old_23_sitstand_healthy`, t=5.4 s — chair + floor aligned, in-sample HUD)
  - (Also refreshed `render_walk_healthy.png`, `render_walk_fast.png`, `render_bed_transfer.png`.)
- **Blender 5.2 Eevee 1920x1080 frames** (human proportions, decorative asymmetric-swing arms [not measured], visible metallic femoral cap + white articulating knee spacer + glowing cyan implant chip + 3 axes):
  - **Stairs up** (51 frames, 19.85 s, 0.39 s/frame):
    - `cache/viewer/blender_stairs_up/frame_0010.png`
    - `cache/viewer/blender_stairs_up/frame_0035.png`
  - **Ramp up** (51 frames, 19.13 s, 0.38 s/frame):
    - `cache/viewer/blender_ramp_up/frame_0010.png`
    - `cache/viewer/blender_ramp_up/frame_0035.png`
  - **Sit-to-stand** (76 frames, 29.38 s, 0.39 s/frame):
    - `cache/viewer/blender_sit_to_stand/frame_0015.png`
    - `cache/viewer/blender_sit_to_stand/frame_0045.png`

### Check 3: In-sample / out-of-sample status per source (evidence from `export_v4.py` & `windows_W4s.npz`) — **PASS**
`pipeline/export_v4.py:102-106` trains the V4 forest (`V4half`) on **all rows with `y >= 0`** in `KNEIL_results\v4\stepD\windows_v11\windows_W4s.npz` (`cv_v4.training_set_v4`, `mask = all True`):

| Viewer source | Motions | In-sample? | Label shown in viewer | Evidence in `windows_W4s.npz` / `export_v4.py` |
|---|---|---|---|---|
| Old viewer: Camargo AB07 | `old_00`..`old_05` | **Yes** | `training data (in-sample: AB07)` | `ds == 'Camargo simulated'`, `grp == 'ab07'` has 2,657 rows (`y >= 0`: walking 1,706, standing 696, stairs_up 164, stairs_down 91). |
| Camargo replay (walk / treadmill / stairs) | `camargo_walk_*`, `camargo_treadmill_fast`, `camargo_stairs_*` | **Yes** | `training data (in-sample: AB07)` | Same `ab07` subject in `Camargo simulated` (2,657 trained windows). |
| Camargo replay (ramps) | `camargo_ramp_gentle`, `camargo_ramp_steep` | **Partial (person in-sample; ramps excluded)** | `training data (in-sample person AB07; ramps not trained)` | `ab07` is in `Camargo simulated`, but `lab` in `windows_W4s.npz` contains only `walking`, `standing`, `stairs_up`, `stairs_down` (0 ramp windows trained). |
| Old viewer: Caicedo 2020 | `old_06`..`old_13` | **Yes** | `training data (in-sample: Caicedo)` | `ds == 'Caicedo older adults'` (`src == 'caicedo'`) has 554 trained windows (`y == 0`); all 7 viewer subjects are present: `caicedo:5` (14), `14` (14), `22` (10), `24` (6), `26` (36), `29` (10), `35` (2). |
| Old viewer: Synthetic v1.6 | `old_22`..`old_37` | **Yes** | `training data (in-sample: v1.6 sim)` | `ds == 'v1.6 synthetic'` (`src == 'sim'`, 60 virtual patients `P000..P059`, 8,613 trained windows) uses the same v1.6 simulator. |
| v1.6 generator (`kneil_v1.py`) | `v16_walk_*` | **Yes (same generator)** | `training data (in-sample: v1.6 generator)` | Same `kneil_v1.py` generator as `v1.6 synthetic` (`P000..P059`, 8,613 windows), generated with fresh seeds `101..104`. |
| Old viewer: Spacer-period personas (walker / crutches / static spacer) | `old_14`..`old_21` | **No (out-of-sample)** | `out-of-sample (recomposed AB07)` | 0 matching rows in `windows_W4s.npz` (no spacer/walker persona dataset in training); recomposed from AB07 strides with artificial pauses/limits not present in training. |

### Check 4: `viewer/README.md` "How to start" & regression check — **PASS**
- `viewer/README.md` now opens with a step-by-step **"How to start (interactive viewer)"** section (exact PowerShell commands, description of both synchronized windows, keyboard controls, and in-sample note).
- Regression check: `python viewer/kneil_viewer.py --verify-c` still prints **PASS** (0 mismatches on all 3 motions).

## 5. Problems and open questions
- Interactive GUI (`mujoco.viewer.launch_passive` + live matplotlib window) remains for the owner to test on screen (documented in `viewer/README.md`).
- Decorative arms in `viewer/blender_render.py` are not measured (driven opposite to asymmetric hip flexion so they swing naturally during walking/stairs/ramps and rest calmly at the sides during symmetric sit-to-stand).
- On a few trials with brief toe-drag or curved walking (`camargo_walk_slow` p95 4.66 cm, `camargo_ramp_gentle` p95 5.03 cm, `old_19_non_weight_bearing_wal` p95 7.59 cm where one leg is held in the air), `p95 |err|` reflects real vertical ankle lift during late-stance heel-rise/transition while `median |err|` is 0.03–1.26 cm across all 48 non-bed motions.
