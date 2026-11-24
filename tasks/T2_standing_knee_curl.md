# Task T2 (worker deepseek, after T1_fix): standing knee curl in the watch therapy mode + the L1 filter settings

Continue on `agent/T1` in `guder_watch_agent` (new commits). Report `tasks/T2_report.md` on `agent/T1` in
`kneil_v4_agent`, committed last. Never push, never flash.

## Why (24 Nov 2026)
The owner wants the exercise in the picture the owner sent: **standing knee curl**. The patient stands holding a chair, the
thigh stays vertical, the heel comes up behind (knee flexion about 20 -> 110 deg, about 10 reps in 70 s). With the thigh
vertical, knee flexion is the shank's backward tilt, so the implant alone measures it.

## Do
1. **Angle for standing**: same `theta = atan2(a_x, a_z)` and the same mount calibration `theta_cal` (shank vertical,
   from the seated foot-flat pose, or a new "stand tall, keep still" calibration: both have a vertical shank). Seated:
   `phi = 90 - (theta - theta_cal)`; **standing: `phi = -(theta - theta_cal)`** (heel back -> theta negative -> phi
   positive). Check the sign in the tests and with `pipeline/kneil_v1.py` if useful (L1 report A.1 has the frames).
   The screen says "keep your thigh still and upright"; the angle is only right while the thigh is vertical (say so).
2. **Third exercise "Standing knee curl"**: rest about 0-20 deg, target flexion (TBC 90 deg), hold 3 s (TBC), same rep /
   partial / set logic, its own voice clips ("Stand tall and hold the chair.", "Bend your knee, lift your heel behind
   you.", "Lower slowly.") added to `tools/voice_clips.csv`, clips regenerated.
3. **L1 filter result** (Gemini's MuJoCo study, `tasks/L1_report.md` A.1): the 2 Hz low-pass lags (95th-percentile
   error 12 deg at 60 deg/s); **6 Hz low-pass with a 0.05 g gate on | |a_raw| - 1 g |** (on the raw, not the filtered,
   magnitude) keeps it under 4 deg. Change `THERAPY_LOWPASS_HZ` to 6 and the gate as described; update the tests; keep
   the displayed number steady (a display-only smoothing is fine; the rep logic uses the 6 Hz angle).
4. Log: the exercise name in each rep line; the session line gives the best standing flexion too.

## Checks
Host tests (counts; standing angles 0 / 45 / 90 / 110 deg, sign, a thigh-tilt case to show the error), build with no
new warnings, image size, simulator render of the standing exercise, the updated hardware test plan section.
