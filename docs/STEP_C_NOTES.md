# Step C: generators for Luo and Lencioni (16 Nov 2026)

## Final (full run, `stage2_v4 1.1`)
Decisions (owner, 16 Nov): **Luo lever arm 0.26 m** for everybody; **Lencioni stairs test only** (index column `role`:
train = walking stride leg, test = stairs stride leg, other = rest). Output `KNEIL_results\v4\stage2\{Luo,Lencioni}\`,
`stage2_index_{Luo,Lencioni}.csv`; logs `KNEIL_results\v4\stepC\stage2_v4_log.txt`, `check_step_c_log.txt`.

| | Luo | Lencioni |
|---|---|---|
| People / recordings | 30 people, 3,420 trial-legs, 0 flagged, 0 failures, no gyro sign inversion | 50 people (21 children), 3,230 stride-legs, 0 flagged |
| Windows (2 s, 1 s hop) | 51,086: walking 24,816; slopes 15,262; **stairs up 3,946, down 3,724**; calibration 2,346; standing 766 | 21,984 (periodised; several per stride) |
| Level-walking lean | 15.8-16.2 deg median (range 10.4-27.6 over people and legs) | 18.5 deg (stride leg) |
| Walking std of |a| | FE 0.34 g, other surfaces 0.36-0.39 g (stride ~1.0 s) | slow 0.12 / comfortable 0.20 / fast 0.32 g |

Measured feature pattern relevant to the device problem (fast walking called stairs):
- Lencioni walking by speed class: tilt 16.3 (slow) -> 17.8 -> **20.8 deg (fast)**; std |a| 0.12 -> 0.20 -> 0.32 g.
  Stairs up (stride leg): tilt **23.3 deg**, std |a| 0.14 g. So fast walking moves toward stairs in tilt.
- Luo: flat 16.4 deg vs stairs up 23.3 / down 25.9 deg; slope down 22.8 deg (close to stairs).

---
# Subset results (before the decisions)

Code: `pipeline/stage2_v4.py` 1.0 (generators), `check_step_c.py`, `check_periodise.py`, `diag_luo_lean.py`,
`diag_luo_intensity.py`, `diag_lever_arm_camargo.py`. Subset test: Luo people 1-2, Lencioni subjects 1-3, written to
`cache\test_v4` (not to the V4 results). Logs and CSVs kept in `KNEIL_results\v4\stepC\subset_test\`.
**Full generators not run yet** (waiting for the decisions at the end).

## What the generators do
- **Luo:** raw CSV (serial map) -> `vimp` with one frame per person and leg (up from CALIB standing, forward from FE
  walking); per sample still -> standing, else the surface label (FE/CS/GR/banks -> walking, StrU/StrD -> stairs,
  SlpU/SlpD -> slope_up/down, CALIB -> calibration). Wrist kept. Gyroscope sign retry as for MHEALTH (not needed so far).
- **Lencioni:** markers -> tibia frame (FH/LatCon/LatMal, pelvis left-right), implant point = knee centre (LatCon + medial
  0.028 x height) - 2.5 cm + 5 mm anterior; each stride periodised (detrend, 7 cycles, 8 Hz zero-lag, d²/dt²), both legs
  (`stride_leg` marks the leg that defines the cycle); speed classes stored absolute (< 1.0 / > 1.4 m/s) and relative
  (< 0.85x / > 1.15x person median); `adult` flag (children kept).
- **Lean rule** (-5..+35 deg) now applied to **level walking only**, per person and leg: stairs and slopes down
  legitimately lean 35-50 deg (first version flagged them wrongly).

## Measured (subset unless stated)
| Check | Result |
|---|---|
| Luo walking lean | 21-27 deg per leg. Diagnosis (6 people): CALIB 'up' vs trial-start 'up' differ by 1.3 deg -> not calibration; lean 13 deg without transfer, 16 at 0.20 m, 20 at 0.36 m -> the transfer removes the ankle's centripetal term (physics). Lencioni (markers, no lever arm) 16-17 deg, Caicedo 17. |
| Periodising (Camargo, 3 people, 8,563 windows) | **Walking: OK for 2-5 s windows** — feature change ≤ the change to the next real window (score 0.3-1.3), bias ≤ 0.07 IQR except ptp/max |a| (-0.15 IQR at 4-5 s). **Stairs: not proven** (only 16 up / 6 down 2 s windows: Camargo staircases are short); bias up to 0.4-0.9 IQR in mean_x, trend_x, tilt. |
| Lencioni stairs | Stride leg: lean up 19.5 / down 29.8 deg; other leg 28.7 / 43.9 (its cycle is not a full stair cycle). Loop kink (velocity mismatch end vs start) walking 0.15-0.24 m/s, stairs down ~1 m/s (not a steady cycle). |
| Lencioni speed | Features change with speed as expected (std |a| 0.15 slow / 0.19 comfortable / 0.29 fast g; ac_m_05s -0.03 / 0.17 / 0.40). |
| **Luo intensity** | **std |a| 0.57 g, ptp 2.8 g** while walking (FE) vs Camargo vimp 0.20 g level ground / 0.35 g treadmill (stride 1.03 s), Lencioni 0.19 g. Luo people walk fast (stride 1.01 s), so ~0.35 g is expected. |
| Luo intensity vs lever arm (4 people) | 0.50 g at 0 m, 0.36 at 0.10, **0.33 at 0.20 (minimum)**, 0.40 at 0.28, 0.54 at 0.36 m. Gyro low-pass 6 instead of 15 Hz: 0.50 (not the cause). |
| Camargo: lever arm truth (2 people, 9 trials) | true d 0.277 m; best r with the replay at 0.26-0.28 m; **lowest intensity 0.04-0.08 m below the truth** (0.20-0.24); at d = true + 0.08 m intensity +55 % and r 0.96 -> 0.86. |

## Decisions needed
1. **Luo lever arm.** Paper anatomy (sensor 5 cm above the malleolus) -> 0.34-0.36 m, but the data put the lowest
   intensity at ~0.17-0.20 m, which by the Camargo relation means a true lever arm of ~0.22-0.28 m; at 0.36 m Luo is
   ~50 % more intense than the references at the same stride time. Options: (a) 0.36 m (anatomy), (b) **one value
   0.26 m** (data, Camargo relation), (c) per person and leg: lowest-intensity point + 0.06 m. The Camargo relation
   rests on 2 people.
2. **Lencioni stairs** (periodising not proven for stairs, stairs-down stride not a steady cycle): use the periodised
   stairs (stride leg only) as **test only**, train on Lencioni walking only? Luo has ~720 real stair trials.
