# KNEIL 3D Motion Viewer (`viewer/`)

Interactive and headless 3D MuJoCo motion viewer with real-time on-device V4 forest decisions (`kneil_tinyml` v2.0 via ctypes), plus a Blender 5.2 studio export/render pipeline.

## How to start (interactive viewer)

Open PowerShell in the workspace root (`kneil_v4_workspace`) and run:

```powershell
# 1. See all 50 available motions (with source, duration, and in-sample/out-of-sample status)
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py --list

# 2. Launch the interactive viewer on a motion (using an alias or full ID)
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer/kneil_viewer.py walk_healthy
```

**What opens (two synchronized windows):**
1. **MuJoCo 3D window** (`mujoco.viewer`): 3D skeletal model replaying the motion with the floor / chair / stairs / ramp / bed fitted to the feet, the tibial insert and cyan implant chip on the device tibia, and the 3 device-axis arrows (red = X anterior, green = Y left, blue = Z superior). Drag with mouse to orbit/zoom; camera tracks the pelvis.
2. **Matplotlib signal window** (`KNEIL Signals`): live-scrolling vertical cursor over the 50 Hz simulated implant acceleration (`x`, `y`, `z` — faint raw + bold 6 Hz chip low-pass) and the coloured 4 s / 1 s-hop **Forest V4** decision timeline directly above the **True** activity timeline. The title bar shows current time, class after stairs rule, raw class, vote %, and posture.

**Keyboard controls (focus the MuJoCo window):**
- `Space`: pause / resume playback
- `Left` / `Right`: step backward / forward by 1 s
- `n` / `p`: switch to next / previous motion in the 50-motion catalog
- `+` / `-`: increase / decrease playback speed (0.2x to 4.0x)
- Close the MuJoCo window (or `Esc`) to exit.

## Friendly motion aliases
- `walk_healthy` -> `old_22_walk_healthy`
- `walk_fast` -> `v16_walk_fast`
- `stairs_up` -> `old_28_stairs_up_healthy`
- `stairs_down` -> `old_29_stairs_down_healthy`
- `ramp_up` -> `camargo_ramp_steep`
- `sit_to_stand` -> `old_23_sitstand_healthy`
- `bed_transfer` -> `old_36_bed_healthy`

## Headless rendering & verification commands

```powershell
# Single composite PNG (3D + signals + V4 forest timeline)
python viewer/kneil_viewer.py stairs_up --render cache/viewer/render_stairs_up.png --t 10.0

# Numbered PNG sequence
python viewer/kneil_viewer.py walk_healthy --frames cache/viewer/frames_walk --fps 10

# Print V4 forest class shares for all 50 motions (with in-sample / out-of-sample tags)
python viewer/kneil_viewer.py --summary-table

# Check stance foot-to-prop contact error (cm) on every floor, stairs, and ramp motion
python viewer/kneil_viewer.py --check-feet

# Verify kneil_tinyml C library == metrics_ref.py + sklearn forest on 3 motions
python viewer/kneil_viewer.py --verify-c
```

## Blender studio renders (Part C)
MuJoCo stays the source of truth for all leg poses and implant axes; Blender renders smooth human-proportioned figures (with decorative swinging arms, not measured), knee spacer + implant chip, and studio lighting.

```powershell
# 1. Export per-frame MuJoCo poses, implant triad, scene props, and V4 decisions
python viewer/export_motion.py stairs_up --t0 8.0 --max-s 2.0 --fps 25 --out cache/viewer/blender_stairs_up.json

# 2. Render headless with Blender 5.2 (Eevee, 1920x1080 PNG sequence)
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P viewer/blender_render.py -- cache/viewer/blender_stairs_up.json cache/viewer/blender_stairs_up
```

## Cache and logs
- Cached motions (`*.npz` + `*.json`), compiled `libkneil_v4.dll`, rendered PNGs, and `viewer_log.txt` are stored under `cache/viewer/` (git-ignored).
- Note: most motions in the catalog (Camargo AB07, Caicedo, v1.6 synthetic) were in the V4 training data and are marked `training data (in-sample)` in `--list`, `--summary-table`, and on-screen; their class shares are an indication only. Only the spacer-period personas (and Camargo ramp windows) were not trained on.
