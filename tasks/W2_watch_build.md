# Task W2: build the watch with the KNEIL mode (after ESP-IDF is installed)

Same branches as W1 (`base: existing`): watch code on `agent/W1` in `guder_watch_agent`, report on `agent/W1` in
`kneil_v4_agent` (`tasks/W2_report.md`, committed last). Never push, never flash, do not install packages.

## Review of the W1 fix (manager)
Accepted: host tests rerun by the manager (75 + 35 + 76 PASS), `apply_roles()` is upstream plus one line, page 1 is
rebuilt from the `built_kneil` flag. Two small items first:
1. `main/ui/ui.c`, the comment above `built_kneil` contains a backspace character (0x08, from a PowerShell `` `b ``
   escape): write the comment in plain ASCII. Check all your new/changed files for control characters.
2. Before `lv_obj_clean()` of page 1, stop the face's running value animations (`lv_anim_delete` on its animated
   variables, as `stop_anim()` does) through a new `ui_face_destroy()` in `ui_face.c`, so a 600 ms glide can never
   write into deleted labels. Only called from `build_page1()`; the face code is otherwise unchanged.

## Build (ESP-IDF v5.5.5, installed by the owner)
1. Find the install (`C:\Espressif`, `%USERPROFILE%\.espressif`, or the VS Code ESP-IDF extension's folder) and use its
   `export.ps1` / `export.bat`; write the exact commands in the report.
2. `idf.py set-target esp32s3` if needed, `idf.py build` on `agent/W1`; fix compile errors **in the new files only**.
   No new warnings in new files.
3. `idf.py size` for `agent/W1` and for `upstream/main` (separate build folder): flash and RAM before / after.
4. `test/sim/run.sh` (Git Bash; LVGL now in `managed_components/`): screenshots of every page in the existing scenarios
   (must look as before) and of the KNEIL page (connected v2 walking with events and a summary; scanning; the reset
   confirm dialog). List the files.
5. Host tests again (counts).

If a step cannot run on Windows, give the exact error and stop that step.
