# T1 report: home therapy mode on the watch (seated knee exercises with voice guidance)

## 1. Status

Done. The therapy mode is implemented, host-tested, built with ESP-IDF 6.1 and rendered in the simulator; no
hardware was flashed. The owner test plan is in Section 4.5.

## 2. Files

New (watch worktree `guder_watch_agent`, branch `agent/T1` from watch `main` 545d31b; two commits, not pushed):
- `main/therapy_config.h` — all therapy parameters, every one marked TBC by the physiotherapist.
- `main/therapy_angle.c`, `.h` — pure C: 2 Hz low-pass, `theta = atan2(a_x, a_z)`, seated
  `phi = 90 - scale*(theta - theta_cal)`, trust checks, 3 s sitting calibration and optional straight check.
- `main/therapy_session.c`, `.h` — pure C rep state machine: extension/bend, hold with beeps, full/partial reps,
  set rest, slow warning, gap/loss handling.
- `main/therapy.c`, `.h` — glue: RAW subscription, CONTROL 0x10/0x11, calibration/session, events to voice/log,
  background link tick, snapshot for the UI.
- `main/therapy_audio.c`, `.h` — ES8311/NS4150B through `esp_codec_dev`; queued playback; volume/mute in NVS;
  amplifier powered only between codec open and close; false return falls back to `haptics_tap()`/`haptics_alert()`.
- `main/therapy_log.c`, `.h` — `gw_therapy.csv` on the data logger's root (SD, else internal flash): one line per
  rep and one per session.
- `main/ui/ui_therapy.c` — full-screen therapy page (angle, target, arc, rep/set, counts, start/pause/stop,
  calibrate, straight check, exercise choice, safety text).
- `main/therapy_voice.bin` — 34 embedded PCM clips, 16 kHz mono 16-bit, 1,852,228 bytes (1.81 MiB).
- `main/therapy_voice.h`, `main/therapy_voice_data.h` — generated clip enum and offsets.
- `tools/voice_clips.csv`, `tools/make_voice_clips.py` — the text table and the offline SAPI generator.
- `test/host/test_therapy.c`, `test/sim/therapy_stub.c` — host tests and simulator stand-ins.

Modified (minimal upstream edits; listed one line each):
- `main/CMakeLists.txt` — new sources and `EMBED_FILES "therapy_voice.bin"`.
- `main/kneil_central.c`, `.h` — adds the RAW characteristic to discovery/subscription and a raw listener pointer;
  existing LIVE/INFO/SUMMARY/CONTROL behaviour is unchanged.
- `main/main.c` — `therapy_init()` after the logger/haptics and before BLE.
- `main/ui/ui.c`, `main/ui/ui_internal.h` — create/refresh the therapy screen.
- `main/ui/ui_kneil.c` — "Therapy" button on the KNEIL page only.
- `main/ui/ui_settings.c` — therapy voice volume slider and mute switch.
- `test/host/run.sh`, `test/sim/run.sh`, `test/sim/sim_main.c` — therapy tests and simulator scenario.

Workspace (`kneil_v4_agent`, branch `agent/T1` from `main`): `tasks/T1_report.md` (this file).
`dependencies.lock` was rewritten by the 6.1 build and is left uncommitted, as instructed (`idf 5.5.5 -> 6.1.0`,
lock `2.0.0 -> 3.0.0`, adds `espressif/usb 1.6.1`).

## 3. Commands

```powershell
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
cd guder_watch_agent
idf.py fullclean
idf.py build
idf.py size

& "C:\Program Files\Git\bin\bash.exe" -lc "cd guder_watch_agent/test/host && SAN= PYTHON=python ./run.sh"
& "C:\Program Files\Git\bin\bash.exe" -lc "cd guder_watch_agent/test/sim && ./run.sh"

C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe tools\make_voice_clips.py
```

The voice clips were generated once with the Windows speech engine; `main/therapy_voice.bin` and the two headers are
committed so the firmware builds without SAPI. Re-run the script after changing `tools/voice_clips.csv` or the rep
count.

## 4. Acceptance checks

### 4.1 Host tests with synthetic 50 Hz streams — PASS

`therapy tests: 51 checks, 0 failed` (`THERAPY TEST: PASS`), in addition to the existing suites:

```text
75/75 checks passed
app_state: 35/35 checks passed
kneil tests: 155 checks, 0 failed
therapy tests: 51 checks, 0 failed
contract: 200 emulator frames, 10% deliberately corrupted
ok=184 checksum_err=16 format_err=0 ignored=0
```

(The `ok`/`checksum_err` split varies per run by design; the corrupted fraction is 10 %.)

What the 51 checks cover:
- known angles: sitting (theta 0) -> phi 90, straight (theta 90) -> phi 0, 45 deg -> phi 45; **straightening lowers phi**;
- a 10 deg thigh/mount offset calibrated out; the optional straight check leaves scale 1 for 90 deg of travel;
- a failed calibration keeps the previous calibration;
- trust: |a| = 1.3 g and a large a_y are rejected; ±0.02 g noise keeps phi within 80-100 deg around sitting;
- clean extension rep (full, hold >= 5 s, peak near target);
- a 2 s hold counts partial, with its peak and hold time;
- a rep to 50 % of the range counts partial;
- ±2 deg jitter at the target for 5.2 s still counts full;
- a sequence gap and a mid-rep loss count no rep; bend exercise full rep; 100 deg/s movement raises the slow warning;
- 3 sets x 10 reps: set-done events, 30 s set rest, final `session complete`, 30 counted reps.

### 4.2 `idf.py build` (EIM profile, ESP-IDF 6.1) — PASS

- 0 errors; **0 warnings from the project's files**. The clean full build prints the same 11 pre-existing
  `Atomic_*_u32 defined but not used` warnings from the IDF FreeRTOS `atomic.h` as W5/W6.
- `guder_watch.bin`: **0x329b20 bytes** (3,316,512) after T1; before T1 (W6 main 545d31b) 0x155d50 (1,400,144);
  **+0x1D3DD0 = 1,916,368 bytes (1.83 MiB)**, of which the voice PCM is 1,852,228 bytes.
- App partition 0x800000 (8 MiB): **0x4d64e0 (5,072,096 bytes, 60.5 %) free**; bootloader 0x5850 unchanged;
  **no partition or flash-layout change**. `idf.py size` reports total image 3.3 MB (flash data 2.30 MB, code 0.90 MB),
  DIRAM 112.7 kB of 341.8 kB (33 %).
- `dependencies.lock` was rewritten by the build and is left uncommitted (see Section 2).

### 4.3 Simulator renders — PASS

All seven scenarios render, including the new `therapy` scenario:

- `test/sim/out/12_therapy_start.bmp` — start screen: 90 deg, target 10 deg, set 1/3, rep 1/10, safety text,
  Extension/Bend, Calibrate/Straight check, Start/Stop.
- `test/sim/out/13_therapy_rep.bmp` — during a rep: 11 deg, "Hold. 3 / 5 s.", rep 3/10, full/partial counts,
  Pause/Stop.
- `test/sim/out/14_therapy_set_complete.bmp` — set complete: "Set complete. Rest 24 s.", 10/10, counts.

The other six scenarios (`live`, `alert`, `demo`, `uncal`, `nodata`, `kneil`) still render; `01_face_therapy` and
the KNEIL screens are unchanged apart from the new KNEIL-page button.

### 4.4 RAW integration and safety behaviour (code audit) — PASS

- `kneil_central.c` now discovers and subscribes the existing RAW characteristic a8f50003, logs its handle, and
  passes decoded `kneil_raw_t` packets (any n up to 39, sequence number and t_ms) to the therapy listener. LIVE,
  INFO, SUMMARY and CONTROL order/behaviour is unchanged.
- `therapy` starts/stops RAW with the existing CONTROL queue: 0x10 on start/resume/calibrate, 0x11 on stop/pause/
  back/end-of-session. A background 500 ms tick detects link loss or 2 s without RAW, aborts the current rep,
  logs the session, and retries 0x11 as soon as the link is back. A BLE sequence gap resets the current rep.
- The angle is trusted only when | |a| - 1 g | < 0.15 g and |a_y| < 0.25 g; otherwise the screen says "Keep the leg
  straight ahead." The calibration step is 3 s sitting; the optional straight check only changes the scale in a
  plausible 45-135 deg range.
- The screen is reachable only from the KNEIL page; leaving it, Stop, Pause or the end of the session sends 0x11.
- The log writes one line per rep (date, time, exercise, set, rep, peak angle, hold, full/partial) and one session
  summary (sets, full, partial, best extension, best flexion, reason) to `gw_therapy.csv` under the existing
  data-logger root. `Clear logs` (`gw_*.csv`) removes it too.

### 4.5 One-page test plan for the owner (hardware) — PASS (written, not executed)

1. **Speaker wiring.** Connect a small 8 ohm speaker to the board's speaker connector (the BSP drives the ES8311 at
   I2C 0x18 and the NS4150B through GPIO46 `BSP_POWER_AMP_IO`). Check polarity and that the connector is the
   speaker, not the microphone. Boot the watch; the serial log should show `therapy-audio: speaker ready, volume 70`.
   If it says `speaker codec unavailable`, the therapy cues fall back to the vibration motor.
2. **Setup.** Set Bluetooth mode to KNEIL device, connect to the implant (the KNEIL page shows connected), open
   `Therapy`. Read the safety text: the watch guides only; stop at sharp pain; targets from the physiotherapist.
3. **Calibration.** Sit with the foot flat and the knee at about 90 deg; press Calibrate and keep still for 3 s.
   The angle should read about 90 deg. Then straighten the leg for the optional Straight check; the angle should
   fall towards 0 deg. Check the sign: straightening must lower the number. Repeat with the sensor mount slightly
   rotated (thigh offset) and confirm the calibrated angle still reads about 90/0.
4. **Extension session.** Press Start; follow "straighten your knee slowly"; hold at the target for 5 s and listen
   for one beep each second; lower slowly. Confirm rep 1/10 counts, then 10 reps, then "Set complete. Rest" for 30 s,
   then set 2 and 3; "Session complete" at the end. Try a 2 s hold and a movement to only half the range: both must
   count as partial with their peak angle in the log.
5. **Bend session.** Select Bend, start, slide the foot back towards 110 deg, hold and return; check the same
   counters and voice prompt.
6. **Stop paths.** Press Pause: RAW stops (implant log should show the 0x11 command / no RAW); Resume restarts with
   0x10. Press Stop; press Back; let a session finish: every path must stop RAW. Disconnect the implant mid-rep:
   the watch must say "Connection lost", count no rep, and send 0x11 when the link returns. Confirm no RAW
   notifications remain after the session.
7. **Volume and mute.** Settings -> Therapy voice volume and mute; check the next cue is quieter/silent and the
   settings survive a reboot. Check the vibration fallback with the speaker unplugged.
8. **Log.** Copy `gw_therapy.csv` from the SD card (or internal flash): one `rep` line per counted rep and one
   `session` line with best extension/flexion and full/partial counts. The clock should be set first; an unset clock
   writes its default date.
9. **Acceptance on hardware:** angle error <= 10 deg at the calibrated sitting and straight poses; 10 full reps per
   set for clean movements; no rep counted for sitting still or a sequence gap; no RAW left on after Stop/Back/end;
   no false "session complete"; audio intelligible at the default volume.

Open questions for the physiotherapist:
- Are the targets (extension 10 deg, flexion 110 deg), hold 5 s, 10 reps x 3 sets and 30 s set rest correct?
- Should a session do one exercise (as implemented, selected on the start screen) or alternate extension and bend
  sets? Which order?
- Is a partial rep (>= 50 % of the range or a short hold) acceptable, and should it count towards the 10?
- What is the correct rest pose/angle, and should the watch require the knee to return near 90 deg before the next
  rep?
- Is the slow-movement warning (> 30 deg/s) the right threshold and wording? Is the warning for too fast or too
  slow movement?
- Should the beep be every second during the hold or only at the start and end?
- What pain/red-flag wording should the watch say; should it stop the session on a pain report?
- Chair/weight-bearing restrictions, and whether the patient should use the operated leg only.
- Should the therapy data be a separate file (as now) or merged into the physiotherapist's log format?

## 5. Problems and open questions

1. **No hardware test.** Nothing was flashed. The speaker/NS4150B path, the actual I2S/codec at 16 kHz, the PA
   enable/disable, the microphone/speaker connector and the real angle signs are only audited and host-tested. The
   test plan above is the next step.
2. **0x11 on disconnect.** The watch cannot send a CONTROL byte while the BLE link is down. The current code marks
   the session lost, logs it, and sends 0x11 as soon as the link is back (background tick). If the implant keeps RAW
   running without a subscriber, it costs battery until reconnection; the implant firmware/log should confirm that
   RAW notifications stop on disconnect. This is the one path that does not literally send 0x11 at disconnect time.
3. **Voice size.** The 34 clips are 1.81 MiB and grow the app from 1.40 MB to 3.32 MB; 60.5 % of the 8 MB app
   partition is free and no partition change was needed. If the wording grows a lot, a data partition would be the
   next step; the script would then write a separate image instead of `EMBED_FILES`.
4. **Parameters are guesses.** Every value in `therapy_config.h` is marked TBC: targets, tolerances, hold, reps,
   sets, rest, partial fraction, slow threshold, trust limits. The state machine is deliberately simple and does not
   model co-contraction, pain or fatigue.
5. **Exercise order.** The screen lets the owner choose extension or bend before a session; the task did not specify
   whether a session should alternate. This is an open physiotherapy question (Section 4.5).
6. **Logging path.** The therapy log writes directly to `gw_therapy.csv` under `data_logger_root()` (its own file,
   own queue) because the existing logger writes one row per sensor reading, not arbitrary lines. `Clear logs`
   deletes it because it matches `gw_*.csv`. If the logger is not mounted, lines are dropped silently; the UI does
   not show a storage warning.
7. **Voice generation.** `tools/make_voice_clips.py` uses the Windows System.Speech voice; the exact voice and
   timing depend on the PC. The generated `.bin` and headers are committed so the firmware build is reproducible;
   only the WAV cache is not committed. The rep clips are generated for 1..20 with the current M = 10; the session
   uses 1..10.
8. **Angle assumptions.** The frame is the documented device frame (x anterior, y left, z superior); calibration
   removes a scalar sitting offset and (optionally) a scale error. A sensor mounted with a different axis convention
   is not handled; check that straightening lowers the displayed angle on hardware.
9. **KNEIL side effect.** RAW is now subscribed on every KNEIL connection (one extra CCCD write, no protocol change);
   if a device has no RAW characteristic, the watch logs a warning and the normal KNEIL page still works.
10. **No on-screen audio failure indicator.** If `bsp_audio_codec_speaker_init()` fails, the cues fall back to
    vibration but the screen does not say that the speaker is unavailable; the serial log does.
11. **Clock.** The therapy log uses `time()`; with the clock unset it writes the default date. Set the time first.
12. **No real patient data.** All host tests are synthetic; the angle/rep logic is not a validated clinical measure.
