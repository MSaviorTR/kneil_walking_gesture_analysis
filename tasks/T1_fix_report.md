# T1_fix report: manager review fixes for the watch therapy mode

## 1. Status

Done. All six review findings are fixed on `agent/T1`; host tests (60), the ESP-IDF 6.1 build and the simulator
pass. No hardware was flashed.

## 2. Files

Changed on `guder_watch_agent` `agent/T1` (new commit `80c0293`, plus the comment-only `608826a`):
- `main/kneil_central.c`, `.h` — reset `idx_raw` on connect/disconnect; raw-owner flag; after the subscriptions,
  queue CONTROL 0x11 once when no therapy session/calibration owns RAW.
- `main/kneil_raw_policy.c`, `.h` — **new**, pure `kneil_raw_stop_on_connect(connected, raw_owner_active)`.
- `main/therapy.c`, `.h` — set/clear the central raw-owner flag at start/resume/calibrate/stop/pause/lost/done;
  refuse a session when the straight check found the wrong orientation; log/show the straight-check extension;
  snapshot `orientation_ok`, `straight_extension_deg`, `log_ready`.
- `main/therapy_angle.c`, `.h` — scale is now always 1 (no rescale); the straight check records the reached
  extension and checks the sign; new `orientation_ok`/`straight_extension_deg`.
- `main/therapy_config.h` — `THERAPY_STRAIGHT_MIN_TRAVEL_DEG` (TBC).
- `main/therapy_log.c`, `.h` — `therapy_log_straight()` and `therapy_log_available()`.
- `main/ui/ui_therapy.c` — straight extension in the counts line; start disabled when not calibrated / wrong
  orientation / no link; orientation warning; "Speaker off: vibration cues" and "Log not saved" line.
- `main/therapy_voice.bin`, `main/therapy_voice.h`, `main/therapy_voice_data.h` — regenerated clips: new
  connection/slow wording plus `orientation_bad`. New size **2,069,186 bytes** (35 clips, 64.7 s).
- `tools/voice_clips.csv` — connection-lost, slow and orientation-bad rows.
- `test/host/test_therapy.c`, `test/host/run.sh` — straight-check tests without rescale, wrong-sign orientation,
  and the raw-stop-on-connect policy; therapy suite 51 -> **60 checks**.
- `test/sim/sim_main.c`, `test/sim/therapy_stub.c` — warning render, audio/log-ready fake state.

Workspace (`kneil_v4_agent`, `agent/T1`): `tasks/T1_fix_report.md` (this file), committed last.
`dependencies.lock` remains uncommitted (6.1 build rewrite as before).

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

## 4. Acceptance checks

### 4.1 Host tests — PASS

```text
75/75 checks passed
app_state: 35/35 checks passed
kneil tests: 155 checks, 0 failed
therapy tests: 60 checks, 0 failed
THERAPY TEST: PASS
contract: 200 emulator frames, 10% deliberately corrupted
ok=175 checksum_err=25 format_err=0 ignored=0
```

New checks for the review findings (the contract split varies per run by design):
- F2: `connected + idle -> stop once`, `connected + session/calibration -> no stop`, `disconnected -> no stop`
  (`kneil_raw_stop_on_connect`).
- F3: a patient reaching only 20 deg reads **20 deg** (not rescaled to 0), `straight_extension_deg` is 20, and a
  straight check with the wrong sign sets `orientation_ok = false`; the session start condition refuses it.
- F1 (`idx_raw`) is in the BLE central, not host-testable; it is a code change (line ranges below) covered by the
  build and static audit.

### 4.2 Build, warnings, size — PASS

- Clean full build (`idf.py fullclean; idf.py build`): 0 errors, **0 project warnings**; the same 11 pre-existing
  IDF FreeRTOS `atomic.h` warnings as W5/W6/T1. Incremental final build: 0 warnings.
- T1 image before this fix: `0x329b20` (3,316,512 B). T1_fix: **`0x35ef60`** (3,534,688 B), delta
  **`0x35440` = 218,176 B**, almost all of it the regenerated voice data (1,852,228 -> 2,069,186 B, +216,958 B).
- App partition 0x800000: **0x4a10a0 (4,853,920 B, 57.9 %) free**; bootloader 0x5850, **no partition change**.
- The new voice clips are still embedded with `EMBED_FILES`; no data partition.

### 4.3 Simulator — PASS

All seven scenarios render. Therapy images:
- `test/sim/out/12_therapy_start.bmp` — start: 90 deg, target 10, set 1/3, rep 1/10, safety text.
- `test/sim/out/13_therapy_rep.bmp` — during rep: 11 deg, "Hold. 3 / 5 s.", rep 3/10.
- `test/sim/out/14_therapy_set_complete.bmp` — "Set complete. Rest 24 s.", 10/10.
- `test/sim/out/15_therapy_warnings.bmp` — speaker-off/log-not-saved line, straight check = 18 deg.

### 4.4 Finding-by-finding result and changed line ranges — PASS

| Finding | Result | Changed lines |
|---|---|---|
| **F1 `idx_raw`** | reset on both reconnects | `main/kneil_central.c:789-793` (CONNECT) and `:828-832` (DISCONNECT); `on_reset` at `:988-991` was already correct |
| **F2 RAW left on** | new-connection 0x11 when therapy idle; raw owner set/clear | `main/kneil_raw_policy.c:1-5`; `main/kneil_raw_policy.h:1-13`; `main/kneil_central.c:96,380-390,1065-1070`; `main/kneil_central.h:43-48`; `main/therapy.c:57-70,348-355,393-399,440-446`; `test/host/test_therapy.c:329-336,349`; `test/host/run.sh:31` |
| **F3 straight check** | scale always 1; sign check + extension; refuse wrong orientation | `main/therapy_angle.c:109-140`; `main/therapy_angle.h:39-54`; `main/therapy_config.h:24`; `main/therapy.c:149-172,332-336,514-524`; `main/ui/ui_therapy.c:239-242,300-306,324-330`; `test/host/test_therapy.c:77-107` |
| **F4 connection wording** | "Connection lost. Rest for a moment; the watch will reconnect." | `tools/voice_clips.csv:13`; regenerated `main/therapy_voice.bin/.h/_data.h`; `main/ui/ui_therapy.c:232` |
| **F5 visible warnings** | "Speaker off: vibration cues" / "Log not saved" line | `main/therapy.h:52-59`; `main/therapy_log.c:116-131`; `main/therapy_log.h:17,20`; `main/therapy.c:524`; `main/ui/ui_therapy.c:20,182-185,340-360`; `test/sim/sim_main.c:537-548`; `test/sim/therapy_stub.c:26-27` |
| **F6 slow wording** | "Too fast. Move slowly and smoothly." | `tools/voice_clips.csv:10`; regenerated voice data |

Details:
- **F1:** `idx_raw` is now in both `idx_live = idx_raw = idx_info = idx_summary = -1` lines in `gap_event`; a
  device without RAW cannot inherit a stale slot after a device with RAW.
- **F2:** `kneil_central_set_raw_owner(true)` is set after 0x10 succeeds for start, resume and calibration;
  `stop_raw_locked()` / pause / stop / loss / session done / calibration end clear it. After each connection's
  subscriptions, `kneil_raw_stop_on_connect(connected, raw_owner_active)` queues **one** 0x11 if the watch is idle.
  The pure policy is host-tested (three cases).
- **F3:** `therapy_angle` no longer changes `scale`; the straight check computes `travel = mean(theta) - theta_cal`
  and sets `orientation_ok = travel > THERAPY_STRAIGHT_MIN_TRAVEL_DEG` (10 deg, TBC), with
  `straight_extension_deg = 90 - travel`. The extension is written to `gw_therapy.csv`, shown in the counts line
  (`straight 18` in the simulator), and a wrong sign shows "Sensor orientation not as expected. Check the watch.",
  plays the new orientation clip, disables Start and `therapy_start()` returns false.
- **F4:** the lost-session screen text and the voice clip both use the new reassuring wording.
- **F5:** the therapy page shows a warning line when `audio_ready` is false and/or `log_ready` is false;
  `therapy_log_available()` reads the existing data logger root. The simulator warning render shows both.
- **F6:** the slow cue now says the movement is too fast; the state machine already emitted the warning above
  30 deg/s.

### 4.5 Test plan — unchanged from T1 Section 4.5, with two additions

The hardware test plan in `tasks/T1_report.md` still applies. Add:
- After the straight check, confirm the displayed **straight extension** is the patient's real reached angle (e.g.
  "straight 18") and that a deliberately reversed sensor orientation gives the orientation warning and refuses to
  start a session.
- With the speaker unplugged and with no SD card/internal log root, the therapy page must show
  "Speaker off: vibration cues" and/or "Log not saved"; the session must still work with vibration.

## 5. Problems and open questions

1. **No hardware test.** The speaker/codec/PA path, the new voice wording and the warning line are not verified on
   the watch; the owner's test plan remains the validation.
2. **F2 is a best-effort stop.** The 0x11 is queued after the subscriptions of every new connection when the watch is
   idle. If the CONTROL queue is full the byte is dropped (the queue normally has room); the implant's own log should
   confirm RAW is off. A running session keeps the raw owner and is not stopped.
3. **Straight check is optional.** If the patient skips it, `orientation_ok` starts true and a session is allowed;
   only a performed straight check can refuse the session. That matches the task's "optional 2nd point", but the
   physiotherapist may want it mandatory.
4. **Straight-check meaning.** The shown value is the reached seated flexion `phi` (20 means 20 deg away from
   straight, i.e. an extension lag of 20 deg). Confirm the physiotherapist's preferred sign/wording.
5. **Voice size.** Regenerating the clips grew them from 1.81 to 2.07 MiB; the app is 3.53 MB and the 8 MB app
   partition is 58 % free. No partition change; a future data partition is still an option.
6. **Warning line is a single line.** If both the speaker and the log are unavailable it reads "Speaker off:
   vibration cues. Log not saved."; otherwise only the relevant part. It does not retry the speaker.
7. **Log availability** means the data logger's root is mounted; a mounted but full/failed write is not detected by
   the warning line (the existing write code reports failures only in the logger status).
8. **Parameters remain TBC.** Targets, hold, reps, sets, rest, partial fraction, slow threshold, trust limits and
   the new 10 deg straight-travel minimum are all marked in `therapy_config.h`; the physiotherapist must confirm.
9. **Exercise order** remains an open question (one selected exercise per session, as implemented).
10. `dependencies.lock` remains rewritten by the 6.1 build and is not committed.
