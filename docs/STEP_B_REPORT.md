# Step B: Luo 2020 and Lencioni 2019 — what is in the files (16 Nov 2026)

Script: `pipeline/inspect_step_b.py` 1.0 with `pipeline/v4_readers.py` 1.0. Output and log:
`KNEIL_results\v4\stepB\` (`step_b_log.txt`, `luo_trials.csv`, `luo_sensor_map.csv`, `lencioni_strides.csv`,
`lencioni_subjects.csv`, `luo_person1_examples.png`). All numbers below are **measured** on all files unless marked
*paper* (from the paper, Europe PMC PMC7343872) or *assumption*.

## Luo et al. 2020 (30 people, outdoor, Xsens MTw)

| Item | Finding |
|---|---|
| Files | `data.mat` (MATLAB 7.3/HDF5, 3.8 GB) and raw per-trial CSVs `input data_SD\input data_SD\<person>\<trial>-000_<serial>.txt.csv` (+ `.mtb`). 30 people, 57 trials each, 6 sensors per trial, complete. |
| Sensors | trunk, thighR, thighL, **shankR, shankL**, wrist (not ankles in the sense of the foot). *Paper:* shank sensors "centered 5 cm above the bony processes of both ankles" (distal shank); thighs anterior; trunk at L5/S1; wrist dorsal forearm. |
| Serial -> position | Fixed for all 30 people (CSV vs .mat, r 0.80 vs next best 0.18): 00B4329B shankR, 00B432B6 shankL, 00B43293 thighR, 00B4328B thighL, 00B432CC trunk, 00B43295 wrist. |
| Trials / labels | Column `Surface` in the .mat tables: trials 1-3 CALIB, 4-9 FE (flat even), 10-15 CS (cobblestone), 16-27 StrU/StrD alternating, 28-39 SlpU/SlpD alternating, 40-51 BnkL/BnkR alternating, 52-57 GR (grass). 6 trials per surface per person. *Paper:* normal self-selected pace; stairs and slopes cement; geometry not surveyed. |
| Rate, units | 100 Hz (samples / TrialDuration = 100.0). Acc in **m/s²** (|a| at rest 9.83), Gyr in **rad/s** (p99 7.4). |
| .mat vs CSV | Same samples (PacketCounter). The .mat is **low-passed** (*paper:* 2nd-order Butterworth 6 Hz): raw r 0.80, after our 6 Hz on both r 0.991, lag 0. The CSV is the raw signal. |
| Gaps | Missing packets per shank trial: median 0 %, max 4.7 % (BnkR); no empty shank trial. thighL of person 5 is empty from trial 14 on. |
| Durations | Stairs 12 s (8.5-16), flat 13 s, slopes 23 s, banks 16 s, grass 14 s, CALIB 19 s. |
| Content (plot, person 1) | Every trial starts with ~1.5-2 s of standing still. Stairs trials are stairs from ~1.7 s to the end (no level part seen). CALIB: ~14 s standing, then movements (*paper:* trunk flexion, arm raise, right and left leg raise, 3 times each). |
| Sensor axes | Shank sensor x lies along the shank (+1.0 g in CALIB standing; *paper:* Acc_X "vertical"). y, z are not stated in the paper; `vimp.person_frame` sets the frame from data anyway. |

**Consequences for step C (Luo)**
- Use the **raw CSVs** (serial map above) for the signals and the .mat only for labels; then the chip's 6 Hz causal
  filter is the only filter, as for the other datasets.
- Lever arm *assumption:* sensor 5 cm above the malleolus -> implant 2.5 cm below the joint: shank length minus
  ~7.5 cm ≈ **0.31-0.36 m** (0.36 m as for PAMAP2 is consistent). Luo gives no body height in the files I read, so one
  value for all.
- Frame per person: z = gravity from the CALIB standing part (first ~14 s), y from FE walking (as planned).
- Stairs: 6 up + 6 down trials x 2 legs x 30 people ≈ 720 stair trials (≈ 2.5 h) — about 4x the people of PAMAP2.

## Lencioni et al. 2019 (50 people, lab motion capture)

| Item | Finding |
|---|---|
| Files | `All_Subjects\Subject1..50.mat` (MATLAB 5, struct `s`), `Demo_Anthro.xlsx` (code, sex, age, height, mass; agrees with the .mat within 0.5 cm). |
| People | Age 6-72; **21 of 50 are children (< 18)**. Marker rate 60 Hz (25 people) or 200 Hz (25). |
| **Data unit** | **One stride per entry, not continuous trials.** 1,615 strides; stride 0.85-1.9 s. Each entry: Task, Foot (RX/LX), Marker 87 x n, speed, cadence, stride length, TimeStampKin. |
| Tasks | Walking 844 strides (50 people), ToeWalking 278, HeelWalking 178, **StepUp 169 (43 people), StepDown 146 (43)**. |
| Stairs check | StepUp: pelvis rises 0.35 m per stride (two steps of ~17 cm), malleolus 0.17 m; StepDown -0.22 m. Real stairs, 0.49 m/s. |
| Speed labels | **None.** Only a measured speed per stride. Walking 0.29-2.29 m/s (median 1.20); within one person the range is 0.85 m/s (median), so several speeds were walked. |
| Markers | 29 markers x XYZ in **metres, Y up**. Tibia: **FH (fibular head), Shank (wand), LatMal**; knee: **LatCon**. Lateral only, **no medial markers**. No gaps in these 4 markers in any stride. Shank length FH-LatMal = 0.207 x height. `StandingData`: one static frame. |

**Consequences for step C (Lencioni) — needs your decision**
1. **Strides, not recordings.** Chip windows are 2-5 s; one stride is ~1.1 s. I cannot see which strides came from the
   same pass (TimeStampKin repeats between passes). Options:
   - (a) *Periodic extension:* repeat each stride to fill a window (the stride is one gait cycle, so the joint is
     small). Test the bias first on Camargo: features of periodised single strides vs the real continuous windows.
   - (b) Use Lencioni only as a **test set** of per-stride features (speed effect, stairs vs walking), not for training.
   - (c) Leave Lencioni out of training; Luo alone covers real stairs.
   My recommendation: (a) with the Camargo bias check, and (b) in any case.
2. **Implant point from lateral markers.** FH, Shank and LatMal give a rigid tibia frame. The knee centre lies medial
   of LatCon by half the knee width, which is not measured (*assumption:* ~0.05 x height). The error only enters
   through the rotation terms (r ≈ 4 cm), small next to the 0.3 m lever arms used elsewhere.
3. **Speed classes** must be made by us: absolute bins (e.g. < 1.0, 1.0-1.4, > 1.4 m/s) and/or relative to each
   person's median (< 0.85x slow, > 1.15x fast). Store the speed per stride either way.
4. **Children:** keep (more people, more speeds) or drop (the KNEIL patients are adults)? I suggest store all, train
   on adults (29 people) first, and test the children separately.
5. 60 Hz markers: acceleration by double differentiation needs a low-pass before; the chip uses 6 Hz, so a 6-8 Hz
   zero-lag filter on positions is enough (Nyquist 30 Hz).
