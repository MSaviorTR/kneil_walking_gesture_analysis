# Task V3e Report (worker gemini): Motion Picker & Standalone Windows Executable

## 1. Status
done

## 2. Files
- `viewer/launcher.py` (added, `launcher 1.0`): `tkinter`-only motion picker listing all 50 motions grouped by source (`old viewer`, `Camargo replay`, `v1.6 generator`) with the 7 friendly aliases pinned on top, live search box, duration / true classes / in-sample vs out-of-sample / availability status columns, viewer options (`Playback speed`, `Implant CAD`, `See-through right leg`), actions (`Open 3D viewer` + double-click, `Save PNG at time t`, `Render Blender clip` in background + auto-disabled if Blender missing), error message boxes with log path, and frozen-exe subprocess worker modes (`--worker-viewer`, `--worker-render`, `--worker-export`, `--screenshot`, `--smoke-test`).
- `viewer/build_exe.ps1` (added, `build_exe 1.0`): pre-builds all 50 motion caches + `catalog.json` + `libkneil_v4.dll` and converted CAD meshes, stages `build/bundled_data/`, and runs PyInstaller 6.22.3 (`--onedir --windowed`) to build `dist\KNEIL_viewer\KNEIL_viewer.exe`.
- `viewer/kneil_viewer.py` (modified, `kneil_viewer 1.4`): added `--speed`, `--no-cad`, `--no-see-through`, and `--prebuild-all` CLI flags; added `bundled_data/` lookup for `motions/`, `libkneil_v4.dll`, `opensim/gait2354_simbody.osim`, and `catalog.json`; added per-motion `available` / `unavailable_reason` annotation; added top-level `import mujoco.renderer` for PyInstaller; routes frozen-exe logs/cache to `%LOCALAPPDATA%\KNEIL_viewer\cache\`.
- `viewer/implant_cad.py` (modified, `implant_cad 1.2`): added `bundled_data/cad/` lookup (resolving mesh paths relative to the bundle directory so the exe works without `sims_html` or the repo) and `KNEIL_CAD_OBJ` env override.
- `.gitignore` (modified): added `dist/`, `build/`, `*.spec`, `*.stl` (alongside existing `cache/`, `*.obj`, `*.dll`, `*.exe`).
- `viewer/README.md` (modified): added the `"Run the exe"` section for the owner (location, usage, and rebuild command).
- `tasks/V3e_report.md` (added): this report.

Note: zero bundle, cache, `.obj`, `.stl`, `.dll`, or `.exe` files are tracked or committed.

## 3. Commands
```powershell
# Check 1: run picker from Python and capture window screenshot
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\launcher.py --screenshot cache\viewer\picker_screenshot.png

# Part B: build the standalone one-folder Windows executable
powershell -NoProfile -ExecutionPolicy Bypass -File viewer\build_exe.ps1

# Check 2: test dist\KNEIL_viewer\KNEIL_viewer.exe from C:\Windows\Temp with clean PATH (no Python) and G:/sims_html hidden
$env:PATH = "C:\Windows\System32;C:\Windows"
$env:KNEIL_DATA_ROOT = "C:\nonexistent_G"
$env:KNEIL_RESULTS = "C:\nonexistent_G"
$env:KNEIL_OLD_HTML = "C:\nonexistent_html"
$env:KNEIL_CAD_OBJ = "C:\nonexistent_obj"
$env:KNEIL_CACHE = "C:\nonexistent_cache"
Push-Location C:\Windows\Temp
Start-Process -FilePath "C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_gemini\dist\KNEIL_viewer\KNEIL_viewer.exe" -ArgumentList "--screenshot","C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_gemini\cache\viewer\exe_picker_screenshot.png" -Wait -PassThru
Start-Process -FilePath "C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_gemini\dist\KNEIL_viewer\KNEIL_viewer.exe" -ArgumentList "--smoke-test","C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_gemini\cache\viewer\exe_smoke" -Wait -PassThru
Pop-Location

# Check 3: verify clean git status
git status --short
```

## 4. Acceptance checks

### Check 1 — `python viewer/launcher.py` works & picker screenshot saved: **PASS**
- Started cleanly (`launcher 1.0`, `frozen=False`, picker window ready in **0.33 s**, **50/50 motions ready**).
- Screenshot captured and visually inspected: `cache\viewer\picker_screenshot.png` (`1136x719`), showing the 7 friendly aliases pinned on top, `old viewer (38)` / `Camargo replay (8)` / `v1.6 generator (4)` groups, search box, options (`Playback speed`, `Implant CAD (3 parts)`, `See-through right leg`), action buttons (`Open 3D viewer`, `Save PNG at time t`, `Render Blender clip`), and status bar with log path.

### Check 2 — Standalone exe built & verified with clean PATH (no Python) and G: hidden: **PASS**
- **Bundle path**: `dist\KNEIL_viewer\KNEIL_viewer.exe` (PyInstaller 6.22.3, one-folder build, Python 3.12.10).
- **Bundle size**: **259.1 MB** (includes all 50 pre-built motions, converted 3-part CAD meshes, OpenSim Gait2354 geometry, `libkneil_v4.dll`, MuJoCo, GLFW, Matplotlib, SciPy, NumPy, Pillow, and `blender_render.py`).
- **Picker start time (standalone exe, clean PATH, G: hidden)**: **0.27 s** (warm) / **0.34 s** (cold) from process start to Tk window ready with `50/50 motions ready | standalone exe | kneil_viewer 1.4` (`cache\viewer\exe_picker_screenshot.png`, visually inspected).
- **3 motions opened + PNG saved from exe (`--smoke-test`, exit code `0`, `12.24 s` total)** running from `C:\Windows\Temp` with `PATH=C:\Windows\System32;C:\Windows` and `KNEIL_DATA_ROOT`/`KNEIL_RESULTS`/`KNEIL_OLD_HTML`/`KNEIL_CAD_OBJ`/`KNEIL_CACHE` pointed at nonexistent paths:
  1. `walk_healthy` (`old_22_walk_healthy`) — loaded from bundled cache & built MuJoCo model with CAD meshes.
  2. `sit_to_stand` (`old_23_sitstand_healthy`) — loaded from bundled cache & built MuJoCo model with CAD meshes.
  3. `stairs_up` (`old_28_stairs_up_healthy`) — loaded from bundled cache & built MuJoCo model with CAD meshes.
  4. Rendered composite PNG via subprocess `KNEIL_viewer.exe --worker-render`: `cache\viewer\exe_smoke\exe_smoke_walk_healthy.png` (`377,004 bytes`), visually inspected (translucent blue right leg, 3-part CAD inside, cyan chip + RGB axes, 50 Hz / 6 Hz LP signals, and V4 forest decision timeline).

### Check 3 — `git status` clean (no bundle, cache, OBJ, or mesh files): **PASS**
- `git status --short` shows only the 6 source/doc files committed (`54649e4`) and this report. `dist/`, `build/`, `*.spec`, `cache/`, `*.obj`, `*.stl`, `*.dll`, and `*.exe` are all ignored by `.gitignore`.

### Check 4 — `viewer/README.md` `"Run the exe"` section: **PASS**
- Added `"Run the exe (recommended for everyday use)"` at the top of `viewer/README.md` with the bundle path, standalone capabilities, `%LOCALAPPDATA%\KNEIL_viewer\cache\` log path, and the one-line rebuild command (`powershell -NoProfile -ExecutionPolicy Bypass -File viewer\build_exe.ps1`).

## 5. Problems and open questions
- **Interactive 3D window click-through**: in this headless/automated session, Check 2 verified the frozen picker GUI (`exe_picker_screenshot.png`), opening 3 motions' MuJoCo models, and rendering a PNG via the frozen subprocess worker (`--worker-render`), rather than manually orbiting the interactive `mujoco.viewer` window with a mouse; the owner should double-click `dist\KNEIL_viewer\KNEIL_viewer.exe` and open a motion to confirm interactive mouse orbit on their display.
- **Bundle size (259.1 MB)**: dominated by `scipy`, `matplotlib`, `mujoco`, and the 50 pre-built motion `.npz` files; this is normal for a scientific Python one-folder bundle and starts in `0.27–0.34 s`.
- **Blender clip button**: automatically enabled when Blender 5.2 (or 4.x / `blender` on PATH) is installed on the host machine and disabled with `(Blender not found)` otherwise.
