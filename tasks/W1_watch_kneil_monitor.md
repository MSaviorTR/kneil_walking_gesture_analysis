# Task W1: KNEIL monitor on the Guder watch (watch = BLE central for the KNEIL implant)

Read `AGENTS.md` first. Two worktrees, as in E2:
- **Watch code**: `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\guder_watch_agent`, branch `agent/W1` (already created
  by the manager from the original repo, commit 65c5384). Read its `README.md`, `GUIDE.md`, `PROJECT_CONTEXT.md` and
  `ROADMAP.md` first. Commit all watch changes there.
- **Report**: `kneil_v4_agent`, new branch `agent/W1` from `main`; commit `tasks/W1_report.md` last.

Never push, never flash the watch (the owner does that), do not install packages (ESP-IDF is installed by the owner).

## Goal
The watch (Waveshare ESP32-S3-Touch-AMOLED-2.06, ESP-IDF v5.5.5, NimBLE) is the Güder lab's K+/pH readout. The owner
wants to use it **also** as a mobile monitor for the KNEIL implant: connect to the KNEIL device over BLE and show the
forest's decisions live, as the PC app does. **No data is saved.**

**Hard rule: the watch's current functionality must stay exactly as it is.** With the new mode not selected, the
firmware must behave as before: same default mode (*Phone + sensor*), same pages, same BLE roles, same logging,
alerts, USB console commands. Keep changes to existing files small and list each one with the reason in the report.

## KNEIL side (read only, from `..\kneil_firmware`, main 718301d)
`protocol/README.md` (protocol v2), `protocol/kneil_proto.h/.c` (C encoder/decoder), `pc_app/kneil/protocol.py`
(class names, colours, posture, events). Service `a8f50001-...`; LIVE `a8f50002` (22 B v2, 20 B v1), INFO `a8f50005`,
SUMMARY `a8f50006` (41 B), CONTROL `a8f50004` (0x12 self-test, 0x13 summary now, 0x14 reset day; 0x10/0x11 raw:
**do not use raw** here). Advertised name `KNEIL-xxxx`, service UUID in the scan response.

## Part A: protocol code
Copy `kneil_proto.h/.c` **unchanged** into a new component `components/kneil_proto/` (a header comment says where it
comes from and the source commit). Do not fork the logic: the watch must decode exactly like the bridge and the PC app.

## Part B: new BLE mode "KNEIL"
- Settings -> Mode gets a 4th option **KNEIL device** (not the default; the setting is stored like the other modes).
- In this mode: the phone peripheral and the Guder-sensor central are off; a KNEIL central scans for a name starting
  with `KNEIL-` or the KNEIL service UUID, connects (strongest RSSI), requests MTU 247, subscribes to LIVE, INFO and
  SUMMARY (SUMMARY optional: firmware v1 devices do not have it), and reconnects after a drop. Put it in a new file
  (`main/kneil_central.c/.h`); reuse patterns from `ble_central.c` but do not change the Guder central's behaviour.
- KNEIL data never enters the K+/pH pipeline, the logger or the alerts.

## Part C: KNEIL page (LVGL, `main/ui/ui_kneil.c`)
Shown only in KNEIL mode (as the first page). Contents:
- link: state (scanning / connecting / connected / lost), device name, RSSI, MTU, packets received, sequence gaps;
- **current class after the stairs rule** (large, v2 class colour) and the age of the last LIVE packet; the raw class
  and its vote share in %; the smoothed class; posture state (sitting / standing / unknown); protocol version
  (v1 devices: 9-class table, no posture/raw);
- event counters since connect from the LIVE event flags: sit-to-stand, stand-to-sit, bed transfer;
- a short history strip of the last 60 classes (one cell per LIVE packet, class colours);
- the latest daily summary (decoded: minutes per class, sitting/standing/unknown minutes, events, steps, cadence);
- the last INFO line (firmware, model, self-test);
- buttons: *Summary now* (0x13), *Self-test* (0x12), *Reset day* (0x14, with a confirm dialog).
The screen layout must fit the 410 x 502 AMOLED and use the existing UI style.

## Part D: USB console
New console commands (existing ones unchanged): `kneil` (status, one line) and `kneil lines on|off`: while on, print
every received LIVE / INFO / SUMMARY as the protocol's text lines (`L,...`, `I,...`, `D,...`, from `kneil_proto.c`),
so the PC can watch the same stream. Making the watch a full drop-in replacement of the XIAO bridge for the PC app is
**not** part of W1 (say in the report what it would need).

## Acceptance checks
1. Existing host tests (`test/host`) all pass, unchanged count (README says 66 checks). On Windows use Git Bash or
   MSYS2 gcc; if ASan/UBSan are not available, run without them and say so.
2. New host tests for the watch-side decoding: the LIVE v2, LIVE v1 and SUMMARY example packets from
   `kneil_firmware/protocol/test_kneil_proto.c` decode to the same fields and lines; the page model (the struct the UI
   reads) gets the right class, posture, event counts and history after a sequence of packets (including a sequence
   gap and a v1 device).
3. `idf.py build` passes with ESP-IDF v5.5.5 (the owner installs it; look for `C:\Espressif` or the VS Code ESP-IDF
   extension's install, and use its `export.ps1`). No new warnings in the files you did not touch. Flash and RAM size
   before / after (`idf.py size`). If ESP-IDF is not installed yet when you get here, do everything else, write the
   report with "partly done: waiting for ESP-IDF", and the manager will give you the rest.
4. UI simulator (`test/sim`): add a KNEIL scenario (connected, v2, walking with events and a summary; and "scanning")
   and save the screenshots under `test/sim/out/`; list the files in the report. If the simulator cannot run on Windows,
   say why.
5. Regression: `git diff --stat upstream/main...agent/W1` (run in `guder_watch_agent`; the remote is called `upstream`)
   and, for every existing file changed, one line why. Default mode unchanged in `sdkconfig.defaults` and the settings
   code.

## Not part of this task
Saving KNEIL data, raw streaming, PC-app bridge mode, pairing/security, changes to the KNEIL firmware or the PC app.
