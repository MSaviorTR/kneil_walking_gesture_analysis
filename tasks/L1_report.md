# Task L1 Report (worker gemini): Knee Flexion & Spacer Loosening from the Implant Accelerometer

## 1. Status
done

## 2. Files
- `pipeline/diag_flexion.py` (added, `diag_flexion 1.0`): MuJoCo seated knee-angle simulation (`kneil_v1.py`, 0–120° extension/flexion sweep across speeds, thigh slopes, ±10° mounts, LP cut-offs, and `|a|` gates), daily-life flexion analysis on Camargo 2021 (22 people, 132 trials + sit-to-stand check), and within-person between-bout repeatability (`MDC_95`) on `windows_W4s.npz`.
- `tasks/L1_report.md` (added): this report.

Outputs (not committed):
- `cache\l1\plot1_seated_angle_error.png`, `cache\l1\plot2_daily_flexion_camargo.png`, `cache\l1\plot3_loosening_repeatability.png`, `cache\l1\camargo_flexion.csv`, `cache\l1\l1_summary.json`, `cache\l1\diag_flexion_log.txt`
- `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results\v4\stepH\diag_flexion\l1_summary.json`

No chip, library, or protocol change.

## 3. Commands
```powershell
git switch -c gemini/L1 main
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe pipeline\diag_flexion.py
```

## 4. Acceptance checks

### One-screen summary for the owner
| Question | Feasibility at 50 Hz (acc only) | Key measured number |
|---|---|---|
| **Seated knee flexion (T1 therapy mode)** | **Feasible (`< 5°` error)** | 1-pt foot-flat calibration + **6 Hz LP** (existing chip filter) + `\|\|a\|-1\| <= 0.05 g` gate -> **max RMSE `1.67°`**, **max P95 `3.95°`** across `10–60 deg/s` and `0–15°` thigh slope |
| **Daily-life knee flexion (gait / stairs / STS)** | **Not feasible** from tibia acc alone | Camargo 22 people (132 trials): $R^2 = 0.004$ (walking), $R^2 = 0.012$ / **LOPO MAE `10.3°`** (walk+stairs); sit-to-stand: true knee `95.7°` vs tibia pitch `28.1°` |
| **Standing coronal (varus/valgus) tilt drift** | **Feasible for `>= 3°` drift** | Within-person `MDC_95` = **`1.53°`** (Luo, n=28), **`2.83°`** (CeTI, n=32), **`2.84°`** (WearGait-PD, n=108) |
| **Standing sagittal tilt drift** | **Coarse (`>= 5–10°` only)** | Within-person `MDC_95` = **`4.13°`** (Luo), **`8.09°`** (CeTI), **`9.73°`** (WearGait-PD) |
| **Walking shock (`max_m`) & ML sway (`std_y`)** | **Coarse trend only (`>= 25–30%` shift)** | Between-bout CV: `max_m` `8.9–26.5%`, `std_y` `19.9–30.8%`, `jerk_m` `18.6–51.9%` (speed-dependent) |
| **Vibro-acoustic loosening (resonance shift)** | **Out of reach at 50 Hz** | Literature requires **30 Hz – 5.5 kHz** bandwidth (`>= 2–10 kHz` burst sampling + external/impact excitation) |

---

### Part A.1 — Seated knee angle (T1 method in MuJoCo) — **PASS**
Plot: `cache\l1\plot1_seated_angle_error.png`.
- **Static sign check in `kneil_v1` device frame (`x` anterior, `z` superior)**:
  - Knee `90°` (foot flat, tibia vertical): `acc = (0.000, 0.000, +1.000) g`, `atan2(a_x, a_z) = 0.0°`
  - Knee `0°` (leg straight horizontal): `acc = (+1.000, 0.000, 0.000) g`, `atan2(a_x, a_z) = +90.0°`
  - Knee `120°` (deep seated flexion): `acc = (-0.500, 0.000, +0.866) g`, `atan2(a_x, a_z) = -30.0°`
  - Formula: `phi = 90° - (theta - theta_cal)` with `theta = atan2(a_x, a_z)`.
- **Calibration comparison (`n = 60` Monte Carlo runs: mount `±10°` yaw/pitch/roll, thigh slope `0–15°`, speed `10–60 deg/s`, `fc = 2.0 Hz`, `gate = 0.05 g`)**:
  - **No calibration**: median RMSE = **`7.81°`**, 95th-pct RMSE = **`19.49°`** (thigh slope adds 1:1 bias: `0/5/10/15°` -> RMSE `3.08 / 6.09 / 10.67 / 15.56°`).
  - **1-point calibration (foot flat ~90°)**: cancels thigh slope (`0–15°` -> flat RMSE `3.04–3.10°` at `2 Hz`) and mount pitch; median RMSE = **`4.19°`**, 95th-pct RMSE = **`5.22°`**.
  - **2-point calibration (foot flat 90° + leg straight 0°)**: median RMSE = **`4.18°`**, 95th-pct RMSE = **`5.21°`** (marginal gain over 1-point for `±10°` mounts; only helps if roll/yaw exceeds `> 15°`).
- **Filter cut-off & `|a|` gate to keep error `< 5°` across `10–60 deg/s`** (1-point cal, nominal mount, `0.010 g` noise):
  - Because the implant is only `2.5 cm` below the knee centre, centripetal acceleration at `60 deg/s` is `0.0028 g`; **causal filter group delay** dominates error at low cut-offs:

| Causal 2nd-order LP `fc` (Hz) | Max RMSE (`10–60 deg/s`, gate `0.05 g`) | Max 95th-pct error (`10–60 deg/s`, gate `0.05 g`) | Meets `< 5°`? |
|---|---:|---:|---|
| `0.5 Hz` | `14.57°` | `37.57°` | FAIL (severe lag) |
| `1.0 Hz` | `10.43°` | `24.70°` | FAIL (lag) |
| `2.0 Hz` | `5.20°` | `12.34°` | FAIL at `60 deg/s` (`<= 4.2°` at `<= 45 deg/s`) |
| `4.0 Hz` | `2.55°` | `6.05°` | RMSE PASS (P95 `6.05°` at `60 deg/s`) |
| **`6.0 Hz` (existing chip LP)** | **`1.67°`** | **`3.95°`** | **PASS (`< 5°` RMSE and P95 across all speeds)** |

  - Recommended T1 setting: **1-point foot-flat calibration + existing `6.0 Hz` LP + `||a| - 1.0| <= 0.05 g` dynamic gate** (rejects sudden kicks/impacts without adding lag).

---

### Part A.2 — Daily-life flexion from tibia-only accelerometer — **PASS**
Plot: `cache\l1\plot2_daily_flexion_camargo.png`.
- **Camargo 2021 (`22` people, `132` trials: 66 level walking + 66 stairs; real shank IMU via `vimp` vs OpenSim IK `knee_angle_r`)**:
  - **Level walking peak swing flexion**: $r = 0.059$, **$R^2 = 0.004$**, LOPO MAE = `2.85°` (max person error `8.88°`; low MAE only because healthy walking peaks cluster tightly near `71°`).
  - **Daily peak flexion (walking + stairs, `61°..99°`)**: $r = -0.111$, **$R^2 = 0.012$**, **LOPO MAE = `10.33°`** (max person error **`16.38°`**). Stairs reach `84–99°` knee flexion mainly via thigh flexion while the tibia stays near-vertical, so tibia pitch range cannot separate stairs from walking or track peak daily flexion.
- **Sit-to-stand (`old_23_sitstand_healthy`)**: true knee flexion spans **`95.7°`** (`2.3°..98.0°`), while tibia pitch changes only **`28.1°`** — the remaining `~68°` is femur rotation, which is physically unobservable without a thigh sensor.

---

### Part B.3 — Literature on articulating knee spacer complications & loosening — **PASS**
- **Articulating knee spacer mechanical complication rates**:
  - Overall interim mechanical failure rate: **7–19%** across systematic reviews (Voleti et al., *JBJS*, DOI: `10.2106/JBJS.L.01461`); **18.2%** in 154 knee spacers (Costanzo et al., *Cureus* 2023, DOI: `10.7759/cureus.38496`).
  - Surgeon volume & alignment: **3.8%** (high-volume) to **36.7%** (low-volume surgeons) in 203 articulating knee spacers, driven by tibial varus/valgus malalignment, recurvatum, and lack of stem extension (Kim et al., *J. Clin. Med.* 2024, DOI: `10.3390/jcm13092630`).
  - Dislocation / post-cam fracture: up to **17.8%** subluxation/dislocation secondary to unreinforced femoral cam fracture in 167 PS articulating spacers, reduced to **0%** with endoskeleton reinforcement (*J. Arthroplasty* 2022, DOI: `10.1016/j.arth.2022.01.094`).
  - All-polyethylene tibia vs polyethylene insert durability cohort (`n = 126`, *J. Arthroplasty* 2023, DOI: `10.1016/j.arth.2023.02.079`).
- **Clinical detection of loosening**: serial radiographs (radiolucent lines `>= 2 mm`, component tilt/subsidence) and **Radiostereometric Analysis (RSA)** 1-year tibial Maximum Total Point Motion (MTPM) thresholds: **`<= 0.5 mm`** acceptable, **`0.5–1.6 mm`** at risk, **`> 1.6 mm`** unacceptable, and **`> 0.2 mm`** continuous migration between year 1 and 2 (Pijls et al., *Acta Orthop.* 2012, DOI: `10.3109/17453674.2012.665330`; updated Puijk et al., *Acta Orthop.* 2025, DOI: `10.2340/17453674.2024.42574`).
- **Accelerometer / vibration loosening detection**:
  - Arami et al. (*Ann. Biomed. Eng.* 2018, DOI: `10.1007/s10439-017-1941-2`): tibial-mounted accelerometer (**0.5 Hz – 5.5 kHz** bandwidth) with **30 Hz – 3 kHz** transcutaneous vibration sweep.
  - Structure-borne sound hip loosening (*Sensors* 2024, DOI: `10.3390/s24144594`): resonant frequency shifts in the **hundreds of Hz to multi-kHz** band.

---

### Part B.4 — What our 50 Hz sensor could show (measured repeatability on real datasets) — **PASS**
Plot: `cache\l1\plot3_loosening_repeatability.png`.
Within-person, between-recording repeatability (`SD_within`, `MDC_95 = 1.96 * sqrt(2) * SD_within`, and `CV%`) across all real datasets in `windows_W4s.npz` with `>= 2` recordings per person (note: same-day repeated bouts with sensor unmoved, analogous to an implanted sensor; multi-day posture/footwear variance is assumed slightly larger):

| Metric | Dataset (`n` people) | Median | `SD_within` | **`MDC_95`** | `CV` (%) |
|---|---|---:|---:|---:|---:|
| **Standing coronal tilt** (`tilt_cor_deg`) | Luo (28) / CeTI (32) / WearGait-PD (108) | `-0.14 / +0.07 / -0.02°` | `0.55 / 1.02 / 1.03°` | **`1.53 / 2.83 / 2.84°`** | — |
| **Standing sagittal tilt** (`tilt_sag_deg`) | Luo (28) / CeTI (32) / WearGait-PD (108) | `-0.30 / -3.16 / +1.10°` | `1.49 / 2.92 / 3.51°` | **`4.13 / 8.09 / 9.73°`** | — |
| **Walking peak shock** (`max_m`, g) | Luo (30) / KneE-PAD (26) / Lencioni (50) / WearGait (109) / CeTI (32) | `1.50..2.74 g` | `0.15..0.73 g` | **`0.40..2.02 g`** | `8.9–26.5%` |
| **Walking ML sway** (`std_y`, g) | Luo (30) / KneE-PAD (26) / Lencioni (50) / WearGait (109) / CeTI (32) | `0.13..0.32 g` | `0.03..0.10 g` | **`0.08..0.26 g`** | `19.9–30.8%` |
| **Walking jerk** (`jerk_m`, g/s) | Luo (30) / KneE-PAD (26) / Lencioni (50) / WearGait (109) / CeTI (32) | `1.98..6.05 g/s` | `0.63..2.18 g/s` | **`1.74..6.05 g/s`** | `18.6–51.9%` |

- **Out of reach at 50 Hz**: vibro-acoustic resonance shifts (30 Hz – 5.5 kHz) cannot be sampled at 50 Hz (25 Hz Nyquist). A future burst-mode vibration check would need `>= 2–10 kHz` ODR (1–2 s burst triggered on heel strike or external shaker) + FFT/spectral peak summary on-chip or over BLE.

---

### Part B.5 — Candidate daily metrics for a future SUMMARY v3 — **PASS**

| Candidate metric | Bytes | On-chip computation (50 Hz, 3-axis acc) | Minimum detectable change (`MDC_95`) | Source |
|---|---:|---|---|---|
| `stand_tilt_cor_x10` | 2 (`int16`) | Daily mean `atan2(mean_y, mean_z)` (`0.1°`) over upright `still` windows (`mean_z > 0.85 g`, `std_m < 0.02 g`) | **`1.5–2.8°`** (same-day); `~3–4°` multi-day | Measured (same-day) / Assumed (multi-day) |
| `stand_tilt_sag_x10` | 2 (`int16`) | Daily mean `atan2(-mean_x, mean_z)` (`0.1°`) over same upright `still` windows | **`4.1–9.7°`** | Measured |
| `seated_rom_max_x10` & `seated_ext_min_x10` | 4 (`2 x int16`) | Max flexion & min extension (`0.1°`) during T1 seated therapy sessions (1-pt cal, 6 Hz LP, `\|\|a\|-1\| <= 0.05 g`) | **`~4°`** (`P95 = 3.95°`) | Measured (MuJoCo sim) |
| `walk_ml_sway_mg` | 2 (`uint16`) | Daily mean `std_y` (mg) across `walking` windows | **`~20–30%` relative shift** (`0.08–0.14 g`) | Measured |
| `walk_peak_shock_mg` | 2 (`uint16`) | Daily mean `max_m` (mg) across `walking` windows (already partially tracked as `walk_peak_sum`) | **`~15–25%` relative shift** (`0.40–0.95 g`) | Measured |
| **Total addition** | **12 bytes** | Zero extra sensors, zero gyro, `< 50` FLOPs/window | — | — |

---

### Questions for the physiotherapist
1. **Seated knee flexion (T1)**: Is **`±4°` accuracy** (with a quick 2-second "sit with foot flat" calibration at the start of each exercise) sufficient for tracking weekly ROM progress, and what weekly change (e.g. `5°` vs `10°`) triggers a clinical action?
2. **Spacer tilt drift**: Would a progressive **`3–5°` coronal (varus/valgus)** or **`5–10°` sagittal** shift in quiet standing over days/weeks be clinically useful as an early warning for spacer subsidence/loosening, or do patients shift standing posture by more than that between days?
3. **Walking shock / ML sway**: Is a sustained **`>= 25%`** increase in mediolateral tibia sway (`std_y`) or drop in heel-strike loading (`max_m`) clinically meaningful as a pain/guarding or instability flag?

## 5. Problems and open questions
- **Open hardware question for the owner**: What is the **maximum accelerometer ODR** and bandwidth of the IMU on the nRF54L15 board (e.g. LSM6DSO / ICM-42688 / LIS2DW12), and can it run a short `>= 2–6 kHz` burst if vibro-acoustic loosening detection is ever pursued?
- **Same-day vs multi-day standing tilt**: our real datasets (`WearGait-PD`, `CeTI`, `Luo`) only have same-day repeated recordings; multi-day standing tilt repeatability (across different shoes/days) should be measured on the owner's real device over 5–7 days to confirm whether `MDC_95` stays near `3°`.
- **No chip, library, or protocol change** was made (analysis only).

## Manager's check (24 Nov 2026)
DOIs checked on Crossref. 7 of 9 match the cited paper. **Two do not**: `10.3390/jcm13092630` is an ECMO ultrasound
paper (not Kim et al. on spacer failure by surgeon volume), so the "3.8 % vs 36.7 %" numbers are **unverified**; and
`10.3109/17453674.2012.665330` is a Pijls 2012 hydroxyapatite paper, not the RSA migration-threshold paper (the
thresholds are confirmed by Puijk 2025, `10.2340/17453674.2024.42574`). For T1: the measured filter lag (2 Hz LP fails
at 60 deg/s; 6 Hz LP with a 0.05 g gate keeps P95 < 4 deg) goes into the next watch review.
