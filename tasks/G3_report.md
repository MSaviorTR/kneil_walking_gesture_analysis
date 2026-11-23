# Task G3 Report (worker gemini): Why the Two Synthetic Aid-Gait Sources Disagree

## 1. Status
done

## 2. Files
- `pipeline/diag_aid_gap.py` (added, `diag_aid_gap 1.0`): read-only analysis script comparing Source 1 (`stepF/aid_gait`), Source 2 (`old_14`..`old_21` from the old HTML viewer), and real slow-walking / real-still benchmarks; caches `aid1.0` seed-0 forest under `cache/g3/` for causal forward & reverse swap tests and saves 4 diagnostic plots + `g3_summary.json` + `diag_aid_gap_log.txt` under `cache/g3/`.
- `tasks/G3_report.md` (added): this report.

No existing code or results under `KNEIL_results` were modified; no deployable model was trained or exported.

## 3. Commands
```powershell
git switch -c gemini/G3 main
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe pipeline\diag_aid_gap.py
```

## 4. Acceptance checks

### Executive answer (measured)
The domain gap between Source 1 (`pipeline/aid_gait.py`, 99.2% held-out aid recall) and Source 2 (`old_14`/`old_20`, 0.0% walking recall) is **NOT** caused by Source 1's `2–8 Hz` roughness, white noise floor, mount rotation, or AB07 identity. Adding all of those to `old_14`/`old_20` leaves both at **0.0%** walking (`S9`), replaying `old_14`/`old_20`'s exact kinematics `Q` through Source 1's own `CR.replay` (zero bias/impact) still gives **3.7% / 0.0%** (`S10`), and stripping all noise, roughness, and mount rotation from Source 1 still keeps **89.1%** walking recall (`R5`).

Instead, the gap is **kinematic amplitude and gait waveform structure**:
1. **Restricted / locked knee swing in Source 2 vs full healthy Camargo knee swing in Source 1**: Source 1 stretches healthy Camargo strides (`amp = 0.90` for pick-up walker, full ~55–65 deg knee flexion), giving strong sagittal tibia swing (`std_x = 0.310 g`, `std_z = 0.110 g`, `tilt_sag_deg = 12.6 deg`, `corr_xz = +0.767`). Source 2 models restricted (`old_14`) or locked static-spacer (`old_20`) knee flexion with per-stride pauses, cutting `std_x` (`0.232 g`) and `std_z` (`0.066 g`) by 25–40% and collapsing `corr_xz` to **`-0.181`** (`old_14 = +0.313`, `old_20 = -0.579`, right on top of real `still = -0.140`).
2. **Per-stride pauses vs multi-stride bursts**: Source 2 pauses after **every single stride** (16–17 short `0.46–0.56 s` pauses in 30 s), so every 4 s walking window is 33–41% flat static pause. Source 1 walks **4–8 consecutive strides** in a burst separated by long `1–10 s` rests, so its walking windows are nearly 100% continuous motion.
3. **Dynamic amplitude threshold**: Scaling Source 2's dynamic acceleration by `1.5x` (`S7`) immediately jumps `old_14` from **0.0% -> 100.0%** and `old_18` from **8.0% -> 84.0%**; scaling by `2.0x` (`S7b`) moves `old_20` from **0.0% -> 74.1%**.
4. **Bonus finding (`aid_gait.py` `_blend()` spike)**: Source 1 contains a **`2.2–2.3 g` transition acceleration spike** at `stand -> walk` chunk boundaries (`t = 2.6 s` in `plot1_signals_walker.png` and `plot2_signals_crutches.png`), and `aid_gait.py` includes start/stop edge windows in usable walking training.

---

### 1. Processing chain, side by side — **PASS**

| Stage | Source 1 (`pipeline/aid_gait.py`, 462 personas) | Source 2 (`old_14`..`old_21`, old HTML viewer) | Status |
|---|---|---|---|
| Base kinematics | 21 Camargo subjects (AB07 excluded), median Fourier template (5 harmonics) from 2 slow overground trials | Single subject AB07 (0.43 m/s treadmill strides) recomposed with restricted/locked knee limits (articulating or static spacer) | Measured from code & HTML `cond` |
| Sampling rate & resampling | `CR.replay` at `200 Hz` -> `resample_poly(acc200, 1, 4)` -> `50 Hz` | Embedded in HTML at `fa = 100 Hz` (quantised to `0.001 g` integers) -> `resample_poly(acc100, 1, 2)` -> `50 Hz` in `kneil_viewer.py` | Measured from code |
| Chip low-pass | Causal 2nd-order Butterworth `6.0 Hz` (`kneil_lowpass_step` at 50 Hz) | Identical (`6.0 Hz` causal low-pass at 50 Hz in `cv_aid.chip_features`) | Measured from code |
| Implant point & mount | Nominal `(0.005, -0.025, 0) m`; post-hoc `_rotate_acc`: `yaw ~ N(0,7)`, `pitch ~ N(+9, 5)` for pick-up walker (`N(0,5)` else), `roll ~ N(0,4)` | `kneil_v1.sample_sensor()`: position jitter `(±4, ±5, ±4) mm`, `yaw ~ N(0,4)`, `slope ~ U(0,7)`, `roll ~ N(0,2)`, plus static `bias ~ N(0,0.02 g)`, `scale ~ N(0,1%)`, `cross ~ N(0,0.5%)` -> measured pause `|a| = 0.9727 g` on `old_14` | Measured from code & signal |
| Sensor noise & roughness | `+0.010 g` white noise everywhere + `2–8 Hz` band-limited roughness (`ROUGH = 0.030 g` walker, `0.020 g` crutches, `0.012 g` rollator) **only while moving** | Generic MEMS `150 ug/sqrt(Hz)` (~`0.001 g`), **no** 2–8 Hz roughness | Measured from code (roughness = assumption) |
| Heel-strike impact | **None** (pure `CR.replay` kinematic acceleration) | `kneil_v1.impact_kernel` (`15–30 Hz` damped sinusoid, vector `[-0.8a, ±0.3a, +1.6a]`, scaled by `(v/1.3)^1.5 * aid`) | Measured from code (impact scale = assumption) |
| Weight-bearing gain | `CR.scale_dynamic(acc, grav, gain)`: full `1.0`, partial `0.80`, toe-touch `0.55`, NWB `0.25` | Modelled in kinematics + `aid = 0.7` impact factor (NWB `old_19` holds right leg) | Measured from code (gain = assumption) |
| Stride stitching & pauses | **4–8 consecutive strides** per walking burst, `1.0 s` cubic Hermite `_blend()` to/from standing (creates `2.2–2.3 g` transition spikes), `2` long pauses (`1.0–10.2 s`, median `5.62 s`) in 36 s | **Pause after every single stride**: `16–17` short pauses (`0.18–1.46 s`, median `0.46–0.56 s`) in 30 s, so every 4 s window is 33–41% paused | Measured from code & signal |
| Gravity / frame | Device frame `(x ant, y left, z sup)`, `|g| = 1.000 g` (pause `mean_m = 1.0075 g` on `S1_walker`) | Same device frame, but `sample_sensor` bias/scale shifts static `|g|` (`old_14` pause `mean_m = 0.9727 g`, `old_20 = 0.9970 g`, `old_15 = 1.0389 g`) | Measured from signal |

---

### 2. Matched-pair signal comparison — **PASS**
Plots saved and visually inspected under `cache/g3/`:
- `cache\g3\plot1_signals_walker.png`: `ab30_p00_pick-upwalker_step-through_full` (`v = 0.20 m/s`, `41%` pause) vs `old_14` (`v = 0.20 m/s`, `41%` pause).
- `cache\g3\plot2_signals_crutches.png`: `ab25_p18_crutches_step-through_partial` (`v = 0.44 m/s`, `21%` pause) vs `old_15` (`v = 0.44 m/s`, `20%` pause).

Key measured signal differences:
- **Amplitude & swing shape (walker pair)**: During steady walking (`t = 5–18 s`), Source 1 swings `x` smoothly from `-0.9 g` to `+0.7 g` and dips `z` down to `0.48 g` every swing phase (`move_std_m = 0.2105 g`, `move_std_xyz = [0.509, 0.252, 0.155] g`), whereas `old_14` has much smaller sagittal swings (`move_std_m = 0.0717 g`, `move_std_xyz = [0.283, 0.072, 0.089] g`) interrupted every ~1.2 s by flat static pauses (`|a| = 0.973 g`).
- **Spectrum**: In the walker pair, Source 1 has ~3–4x higher spectral amplitude below `2 Hz` (strong fundamental gait swing) AND higher power across `2–6 Hz` (from `ROUGH = 0.030 g`), whereas in the crutch pair (`plot2_signals_crutches.png`) both sources have very similar spectral energy across `0–6 Hz` (explaining why `old_15` is already recognised at `92.3%`).
- **Single steady stride overlay**: Source 1 shows a smooth single-hump wave peaking near `1.10 g`; `old_14` shows a flat `0.97 g` baseline punctuated by sharp multi-peak `1.14 / 0.83 / 1.13 g` bursts from its heel-strike impact kernel and abrupt pause starts/stops.
- **Transition spike in Source 1**: Both `plot1` and `plot2` reveal a `~2.2–2.3 g` spike in Source 1 at `t = 2.6 s` where `_blend()` transitions from standing to walking.

---

### 3. 20 features, effect sizes, and forest split alignment — **PASS**
Plot saved and visually inspected: `cache\g3\plot3_feature_boxplots.png`.

Top 10 features separating Source 1 (pick-up walker `0.15–0.25 m/s`, `n = 1,288` walking windows) from Source 2 (`old_14` + `old_20`, `n = 54` walking windows), ranked by `|Cohen's d|`, alongside real benchmarks (`WearGait-PD` slowest 25% `SelfPace` `n = 1,811`, `AB07` treadmill `0.5 m/s` `n = 13`, `Caicedo` `0.6 m/s` `n = 5`, real `still` `n = 83,416`):

| Feature | Cohen's `d` | Cliff's `delta` | S1 A1 walker | S2 `old_14/20` | Real WG Slow Q1 | AB07 0.5 m/s | Caicedo 0.6 m/s | Real still |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `corr_xz` | **+2.14** | +0.90 | **0.7671** | **-0.1813** | 0.7548 | 0.7411 | 0.8045 | -0.1402 |
| `zcr_z_hz` | **-2.13** | -0.86 | 1.5000 | 3.5000 | 3.2500 | 2.7500 | 1.2500 | 7.5000 |
| `std_z` (g) | **+1.87** | +0.89 | 0.1104 | **0.0656** | 0.1958 | 0.1466 | 0.1971 | 0.0083 |
| `hf_ratio` | **-1.73** | -0.76 | 0.0851 | **0.2408** | 0.2208 | 0.1341 | 0.0854 | 0.3310 |
| `std_x` (g) | **+1.65** | +0.92 | 0.3096 | **0.2316** | 0.3814 | 0.3134 | 0.3805 | 0.0544 |
| `mean_z` (g) | **-1.33** | -0.63 | 0.9217 | 0.9546 | 0.9522 | 0.9641 | 0.9044 | 0.9954 |
| `mean_x` (g) | **-1.33** | -0.67 | -0.2076 | -0.0271 | -0.0877 | -0.1649 | -0.2428 | 0.0102 |
| `tilt_sag_deg` | **+1.32** | +0.67 | 12.62 | 1.67 | 5.26 | 9.64 | 14.86 | -0.58 |
| `mean_m` (g) | **+1.03** | +0.47 | 1.0127 | 0.9933 | 1.0534 | 1.0348 | 1.0288 | 1.0013 |
| `ac_m_10s` | **-1.01** | -0.53 | -0.0611 | 0.0308 | -0.1000 | -0.0476 | -0.0993 | -0.0074 |

Per-persona breakdown of the 3 Source 2 walkers:
- `old_14` (early walker): `std_x = 0.243`, `std_z = 0.063`, `mean_m = 0.979`, `corr_xz = +0.313`, `hf_ratio = 0.151`
- `old_18` (toe-touch walker): `std_x = 0.265`, `std_z = 0.068`, `mean_m = 0.971`, `corr_xz = +0.118`, `hf_ratio = 0.258`
- `old_20` (static-spacer locked knee): `std_x = 0.208`, `std_z = 0.069`, `mean_m = 1.014`, **`corr_xz = -0.579`**, **`hf_ratio = 0.326`**

**Match to `aid1.0` seed-0 forest splits**:
- Root splits reproduced exactly: `hf_ratio <= 0.006` (3/20), `mean_z <= 0.478` (2/20), `ptp_m <= 0.152` (2/20), `ptp_m <= 0.279` (2/20), `mean_m <= 1.045` (1/20), `jerk_m <= 0.309` (1/20).
- Most-visited decision-path features on `old_14` + `old_20`: **`std_x` (1,229)**, **`mean_z` (1,139)**, `ptp_m` (933), **`std_z` (880)**, **`mean_m` (808)**, `std_y` (732), `std_m` (675), `jerk_m` (674), **`hf_ratio` (584)**, **`tilt_sag_deg` (559)**, **`mean_x` (455)**, **`zcr_z_hz` (452)** — directly matching the high-effect-size separators above.

---

### 4. Causal swap test (forward & reverse) — **PASS**
Exact A1 `aid1.0` seed-0 final forest cached in `cache/g3/aid10_seed0.pkl` (16,210 nodes; reproduced A1 Section 4.4 to the exact decimal on all 8 viewer personas). Plot saved and visually inspected: `cache\g3\plot4_swap_test.png`.

**Forward swaps (changing one step of Source 2 -> Source 1, walking recall %):**

| Swap | `old_14` | `old_18` | `old_20` | `old_15` |
|---|---:|---:|---:|---:|
| `S0`: baseline (Source 2) | 0.0 | 8.0 | 0.0 | 92.3 |
| `S1`: `+0.010 g` white noise | 0.0 | 8.0 | 0.0 | 92.3 |
| `S2`: `+0.030 g` 2–8 Hz roughness (moving only) | 0.0 | 12.0 | 0.0 | 92.3 |
| `S3`: `+0.010 g` white noise + roughness | 0.0 | 8.0 | 0.0 | 92.3 |
| `S4`: `+9 deg` mount pitch | 0.0 | 8.0 | 0.0 | 92.3 |
| `S5`: normalise static `|g| = 1.000` (remove bias) | 0.0 | **44.0** | 0.0 | 100.0 |
| `S6`: remove pauses (continuous strides) | 0.0 | **86.7** | 0.0 | 100.0 |
| `S7`: scale dynamic acceleration `x1.5` | **100.0** | **84.0** | 0.0 | 100.0 |
| `S7b`: scale dynamic acceleration `x2.0` | **96.3** | **100.0** | **74.1** | 100.0 |
| `S8`: `+roughness` + `+9 deg` pitch | 0.0 | 8.0 | 0.0 | 92.3 |
| `S9`: noise + roughness + pitch + norm `|g|` | 0.0 | 16.0 | 0.0 | 100.0 |
| `S10`: `CR.replay(Q)` (Source 1 replay on Source 2 `Q`, no bias/impact) | 3.7 | 16.0 | 0.0 | 100.0 |

**Reverse swaps (stripping one step at a time from 6 Source 1 slow pick-up walker streams, `ab06/ab08/ab10`, `n = 165` walking windows):**

| Swap | Walking recall (%) | Med `hf_ratio` | Med `std_m` (g) | Med `jerk_m` (g/s) |
|---|---:|---:|---:|---:|
| `R0`: full Source 1 | **99.4** | 0.1068 | 0.0232 | 0.3143 |
| `R1`: no 2–8 Hz roughness | **98.2** | 0.0462 | 0.0199 | 0.1566 |
| `R2`: no white noise | **99.4** | 0.0973 | 0.0226 | 0.2977 |
| `R3`: no mount rotation | **100.0** | 0.1068 | 0.0232 | 0.3143 |
| `R4`: no noise & no roughness | **89.1** | 0.0201 | 0.0193 | 0.1053 |
| `R5`: clean replay (no noise, roughness, or mount) | **89.1** | 0.0201 | 0.0193 | 0.1053 |

**Causal conclusion**: Neither roughness, white noise, mount pitch, nor sensor bias/impact explains `old_14`/`old_20` staying at `0%`. Only **increasing dynamic kinematic amplitude** (`S7` x1.5 -> `old_14 = 100%`, `S7b` x2.0 -> `old_20 = 74.1%`) — or removing per-stride pauses / bias on borderline `old_18` (`S6` -> `86.7%`, `S5` -> `44.0%`) — moves Source 2 into the `aid1.0` walking region.

---

### 5. Which is closer to reality — and owner recording checklist — **PASS**

**Comparison with real slow walking** (`WearGait-PD` slowest 25% `SelfPace` `n = 1,811`, `Caicedo` `0.6 m/s`, `Camargo AB07` `0.5 m/s`):
- **Where Source 1 is closer to real slow walking**: `corr_xz` (`S1 = +0.767` vs real `WG = +0.755`, `AB07 = +0.741`, `Caicedo = +0.805`; Source 2 is `-0.181`), `std_x` (`S1 = 0.310` vs real `0.313–0.381`; `S2 = 0.232`), `std_z` (`S1 = 0.110` vs real `0.147–0.197`; `S2 = 0.066`), and `mean_m` (`S1 = 1.013` vs real `1.029–1.053`; `S2 = 0.979` due to sensor bias). On real `WearGait-PD` slowest-quartile `SelfPace`, `aid1.0` seed 0 already achieves **80.7% walking recall**.
- **Where Source 2 is closer to real slow walking (and where Source 1 is unrealistic)**: `zcr_z_hz` (`S2 = 3.50 Hz`, `WG_slow = 3.25 Hz`, `AB07 = 2.75 Hz`, whereas `S1 = 1.50 Hz` is too smooth/slowly varying) and `hf_ratio` (`S2 = 0.241`, `WG_slow = 0.221`, whereas `S1 = 0.085` is too low even with `ROUGH = 0.030 g`). Also, **neither** source is validated for real pick-up-walker stop-and-go pauses or locked-knee (`static spacer`) gait: Source 1's 4–8 continuous strides with full healthy knee flexion likely **overestimate** real early pick-up-walker swing amplitude (especially stiff-knee patients), while Source 2's static-spacer locked knee + negative bias likely **underestimates** articulating-spacer gait.

**Short checklist for the owner's real walker / crutch recordings (Step 6):**
To decide definitively which regime real aid gait occupies, record **with the real sensor mounted on the anterior proximal tibia** (same axes: `x` anterior, `y` left, `z` superior) and mark transitions with the truth keys:
1. **Aids (3 minimum, plus stiff-knee test)**:
   - Standard **pick-up walker** (lift-place-step stop-and-go)
   - **Rollator** / 2-wheeled walker (continuous rolling)
   - **Bilateral forearm/axillary crutches** (3-point partial weight-bearing)
   - **Stiff-knee / brace-locked walk** with walker (e.g. knee brace locked near 0–15 deg to test whether real static-spacer gait has `corr_xz < 0` and `std_z ~ 0.07 g` like `old_20`!)
2. **Speeds & pause patterns (record each for 45–60 s continuously)**:
   - Ultra-slow pick-up walker (`~0.20–0.30 m/s`) with **per-stride pauses** (0.5–1.5 s pause every step-to / advance-walker cycle)
   - Moderate walker/rollator (`~0.35–0.55 m/s`) with **occasional 3–6 s standing rests**
   - Crutches step-to (`~0.25–0.35 m/s`) and step-through (`~0.40–0.55 m/s`)
   - Clean quiet **standing still** (30 s before/after) and **standing with weight-shifting / adjusting walker** (30 s, to test real-still false-positive boundary)
3. **What to mark with the truth keys**:
   - Exact start/end of every walking bout (first foot lift to final foot plant)
   - Exact start/end of every pause `>= 1.5 s` (and note whether pauses are per-stride `< 1 s` vs standing rests `>= 2 s`)
   - Aid type, measured walkway distance + elapsed time (for exact `v_avg`), step count, and whether knee is free vs brace-locked.
4. **Key numbers to inspect immediately on the real recordings**: `std_x`, `std_z`, `corr_xz`, `zcr_z_hz`, `hf_ratio`, `mean_m`, and actual pause durations (per-stride vs chunked).

## 5. Problems and open questions
- **`aid_gait.py` `_blend()` transition spike**: `plot1_signals_walker.png` and `plot2_signals_crutches.png` expose a `2.2–2.3 g` spike at `stand -> walk` transitions in Source 1 (`t = 2.6 s`). If `aid_gait.py` is ever updated later, `_blend()` should be checked (and start/stop edge windows verified) so the forest does not train on synthetic transition spikes.
- **No real `< 0.4 m/s` walker/crutch dataset exists in `windows_W4s.npz`**: `WearGait-PD` slowest 25% `SelfPace` is real slow Parkinson's/older-adult walking (unassisted, `~0.6–0.9 m/s` typical), so only the owner's Step 6 recordings can establish the true `std_x`, `std_z`, and `corr_xz` of real pick-up-walker and stiff-knee gait.
- **Read-only compliance**: all outputs (`plot1`..`plot4`, `g3_summary.json`, `aid10_seed0.pkl`, `diag_aid_gap_log.txt`) were written exclusively under `cache\g3\`; no existing pipeline files or `KNEIL_results` were modified.
