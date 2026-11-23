# Task board (manager: Claude Code; workers: OpenCode / DeepSeek V4.1 Flash, Antigravity / Gemini)

How it works:
1. The manager writes `tasks/<id>_<name>.md` on `main` (goal, files, rules, acceptance checks) and points
   `tasks/NEXT.md` (on `main`) at it: `id`, `task`, `branch`, `base` (`main` = new branch from main, `existing` = keep
   working on that branch, e.g. for a fix).
2. The owner starts the worker once in the agent worktree `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_agent`
   with: *"Read AGENTS.md and follow it."*
3. The worker commits on its branch `agent/<id>`, commits `tasks/<id>_report.md` last, then runs
   `tasks/wait_for_task.ps1` (waits for a new id in `main:tasks/NEXT.md`, 9 min per call, repeated).
4. The manager's watcher sees the committed report; the manager reviews the diff, reruns the key checks, merges into
   `main` or writes `tasks/<id>_fix.md`, and updates `NEXT.md` (or writes `id: STOP`).

| Id | Task | Branch | State |
|---|---|---|---|
| D0 | [Window-length loaders + C feature check](D0_windows_and_loaders.md) | `agent/D0` | **merged** ([report](D0_report.md)) |
| D1 | [CV: 8 classes x window length x data variant](D1_cv_classes_windows.md) | `agent/D1` | **merged** ([report](D1_report.md)) |
| D2 | [Seeds, weight of new data, stairs evidence rule](D2_seeds_weight_stairs_rule.md) | `agent/D2` | **merged** ([report](D2_report.md)) |
| D3 | [Transition events + stairs rule v2 (F0.5)](D3_transition_events_rule_v2.md) | `agent/D3` | **merged** ([report](D3_report.md)) |
| E1 | [V4 export + chip library v2.0](E1_v4_export_library_v2.md) | `agent/E1` | **merged** ([report](E1_report.md)) |
| E2 | [V4 in the firmware, BLE protocol v2, PC app](E2_firmware_protocol_v2.md) | `agent/E2` (firmware repo + workspace) | **merged** ([report](E2_report.md), [fix report](E2_fix_report.md)) |
| W1 | [KNEIL monitor on the Guder watch](W1_watch_kneil_monitor.md) | `agent/W1` (watch repo + workspace) | code accepted ([report](W1_report.md), [fix report](W1_fix_report.md)); build in W2 |
| W2 | [Build the watch with the KNEIL mode](W2_watch_build.md) | `agent/W1` | **merged + pushed** ([report](W2_report.md), [fix report](W2_fix_report.md)) |
| W3 | [Wrong KNEIL service UUID on the watch](W3_uuid_fix.md) | `agent/W3` | **merged + pushed** ([report](W3_report.md)) |
| W4 | [Watch subscribes to the wrong CCCD](W4_cccd_fix.md) | `agent/W4` | **merged + pushed** ([report](W4_report.md)) |
| W5 | [Descriptor discovery start handle](W5_dsc_call_fix.md) | `agent/W5` | **merged + pushed** ([report](W5_report.md)) |
| V1 | [Figures: accuracy, data handling, future work](V1_figures.md) | `agent/V1` | **merged** ([report](V1_report.md), [fix report](V1_fix_report.md)) |
| V2 | [One overview figure (graphical abstract)](V2_overview_figure.md) | `agent/V2` | **merged** ([report](V2_report.md), [fix report](V2_fix_report.md)) |
| V2b | [Polish the overview figure (layout only)](V2b_overview_polish.md) | `agent/V2b` | **merged** ([report](V2b_report.md), [V2c report](V2c_report.md)) |
| G0 | [Gemini setup check](G0_gemini_setup_check.md) (worker gemini) | `gemini/G0` | **merged** ([report](G0_report.md)) |
| G1 | [Review of the watch's KNEIL BLE code](G1_review_watch_ble.md) (worker gemini, read only) | `gemini/G1` | **merged** ([report](G1_report.md)) |
| W6 | [Watch: fix the 9 review findings](W6_watch_review_fixes.md) | `agent/W6` | **merged + pushed** ([report](W6_report.md)) |
| V3 | [MuJoCo motion viewer + Blender renders](V3_mujoco_viewer.md) (worker gemini) | `gemini/V3` | **merged** ([report](V3_report.md)) |
| V3b | [Viewer fixes: scene alignment, Blender figure, in-sample labels](V3b_viewer_fixes.md) (worker gemini) | `gemini/V3b` | **merged** ([report](V3b_report.md)) |
| G2 | [Why walker / crutch gait is called still (analysis)](G2_walker_diagnosis.md) (worker gemini) | `gemini/G2` | given 23 Nov |
