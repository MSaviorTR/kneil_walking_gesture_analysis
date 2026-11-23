# Task V3e (worker gemini): a motion picker and a Windows executable for the viewer

Branch `gemini/V3e`, new from `main`. Report `tasks/V3e_report.md`, committed last. Same rules as V3-V3d
(**never commit the OBJ or anything made from it**; the exe bundle stays local, never in git).

## Owner's request (24 Nov 2026)
"An executable file and an option to choose the motion." Today the owner must type
`python viewer/kneil_viewer.py <motion id>` in a terminal.

## Part A: motion picker (`viewer/launcher.py`, version 1.0, tkinter only)
- One window: the 50 motions in a list, grouped by source (old viewer / Camargo replay / v1.6 generator), with
  duration, true classes and the in-sample / out-of-sample tag; a search box; the friendly aliases on top.
- Buttons: **Open 3D viewer** (also on double-click; runs the existing interactive viewer for the selected motion),
  **Save PNG at time t** (the existing `--render`), and **Render Blender clip** (start time, length; runs the existing
  export + Blender render in the background and opens the output folder when done; disabled with a clear message if
  Blender is not found).
- Options: playback speed, implant CAD on/off, see-through leg on/off (if the viewer has these switches; add them as
  command-line flags if needed).
- After the 3D viewer is closed, the picker stays open for the next motion. Errors are shown in a message box with the
  log path, never a silent exit.

## Part B: Windows executable (`viewer/build_exe.ps1`)
- PyInstaller (already installed, 6.22.3) **one-folder** build: `dist\KNEIL_viewer\KNEIL_viewer.exe` starting the
  picker. Include the kneil_tinyml DLL, MuJoCo, matplotlib backends and the needed data.
- The exe must run **without G: and without the repo**: pre-build the motion cache for all 50 motions and the
  converted CAD meshes into the bundle's data folder. If a source is missing at run time, the motion is greyed out with
  the reason.
- Add `dist/`, `build/` and `*.spec` (or the spec under `viewer/` if you keep it) to `.gitignore`.
- Report the bundle size and the start time.

## Checks
1. `python viewer/launcher.py` works; screenshot of the picker (saved under `cache\viewer\`).
2. Build the exe; run it from a PowerShell with a **clean PATH** (no Python) and with `G:` hidden from the process
   (e.g. a config override), open 3 motions and save a PNG from the exe; list what you checked.
3. `git status` shows no bundle, cache, OBJ or mesh files.
4. `viewer/README.md`: "Run the exe" section for the owner (where it is, how to rebuild it).
