# KNEIL 3D Motion Viewer (`viewer/`)

Interactive and headless 3D MuJoCo motion viewer with real-time on-device V4 forest classification (`kneil_tinyml` v2.0 via ctypes), plus a Blender 5.2 export/render pipeline for presentation visuals.

## Quick start

```powershell
# List all 50 motions (38 old viewer + 8 Camargo replay + 4 v1.6 generator)
python viewer/kneil_viewer.py --list

# Interactive 3D MuJoCo viewer + live matplotlib signal/decision window
python viewer/kneil_viewer.py walk_healthy

# Headless single-frame composite render (3D + signals + V4 forest timeline)
python viewer/kneil_viewer.py walk_healthy --render cache/viewer/render_walk_healthy.png --t 10.0

# Headless PNG sequence
python viewer/kneil_viewer.py walk_healthy --frames cache/viewer/frames_walk --fps 10

# Print V4 forest class shares for all 50 motions
python viewer/kneil_viewer.py --summary-table

# Verify C library == metrics_ref.py + sklearn forest on 3 motions
python viewer/kneil_viewer.py --verify-c
```

## Interactive keyboard controls
- `Space`: pause / resume
- `Left` / `Right`: step backward / forward 1 s
- `n` / `p`: next / previous motion
- `+` / `-`: increase / decrease playback speed

## Friendly motion aliases
- `walk_healthy` -> `old_22_walk_healthy`
- `walk_fast` -> `v16_walk_fast`
- `stairs_up` -> `old_28_stairs_up_healthy`
- `stairs_down` -> `old_29_stairs_down_healthy`
- `ramp_up` -> `camargo_ramp_steep`
- `sit_to_stand` -> `old_23_sitstand_healthy`
- `bed_transfer` -> `old_36_bed_healthy`

## Blender studio renders (Part C)
MuJoCo remains the source of truth for all segment poses and implant axes; Blender only renders them.

```powershell
# 1. Export per-frame MuJoCo body poses, implant triad, scene props, and V4 forest decisions
python viewer/export_motion.py walk_healthy --fps 25 --max-s 3.0

# 2. Render headless with Blender 5.2 (Eevee, 1920x1080 PNG sequence)
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b -P viewer/blender_render.py -- cache/viewer/blender_walk_healthy.json cache/viewer/blender_walk_healthy_frames
```

## Cache and logs
- Cached motions (`*.npz` + `*.json`), compiled `libkneil_v4.dll`, rendered PNGs, and `viewer_log.txt` are stored under `cache/viewer/` (git-ignored).
