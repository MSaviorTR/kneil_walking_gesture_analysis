# Task E2: V4 model in the firmware, BLE protocol v2, PC app

Read `AGENTS.md` first. This task works in **two worktrees**:
- **Firmware code**: `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_firmware_agent` (a git worktree of the
  firmware repo `kneil_firmware`, branch `agent/E2`, already created by the manager from `origin/main` fd74429). All
  firmware, bridge, protocol and PC-app changes are committed **there**, on `agent/E2`.
- **Report and prompts**: your usual worktree `kneil_v4_agent`, new branch `agent/E2` from `main` (the normal
  `base: main` step). Commit `prompts/*.md`, the `docs/add_v3_model.py` guard and `tasks/E2_report.md` (last) here.

The owner allowed this task (17 Nov 2026) to change, **in the firmware repo only**: the kneil_tinyml copy
(`include/`, `src/kneil_*.c`, `tests/`, `zephyr/`, `docs/kneil_tinyml.md`), `src/kneil_live.c`, `kneil.conf`,
`protocol/`, `bridge/src/main.c` + `bridge/README.md`, `pc_app/`, `README.md`, `docs/BUILD.md`. Do **not** change the
NeiL app (`src/main.c`, `bma580*`, `rtc.c`, `TEMP118.c`), the board files, `prj.conf`, or anything in the workspace
`kneil_tinyml/` (that is the master copy, merged in E1). Never push. Never flash a board (the owner does that).

## Part A: library v2.0 into the firmware
1. Copy from workspace `main` (`kneil_tinyml/`): `include/*.h`, `src/kneil_*.c`, `tests/host_test.c`,
   `tests/kneil_test_vectors.h`, the zephyr Kconfig text. Keep the firmware's own folder layout. `tests/run_host_test.py`
   must print `HOST TEST: PASS (both models)`.
2. `docs/kneil_tinyml.md`: v2.0 / model V4 (classes, 4 s window, stairs rule, events, posture, summary format 2, RAM).
   Copy numbers from the workspace `kneil_tinyml/README.md` and `tasks/E1_report.md`; flash from Part D (measured).

## Part B: `kneil_live.c` and protocol version 2
1. Use the library for everything: `kneil_classifier_push()` (class after the stairs rule), `clf.raw_class`,
   `clf.vote`; remove the firmware's own `predict_proba` call and its own majority-of-3 code if the library gives the
   same; run `kneil_metrics_update()` on every window (one static `kneil_metrics_t`, reset at boot and by command).
   After lost samples: `kneil_classifier_init` only, **not** a metrics reset.
2. **LIVE v2** (version byte 2, **22 bytes**): offsets 0-19 as v1, but byte 8 = class **after the stairs rule** (0-7),
   byte 9 = smoothed class (0-7), byte 10 = vote share of the **raw** class in %; new byte 20 = raw class (argmax,
   before the rule; 255 = none); new byte 21 = event flags: bit0 sit-to-stand counted in this window, bit1 stand-to-sit,
   bit2 bed transfer, bits 4-5 posture state (0 unknown, 1 sitting, 2 standing). The window is 4 s; `t_ms` = its end.
3. **SUMMARY** (new optional characteristic `a8f50006-3e2c-4c6e-9b1a-6b4e45494c00`, notify): `uint8 type = 0x04`
   + the 40-byte `kneil_daily_summary_t` (format 2) = 41 bytes. Sent when the central subscribes, every 60 s while
   connected, and on CONTROL `0x13`. CONTROL `0x14` = reset the daily metrics (also sends one INFO line).
   If the MTU is below 44, send nothing and one INFO line saying why.
4. **Text lines**: `L,...` gains `,<raw_class>,<event_flags>` at the end (v2 only); new
   `D,<format>,<n_classes>,<min_0>,...,<min_7>,<min_sitting>,<min_standing>,<min_still_unknown>,<n_sts>,<n_s2s>,<n_bed>,<sts_s_x10>,<steps>,<cadence_x10>,<stairs_cadence_x10>,<sit_tilt_x10>`;
   PC commands `Q` (= 0x13) and `Z` (= 0x14). The bridge subscribes to SUMMARY if present.
5. C (`kneil_proto.c/.h`) and Python (`pc_app/kneil/protocol.py`) stay identical; both unit tests get the same new
   example packets (one LIVE v2, one SUMMARY). **Older parts keep working**: the PC app and the bridge still accept LIVE
   v1 (20 bytes, 9 classes, 2 s window); the app picks the class table and window length from the LIVE version.
6. `protocol/README.md`: version 2 section; v1 kept as history. INFO lines: firmware version (bump
   `KNEIL_FW_VERSION`), library version, model name and window from `kneil_model_info.h`.

## Part C: PC app (`pc_app/`)
- 8-class table for v2 (still = one colour; the posture state shown as text: sitting / standing / unknown). Truth keys
  stay as they are (the owner still marks sitting and standing): for v2 the confusion compares truth sitting/standing
  with device `still` + posture state; the window centre is 2 s before `t_ms` for v2 (1 s for v1).
- Events: count sit-to-stand / stand-to-sit / bed-transfer from the event flags (not from window runs) for v2, next to
  the truth events marked with the keys.
- Show the latest daily summary (decoded) and buttons for `Q` and `Z`. Recordings: write the new fields (raw class,
  event flags, D lines); old recordings must still load.
- `python -m unittest discover -s tests` passes (V3: 25 tests; add tests for v2 parsing, v1 back-compatibility,
  summary decode, and the confusion/event logic for v2).

## Part D: builds (measured, not estimated)
Use the installed nRF Connect SDK v3.1.0 (`C:\ncs`; see `docs/BUILD.md`). Find a non-interactive way to run `west`
in the toolchain environment (for example `nrfutil toolchain-manager launch --ncs-version v3.1.0 -- <command>` or the
toolchain's own environment script); if none works, stop this part and report the exact error.
1. KNEIL live build (`build_kneil`, `kneil.conf`, `--pristine=always`) with the forest; `rom_report` and `ram_report`:
   total flash and RAM, and the size of the forest/tree symbols. Same for `CONFIG_KNEIL_TINYML_MODEL_SMALL=y`.
2. Bridge build (`xiao_ble`). 3. Protocol unit test (gcc). 4. Host test. 5. PC app unit tests.
6. Compare flash and RAM with the V3 build (build `origin/main` fd74429 once in a separate build folder).

## Part E: workspace (branch `agent/E2` in `kneil_v4_agent`)
- `prompts/PROMPT_firmware_KNEIL_live.md` and `prompts/PROMPT_gui_KNEIL_live.md`: class table, 4 s window, LIVE v2,
  SUMMARY, new commands (the E1 report lists the lines).
- `docs/add_v3_model.py`: refuse to run if `kneil_tinyml/include/kneil_model_info.h` defines `KNEIL_MODEL_WIN_S`
  (prints why and exits 1). Test both cases on a scratch copy.

## Acceptance checks
1. Host test PASS in the firmware worktree; protocol unit test PASS; PC app tests OK (give the count).
2. KNEIL live build OK for forest and single tree; measured flash / RAM vs V3 (table); bridge build OK.
3. A replay test without hardware: feed 3 simulation CSV files (one walking, one sit-stand, one bed) through the host
   build of the library + `kneil_proto.c` LIVE/SUMMARY encoders, decode them with `protocol.py`, and show the decoded
   classes, event flags and the summary equal to `pipeline/metrics_ref.py` on the same files.
4. LIVE v1 example packets of the old tests still decode with the v1 table.
5. `git diff --stat origin/main...agent/E2` in the firmware worktree lists only allowed files.

## Not part of this task
Flashing, real-device tests, pushing, the NeiL app, retraining, `tools/train_kneil_tinyml.py` (say what it would need).
