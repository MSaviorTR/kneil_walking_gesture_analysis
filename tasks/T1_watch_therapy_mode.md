# Task T1 (worker deepseek): home therapy mode on the watch (seated knee exercises with voice guidance)

Watch worktree `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\guder_watch_agent`, new branch `agent/T1` from the watch
repo's `main` (`545d31b`; the folder `main/` makes `main` ambiguous: use
`git switch -c agent/T1 refs/heads/main --`; leave `dependencies.lock` uncommitted). Report `tasks/T1_report.md` on `agent/T1` from
`main` in `kneil_v4_agent`. Never push, never flash. Same rules as W1-W6: **Korhan's functions stay unchanged**;
new code in new files, minimal edits to upstream files (list each one in the report).

## Why (24 Nov 2026)
A physiotherapist asked for home support of knee exercises: patients sit and flex / extend the operated knee to
strengthen the muscles. The watch guides them by voice through its speaker and counts the repetitions.

## Facts (checked by the manager)
- **No chip or protocol change.** The implant already streams RAW 50 Hz samples (`int16 x, y, z` mg, n per packet,
  every 0.5 s) after CONTROL `0x10`; `0x11` stops it (`kneil_firmware/protocol/README.md`). Use the existing CONTROL
  queue (`kneil_ctrl_queue.c`). Handle any n (MTU) and sequence gaps.
- **Audio**: the board package has `bsp_audio_codec_speaker_init()` (I2S -> ES8311 codec at 0x18 -> NS4150B amplifier,
  PA pin `BSP_POWER_AMP_IO`) in `managed_components/waveshare__esp32_s3_touch_amoled_2_06`. Use it through
  `esp_codec_dev`; power the amplifier only while playing. The vibration motor (`haptics.c`) is the fallback.
- Device frame: x anterior, y left, z superior; sitting with the foot flat reads about (0, 0, +1 g).

## Do
1. **Knee angle** (`therapy_angle.c`, pure C, host-testable): low-pass (about 2 Hz) the RAW samples; shank pitch
   `theta = atan2(a_x, a_z)`; seated knee flexion `phi = 90 - (theta - theta_cal)` deg. Calibration: "sit with the
   foot flat, knee at a right angle, keep still" for 3 s -> `theta_cal`; optional 2nd point "leg straight" to check
   the scale. Trust the angle only when | |a| - 1 g | < 0.15 g and |a_y| is small (else "keep the leg straight
   ahead"). Check the sign on paper and in the tests: straightening the knee must lower `phi`.
2. **Exercises and rep counter** (`therapy_session.c`, pure C state machine, host-testable). Two exercises:
   **knee extension** (from about 90 deg towards the extension target) and **knee bend** (slide the foot back under the
   chair, towards the flexion target). States: rest -> moving -> at target (hold, beep each second) -> return ->
   rep counted. A rep that reaches >= 50 % of the range but not the target counts as partial, with its peak angle.
   Parameters in one table (`therapy_config.h`), **all marked "to be confirmed by the physiotherapist"**: targets
   (extension 10 deg, flexion 110 deg), hold 5 s, 10 reps x 3 sets, 30 s rest, slow-movement warning.
3. **Voice** (`therapy_audio.c`): short English clips: setup, calibrate, "straighten your knee slowly", "hold",
   "lower slowly", "rep N of M" (numbers 1-20), "set complete, rest", "bend your knee, slide your foot back",
   "session complete", "connection lost", "stop if you feel sharp pain", plus a beep. Generate them **offline** with
   the Windows speech engine (System.Speech / SAPI) by a script `tools/make_voice_clips.py` from one text table
   (`tools/voice_clips.csv`) so the wording can be changed and rebuilt; 16 kHz mono 16-bit; store in flash
   (embedded files or a data partition; report the size and the partition change if any). Volume and mute in the
   settings.
4. **Screen** (`ui_therapy.c`, only in KNEIL mode): big current angle, target, an arc gauge, rep / set counter, start /
   pause / stop buttons, calibration button. Starting a session sends `0x10`; leaving the page, stop, disconnect or
   the end of the session sends `0x11` (no RAW streaming left on, it costs the implant battery).
5. **Log** (SD, through the existing logger if possible): one line per rep (date, time, exercise, set, rep, peak angle,
   hold s, full/partial) and one summary line per session (best extension, best flexion, reps). These are the
   flexion trends the physiotherapist asked for.
6. Safety text on the start screen: the watch guides only; stop at sharp pain; targets come from the physiotherapist.

## Checks
1. Host tests with synthetic 50 Hz streams: angle and calibration (known angles, thigh offset, noise), rep counter
   (clean reps, too short hold, partial, jitter around the threshold, sequence gap, disconnect mid-rep). Counts.
2. `idf.py build` (EIM profile, IDF 6.1) with no new warnings; image size before/after; the flash and partition use.
3. Simulator renders of the therapy page (start, during a rep, set complete).
4. A one-page test plan for the owner on hardware (speaker wiring to the board's speaker connector, what to do, what
   to look for). List the open questions for the physiotherapist.
