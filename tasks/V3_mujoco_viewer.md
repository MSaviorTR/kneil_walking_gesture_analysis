# Task V3: a clean KNEIL motion viewer in Python + MuJoCo (with the forest's decision)

Branch `gemini/V3` in `kneil_v4_gemini`, new from `main`. Report `tasks/V3_report.md`, committed last.
Read `AGENTS.md`, `CLAUDE.md` and `README.md` first.

## Background
The owner's old viewer is one self-contained HTML file (12 MB):
`C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\sims_html\KNEIL motion viewer.html` (2D canvas stick figure, the motion data
embedded as JSON at 50 Hz, 23 motions: walking / sit-stand / stairs / bed for healthy older adult, limp, locked knee,
and walking-aid protocols). **Do not change or move it.** The owner wants something cleaner, with more motions, built
with Python and MuJoCo (installed: system Python 3.12, `mujoco 3.17.0`; not installed: imageio, PyQt). You may use
more compute than the HTML did.

## Part A: check the old viewer (report only)
1. List the 23 motions: name, duration, what is animated (segments, joints), which signals are shown, and where the data
   most likely came from (compare with `pipeline/kneil_v1.py` `make_trial()` / the v1.6 synthetic scenarios and with
   `pipeline/camargo_replay.py`).
2. Check what it shows against the project facts in `CLAUDE.md`: implant point (2.5 cm below the joint centre, 5 mm
   anterior), device frame (x anterior, y left, z superior; standing reads (0, 0, +1 g)), 50 Hz. List anything wrong or
   unclear.
3. List the motions that exist in our data but are missing from the viewer. At least: walking at slow / normal /
   **fast** speed (the owner's main device problem: fast walking was called stairs), ramps up/down and stairs at
   different heights from the Camargo replay (measured joint angles, 22 people), lying and bed transfer variants, and
   any other class or condition of the v1.6 generator. Say for each where its joint angles come from.

## Part B: the new viewer (`viewer/kneil_viewer.py`, version 1.0, plus `viewer/README.md`)
1. **3D**: the KNEIL MuJoCo model from `pipeline/kneil_v1.py` (`build_model`) replaying a motion's joint angles, with
   the scene objects the motion needs (floor, chair, stairs with the right step height, ramp, bed, walking aid where
   available; simple shapes are fine). The implant point is drawn on the tibia with its device axes (x, y, z arrows).
   Camera follows the body; a sensible default view per motion.
2. **Signals and decision**, synchronised with the 3D view: the simulated implant acceleration x/y/z at 50 Hz (from the
   same code path that makes the training data, including the 6 Hz low-pass the chip applies), and the **forest's
   decision** for every 4 s window with a 1 s hop, computed by the real chip library `kneil_tinyml` v2.0 through ctypes
   (as `pipeline/check_step_e.py` does): class after the stairs rule, raw class, vote share, events and posture. Show the
   class as a coloured timeline (class colours from `..\kneil_firmware\pc_app\kneil\protocol.py` CLASS_COLOURS_V2) and,
   where the motion has a true label, the true class under it.
3. **Use**: `python viewer/kneil_viewer.py --list` lists all motions; `python viewer/kneil_viewer.py <motion>` opens the
   MuJoCo viewer (`mujoco.viewer.launch_passive`) and a matplotlib window for the signals; keys: space = pause,
   left/right = step 1 s, `n`/`p` = next/previous motion, `+`/`-` = speed. It must also run headless:
   `--render out.png --t 12.5` writes one frame (3D + signals side by side) with `mujoco.Renderer`, so you can test it
   without a screen, and `--frames DIR` writes a numbered PNG sequence (no video library needed).
4. **Motions**: all 23 of the old viewer, plus the missing ones from A3 that have joint angles (at least slow / normal /
   fast walking, ramps up and down, stairs at two heights, from the Camargo replay). Motions are built once and cached
   under `cache\viewer\` (not committed) so the viewer starts fast.

## Part C (after A and B pass): realistic renders with Blender
Blender is installed: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` (also 4.5). The owner wants more
realistic visuals for talks. MuJoCo stays the source of truth for the motion; Blender only renders it.
1. `viewer/export_motion.py`: write a motion's body poses per frame (segment positions + quaternions from MuJoCo, 50 Hz
   or resampled to 25/30 fps), the scene objects and the implant point/axes to a JSON file under `cache\viewer\`.
2. `viewer/blender_render.py`, run headless: `blender.exe -b -P viewer/blender_render.py -- <motion json> <out dir>`.
   It builds the scene from the JSON (smooth limb shapes, a visible knee spacer and implant on the tibia, the
   chair / stairs / ramp / bed, soft studio light, a floor with a shadow), keyframes the poses, and renders a PNG
   sequence (Eevee, 1920 x 1080). Optional overlay: the forest's class as a coloured label in a corner.
3. Test on 3 s of healthy walking first; report the render time per frame and show 2 frames (paths in the report).
   Then render: fast walking, stairs up, sit-to-stand. No video encoding needed (a PNG sequence is enough); if you think
   a video is needed, say which tool you would use (Blender can write MP4 itself).
4. Use only Blender's own Python (bpy) inside Blender; no add-ons or downloaded assets (no human models from the web).

## Rules
- Test on one motion first (walking, healthy) with `--render`, and show the PNG path in the report before building all.
- Every script prints a version line and logs to `cache\viewer\viewer_log.txt`.
- Read-only on data and earlier results; no change to `kneil_tinyml/`, `pipeline/kneil_v1.py`, `pipeline/camargo_replay.py`
  (import them; copy a function into `viewer/` only if you must change it, and say why).
- No new packages. If something truly needs one (e.g. video export), stop that part and say which package and why.

## Acceptance checks
1. Part A tables in the report.
2. `--list` shows all motions with their source (old viewer / v1.6 generator / Camargo replay) and duration.
3. `--render` PNGs for at least: healthy walking, fast walking, stairs up, ramp up, sit-to-stand, bed transfer (paths
   under `cache\viewer\`, listed in the report; the manager looks at them).
4. For each motion: the forest's class shares (% of windows per class) in a table, next to the true class. Fast walking
   called stairs must be visible if it happens.
5. The C library decision equals `pipeline/metrics_ref.py` + the sklearn model on 3 motions (same check as E1).
