# Task L1 (worker gemini): knee flexion and spacer loosening from the implant accelerometer (feasibility, analysis only)

Branch `gemini/L1`, new from `main`. Report `tasks/L1_report.md`, committed last. New code `pipeline/diag_flexion.py`
(version line, log); outputs under `cache\l1\` and `KNEIL_results\v4\stepH\` (new allowed folder for this task).
**Analysis only**: no chip, library or protocol change.

## Why (24 Nov 2026)
A physiotherapist told the owner to focus on **knee flexion** and **implant (spacer) loosening**. The watch gets a
seated-exercise therapy mode (task T1) that uses the seated knee angle from the tibia tilt. We have only a 3-axis
accelerometer, 50 Hz, +-8 g, in the tibial insert (2.5 cm below the joint centre, 5 mm anterior), no gyroscope, no
thigh sensor.

## Part A: knee flexion
1. **Seated angle** (the T1 method): shank pitch `theta = atan2(a_x, a_z)` after a low-pass, knee flexion
   `phi = 90 deg - (theta - theta_cal)`, `theta_cal` = pitch while sitting with the foot flat (knee about 90 deg).
   In the MuJoCo model (`pipeline/kneil_v1.py`, as the viewer uses it), simulate seated knee extension (90 -> 0 deg)
   and flexion (90 -> 120 deg) at 10-60 deg/s, thigh slope 0-15 deg, mount error +-10 deg about each axis. Angle
   error vs true knee angle: no calibration, 1-point (foot flat), 2-point (foot flat + leg straight). What filter cut-off
   and what |a| gate (dynamic acceleration) keep the error under 5 deg?
2. **Flexion in daily life**: can the tibia alone estimate knee range in gait (peak swing flexion) or the largest
   flexion of the day (sit-to-stand, stairs)? Use Camargo (real joint angles + `vimp` implant signal): relation of
   shank pitch range to knee flexion range, error per person, how many people.

## Part B: spacer loosening and other spacer complications
3. **Literature** (DOIs; measured numbers only): articulating knee spacer complications (dislocation, fracture,
   subsidence, loosening, tilt of the insert) with rates; how loosening is detected clinically; any study of
   loosening detection with an implanted or skin accelerometer, and the sample rates they needed.
4. **What our sensor could show**, each with a test on our data:
   - drift of the **standing tilt** (device orientation vs gravity in upright still windows) across days: the noise
     floor between sessions of the same person (repeated sessions in our datasets, if any; say which);
   - change of the **heel-strike shock** (peak |a|, jerk at initial contact) and of the mediolateral (y) sway in stance;
   - what is out of reach at 50 Hz (vibration analysis at kHz) and what a higher rate burst would need (the nRF54L15
     sensor's max rate is a question for the owner: list it as open).
5. A short list of **candidate daily metrics** for a future SUMMARY v3 (bytes each, how computed on the chip, minimum
   detectable change), marked "measured" or "assumed".

## Report
Plots and tables for 1-5, a one-screen summary for the owner, and the questions for the physiotherapist (what change
in flexion or tilt would matter clinically).
