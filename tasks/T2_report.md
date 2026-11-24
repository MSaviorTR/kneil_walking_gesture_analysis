# T2 report: standing knee curl and the L1 angle filter

## 1. Status

Done. The watch therapy mode now has a third exercise, **Standing knee curl**, using the standing formula
`phi = -(theta - theta_cal)`, a stand-tall calibration, its own voice cues, the L1 A.1 6 Hz / 0.05 g filter and
the standing fields in `gw_therapy.csv`. Host tests, the clean ESP-IDF build and the simulator pass. Nothing was
pushed or flashed.

## 2. Files changed (agent/T1 in guder_watch_agent, commit 55364fa)

- `main/therapy_angle.c/.h` — seated/standing mode, `THERAPY_CAL_STAND`, standing `phi`, 6 Hz filter, 0.05 g
  gate on the **raw** magnitude, 2 Hz display-only smoothing (`phi_display`), stand-tall calibration.
- `main/therapy_config.h` — `THERAPY_LOWPASS_HZ 6.0`, `THERAPY_DISPLAY_HZ 2.0`, `THERAPY_TRUST_DY_G 0.05`,
  `THERAPY_CURL_REST_DEG 10`, `THERAPY_CURL_TARGET_DEG 90`, `THERAPY_CURL_HOLD_SECONDS 3` (all TBC).
- `main/therapy_session.c/.h` — `THERAPY_EX_CURL`, `THERAPY_EV_PROMPT_CURL`, per-exercise rest/target/hold;
  same rep/partial/set logic for all three exercises; snapshot gains `rest` and `hold_goal`.
- `main/therapy.c/.h` — selects the standing formula at session start, resets the filter on start/resume,
  plays the curl setup/bend/lower cues, plays the stand calibration cue, logs `standing_curl`, reports the best
  standing flexion in the session line, snapshot gains `rest`, `hold_goal`, `cal_mode`.
- `main/therapy_log.c/.h` — session line prints `best standing flexion` for the standing curl.
- `main/ui/ui_therapy.c` — third exercise button "Standing", note "Standing: keep your thigh still and upright.
  The angle is only right while the thigh is vertical.", "Stand cal" button, curl-specific prompts, per-exercise
  target and hold time.
- `main/therapy_voice.bin/.h/_data.h` — regenerated: **38 clips, 2,273,118 bytes**, 71.0 s.
- `tools/voice_clips.csv` — `curl_setup`, `curl_bend`, `calibrate_stand`.
- `test/host/test_therapy.c` — standing angle/sign/thigh-tilt/display tests and the standing-curl session test.
- `test/sim/sim_main.c`, `test/sim/therapy_stub.c` — standing render and stand-calibration state.

Workspace (`kneil_v4_agent`, `agent/T1`): `tasks/T2_report.md` (this file), committed last.
`dependencies.lock` remains modified by the 6.1 build and uncommitted, as before.

## 3. Commands

```powershell
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
cd guder_watch_agent
idf.py fullclean
idf.py build

& "C:\Program Files\Git\bin\bash.exe" -lc "cd guder_watch_agent/test/host && SAN= PYTHON=python ./run.sh"
& "C:\Program Files\Git\bin\bash.exe" -lc "cd guder_watch_agent/test/sim && ./run.sh"

C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe tools\make_voice_clips.py
```

## 4. Acceptance checks

### 4.1 Angle model and sign — PASS

The device frame and sign come from L1 report A.1 (lines 38–42): at a vertical shank `a=(0,0,+1)` and
`theta=0`; a straight seated leg gives `a=(+1,0,0)` and `theta=+90`. Standing with the heel behind tilts the
shank backward, so `theta` is negative and the standing flexion `phi = -(theta - theta_cal)` is positive.

Host tests:
- standing calibration at `theta=0`, then `theta = 0, -45, -90, -110` reads `phi = 0, 45, 90, 110 deg`
  (within 2 deg at each point);
- the 45 deg point also checks `theta < 0` and `phi > 0` (heel back = positive flexion);
- **thigh-tilt error**: after a stand-tall calibration, a 10 deg thigh lean with the knee unchanged reads
  10 deg of apparent flexion, so the 1:1 error is visible and documented (the screen says the thigh must be
  upright);
- the seated formula is unchanged (`theta=90` -> `phi=0`).

I did not run `pipeline/kneil_v1.py`: it is the synthetic **walking** generator in `kneil_v4_agent`; the
standing sign is taken directly from the L1 A.1 static frames above and locked by the tests.

### 4.2 Filter (L1 A.1) — PASS

- `THERAPY_LOWPASS_HZ` changed `2 -> 6` for the angle used by the rep logic.
- The gate is `| |a_raw| - 1 g | < 0.05 g` on the **raw** magnitude (`raw_magnitude_g`), before filtering; a
  test shows a single 1.1 g sample is rejected at once while the filtered magnitude is still within 0.1 g of 1.
- The shown number uses a separate 2 Hz low-pass (`phi_display`); the rep logic and peak/hold detection use the
  6 Hz `phi_deg`. A test confirms the displayed range is smaller than the 6 Hz angle range under the same jitter.

### 4.3 Host tests — PASS

```text
75/75 checks passed
app_state: 35/35 checks passed
kneil tests: 155 checks, 0 failed
KNEIL TEST: PASS
therapy tests: 83 checks, 0 failed
THERAPY TEST: PASS
contract: 200 emulator frames, 10% deliberately corrupted
ok=178 checksum_err=22 format_err=0 ignored=0
```

The therapy suite grew 60 -> **83** checks (the contract split varies per run by design). New checks:
standing calibration, 0/45/90/110 and sign (10), thigh-tilt error (1), raw-magnitude gate (3), display
smoothing (1), and a complete standing-curl repetition with rest 10 / target 90 / 3 s hold (9).

### 4.4 Build, warnings, size — PASS

- `idf.py fullclean; idf.py build`: 0 errors, **0 project warnings**; only the same 11 pre-existing IDF
  FreeRTOS `atomic.h` `-Wunused-function` warnings as W5/W6/T1/T1_fix.
- Image: `0x3912d0` (`3,740,368 B`). T1_fix was `0x35ef60` (`3,534,688 B`); delta **`0x32370` = 205,680 B**,
  of which **203,932 B** is the regenerated voice data (2,069,186 -> 2,273,118 B, +3 clips and re-encoded
  offsets). Project code adds about 1.7 KB.
- App partition `0x800000`: **`0x46ed30` (4,648,240 B, 55.4 %) free**; bootloader `0x5850`; no partition change.

### 4.5 Simulator — PASS

All seven scenarios render. Therapy images:
- `test/sim/out/12_therapy_start.bmp` — three exercise buttons (Extension / Bend / Standing), note and targets.
- `test/sim/out/13_therapy_rep.bmp` — seated hold.
- `test/sim/out/14_therapy_set_complete.bmp` — set rest.
- `test/sim/out/15_therapy_warnings.bmp` — speaker-off/log-not-saved line.
- `test/sim/out/16_therapy_standing.bmp` — **standing curl**: Standing selected, 88 deg, target 90 deg,
  set 1/3 rep 4/10, "Hold. 2 / 3 s.", thigh-upright note, Stand cal button visible.

### 4.6 Logging — PASS

`gw_therapy.csv`:
- every rep line carries the exercise name (`extension`, `bend` or `standing_curl`);
- the session line prints `best extension` and, for the standing curl, `best standing flexion` (the highest
  standing `phi` reached); the seated session line still prints `best flexion`.

## 5. Hardware test plan (updated)

The T1 plan in `tasks/T1_report.md` still applies. For T2 add:

1. **Stand-tall calibration**: stand tall, press **Stand cal**, keep still. The displayed angle should sit near
   0 deg; pressing **Sit cal** from the seated foot-flat pose must give the same result (both shanks vertical).
2. **Sign**: select **Standing**, hold the chair, lift the heel behind. The angle must rise (about 10 -> 90),
   not fall. A heel lift of about 45 deg should read about 45 deg.
3. **Thigh upright**: repeat a few reps leaning the thigh forward/back by 10 deg; the reading shifts by about
   10 deg in the same direction, so the patient must keep the thigh still and upright (screen note).
4. **Hold and target**: the standing curl should hold 3 s (not the seated 5 s) and count a full rep at 90 deg;
   a half-height heel lift (about 50 deg) should count as partial.
5. **Filter**: move at a normal curl speed and at a deliberately fast speed; the 6 Hz angle should not lag like
   the old 2 Hz value, and the slow-movement cue should still fire above 30 deg/s.
6. **Voice**: at session start hear "Stand tall and hold the chair." then "Bend your knee, lift your heel behind
   you."; on the return "Lower slowly."; the stand calibration says "Stand tall and keep still."
7. **Log**: after a curl session the rep lines say `standing_curl` and the session line gives the best standing
   flexion.
8. The standing/curl values (rest 10, target 90, hold 3 s, tolerances, slow threshold) are TBC and need the
   physiotherapist's confirmation.

## 6. Problems and open questions

1. **No hardware test.** The standing sign, stand calibration, voice set and 3 s hold are verified in code,
   host tests and the simulator only; the watch test plan in Section 5 is the real validation.
2. **Thigh vertical is an assumption.** With one tibial sensor, thigh tilt adds 1:1 to the standing angle;
   the 10 deg test demonstrates the error. The screen warns the patient; a thigh sensor is the only real fix.
3. **Calibration equivalence.** Stand-tall and seated foot-flat both assume a vertical shank, so either sets
   `theta_cal`; the stand calibration exists so the patient can calibrate in the exercise posture.
4. **Straight check stays seated-only.** It is optional and its 90 deg travel/sign check applies to the seated
   foot-flat pose; the standing exercise does not use it for scaling (there is no scale, per T1_fix).
5. **Parameters TBC.** Curl rest 10, target 90, hold 3 s, the 30 deg/s slow threshold and all target windows
   are still first guesses in `therapy_config.h`.
6. **Voice size.** The clips are now 2.27 MB (38 clips). The image is 3.74 MB with 55 % of the 8 MB app
   partition free; no partition change was made.
7. **The screen still shows `best ext` / `flex` for the standing exercise** in the compact counter line; this is
   the same min/max pair, labelled in the log as `best standing flexion`. If the physiotherapist prefers, the
   UI wording can be changed to `best flex` for the curl.
8. `dependencies.lock` remains rewritten by the 6.1 build and is not committed.
