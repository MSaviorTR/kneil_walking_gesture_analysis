# Task R1 Report (worker gemini): Gait Recovery Score from the Implant Accelerometer (after Ghaffari et al. 2025)

## 1. Status
done

## 2. Files
- `pipeline/gait_score.py` (added, `gait_score 1.0`): extracts walking bouts and 101-point time-normalised strides from 50 Hz stage-2 virtual-implant streams (`WearGait-PD`, `KneE-PAD`, `Marpino`, `CeTI`) and A1 walking-aid personas (`stepF/aid_gait`), compares sagittal `a_x` vs magnitude `|a|` triggers, computes FFT harmonics `H1..H10`, runs `spm1d` (v0.4.59) two-sample and paired t-tests, measures within-person `MDC_95` repeatability, evaluates a 0–100 gait similarity score (healthy reference and self-baseline), and tests 68-byte on-chip compression fidelity.
- `tasks/R1_report.md` (added): this report.

Outputs (not committed):
- `cache\r1\plot1_spm_curves.png`, `cache\r1\plot2_harmonics_and_speed.png`, `cache\r1\plot3_gait_score_and_compression.png`, `cache\r1\bouts_cache.npz`, `cache\r1\r1_summary.json`, `cache\r1\gait_score_log.txt`
- `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results\v4\stepI\gait_score\r1_summary.json`

No chip, library, or protocol change. Installed `spm1d` (`0.4.59`) via `pip install spm1d` as allowed by the task.

## 3. Commands
```powershell
git switch -c gemini/R1 main
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe -m pip install spm1d
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe pipeline\gait_score.py
```

## 4. Acceptance checks

### One-screen summary for the owner
| Question | Measured result (50 Hz tibial implant, real datasets + A1) |
|---|---|
| **Stride trigger on tibia** | Sagittal `a_x` (2.5 Hz LP) + local `|a|` peak refinement beats Ghaffari's `|a|`-only trigger: **lower stride-time CV (`0.095` vs `0.112`)** and **higher yield (`86.0%` vs `80.7%`)** on `WearGait-PD` (`1,138` bouts across `263` people) |
| **SPM1D sensitivity (knee / aid vs healthy)** | **3 significant gait-cycle regions** (`p < 0.001..0.030`) in both `KneE-PAD` (`n=28`) and `Aid-walker` (`n=21`) vs `WG-Control` (`n=76`): loading response (`0–12%`), push-off/pre-swing (`45–68%`), terminal swing (`94–100%`) — closely mirroring Ghaffari et al. 2025 (DOI: `10.1002/jor.70058`) |
| **FFT harmonics `H1..H10`** | Strongest single separator: **`H1..H5` power** separates `KneE-PAD` (`d = -1.57`) and `Aid-walker` (`d = -1.62`) from controls; `H6..H10` (only available at 50 Hz, impossible at Ghaffari's 12.5 Hz) adds `d = -0.97` to `-1.00` |
| **Speed confounder** | **Major confounder**: paired `SelfPace` vs `HurriedPace` in the exact same `n=93` people triggers **4 SPM regions (~75% of cycle, all `p < 0.001`)**, `H1..H5` `d = -1.00`, and shifts the 0–100 score by **`-9.4 pts`** |
| **0–100 Gait Similarity Score** | Healthy controls `89.4` (self-repeat `94.5`), `Aid-walker` `58.5`, `Marpino Eld/Dis` `83.3`, `KneE-PAD` `87.4`, `WG-PD` `89.2`. Undirected distance penalises *faster* gait too (`WG-Hurried` `80.4`, `CeTI` `78.7`), whereas directional `H1..H5` rises monotonically with gait vigour |
| **On-chip daily cost & compression loss** | **68 bytes/day** (`32`-pt `uint8` `|a|` template + `30`-byte `uint8` harmonics + `T_stride`, `duty`, `wave_sd`, `n_strides`), **~1,200 FLOPs/stride** (`< 0.05 ms` on Cortex-M33); score vs full float32: **`r = 0.99985`**, **`MAE = 0.28 pts`** (max `1.72 pts`) |

---

### Differences vs Ghaffari et al. 2025 (DOI: `10.1002/jor.70058`)
- **Tibia vs thigh**: sagittal `a_x` swing peak is sharper at the tibia than `|a|` (which often has dual heel-strike + toe-off peaks).
- **50 Hz vs 12.5 Hz**: unlocks harmonics `H6..H10` (above Ghaffari's ~6 Hz Nyquist), which carry `|d| ~ 1.0` between knee/aid patients and controls.
- **Bone-fixed implant vs skin thigh patch**: eliminates day-to-day re-attachment error; our `MDC_95` estimates come from same-day repeated bouts with sensor unmoved.
- **No post-op longitudinal data or PROMs yet**: this study validates impairment sensitivity, speed confounding, repeatability, and on-chip compression — **not** clinical responsiveness against EQ-5D / KOOS / WOMAC recovery.

---

### 1. Stride extraction & quality rules — **PASS**
Extracted **`1,138` walking bouts** (`>= 5 s`, trimmed `0.4 s` at edges, 4th-order `6 Hz` Butterworth LP): `WearGait-PD` (`781` bouts, `109` files), `KneE-PAD` (`94` bouts, `28` files), `Marpino` (`65` bouts, `78` files), `CeTI` (`129` bouts, `32` files), `Aid-walker` (`69` bouts, `63` personas / `21` people).
- **Trigger comparison (`WearGait-PD` `SelfPace`)**:
  - Sagittal `a_x` (`2.5 Hz` LP peak + nearest `|a|` peak in `[0, +0.25 s]`): median `T_cv = 0.0952`, valid yield **`86.0%`**.
  - Magnitude `|a|`-only (Ghaffari method): median `T_cv = 0.1122`, valid yield **`80.7%`**.
- **Quality rules**: `T_stride in [0.70, 2.20] s` (`3.20 s` for aid gait), `|T - median(T)| <= 0.35 * median(T)`, `mean(|a|) in [0.75, 1.60] g`, `ptp(|a|) >= 0.12 g`, `>= 3` valid strides per bout.
- **Duty factor**: estimated from accelerometer-only `argmin(a_x)` in `45–75%` of the normalised cycle (marked as an *accelerometer-only approximation* of stance share).

---

### 2 & 3. Sensitivity: SPM1D tests & harmonic effect sizes — **PASS**
Plots: `cache\r1\plot1_spm_curves.png` and `cache\r1\plot2_harmonics_and_speed.png`.
One mean stride per person (`N` = unique people, no pseudoreplication); `spm1d` two-sample Welch `ttest2` (`alpha = 0.05`, two-tailed) and `ttest_paired` for within-person speed:

| Comparison (`n_A` vs `n_B` people) | SPM significant gait-cycle regions (`p`) | `H1..H5` `d` | `H6..H10` `d` | `T_mean` `d` | `duty` `d` | `wave_sd` `d` |
|---|---|---:|---:|---:|---:|---:|
| `KneE-PAD` (28) vs `WG-Control` (76) | `0–12.2%` (`<0.001`), `44.7–61.3%` (`<0.001`), `93.7–100%` (`0.005`) | **-1.57** | **-0.97** | +0.36 | +0.03 | **-1.47** |
| `Aid-walker` (21) vs `WG-Control` (76) | `0–3.1%` (`0.030`), `48.6–67.9%` (`<0.001`), `96.4–100%` (`0.024`) | **-1.62** | **-1.00** | **+1.30** | -0.51 | -0.32 |
| `WG-PD` (27) vs `WG-Control` (76) | none (`reject = False`) | +0.01 | +0.08 | +0.10 | +0.03 | +0.07 |
| Speed-matched `WG-PD` (20) vs `Ctrl` (58) (`T in 1.05..1.25 s`) | `9.6–11.0%` (`0.044`) | +0.21 | +0.09 | -0.49 | -0.18 | +0.14 |
| **Paired `SelfPace` vs `HurriedPace` (same `n=93`)** | `0–18.5%`, `35.4–53.5%`, `58.7–74.2%`, `78.1–100%` (all `<0.001`) | **-1.00** | -0.27 | **+1.14** | **+1.07** | **-0.90** |

---

### 4. Repeatability (`MDC_95`, within-person between-bout / session) — **PASS**

| Feature | `WearGait-PD` SelfPace (`n=104`) `SD / MDC_95` | `CeTI` (`n=22`) `SD / MDC_95` | `KneE-PAD` (`n=26`) `SD / MDC_95` |
|---|---:|---:|---:|
| `T_mean` (s) | `0.095 / 0.264` | `0.109 / 0.302` | `0.144 / 0.399` |
| `duty` (%) | `3.50 / 9.69` | `4.84 / 13.41` | `5.74 / 15.91` |
| `H1..H5` power (`g^2`) | `0.0060 / 0.017` | `0.0161 / 0.044` | `0.0033 / 0.009` |
| `H6..H10` power (`g^2`) | `0.0011 / 0.003` | `0.0020 / 0.006` | `0.0004 / 0.001` |
| `wave_sd` (g) | `0.030 / 0.083` | `0.052 / 0.145` | `0.022 / 0.062` |
| 0–100 Similarity Score (pts) | `5.16 / 14.3` | `7.46 / 20.7` | `10.18 / 28.2` |

---

### 5. 0–100 Gait Similarity Score — **PASS**
Plot: `cache\r1\plot3_gait_score_and_compression.png`.
- **vs Healthy Control Reference (`WG-Control` `SelfPace`, `n=76`)**:
  - `WG-Control (Self)` (`n=76`): median **`89.4`** (IQR `9.4`), `WG-Control (Hurried)` (`n=67`): **`80.4`** (IQR `16.2`), `CeTI (Healthy)` (`n=26`): **`78.7`** (IQR `7.2`), `WG-PD (Self)` (`n=27`): **`89.2`** (IQR `5.0`), `KneE-PAD (Knee)` (`n=28`): **`87.4`** (IQR `7.2`), `Marpino (Eld/Dis)` (`n=18`): **`83.3`** (IQR `14.6`), `Aid-walker (A1)` (`n=21`): **`58.5`** (IQR `50.1`).
- **vs Person's Own Baseline (bout 0)**:
  - Same-speed repeat bout (`n=104`): median **`94.5 / 100`**.
  - `SelfPace -> HurriedPace` (`n=93`): drops to **`80.9 / 100`** (healthy-ref delta **`-9.4 pts`**, IQR `17.0`).
- **Speed confounder implication**: because walking faster shifts both the waveform and `T_mean`, a single undirected distance-to-control score drops for *faster* walkers (`WG-Hurried`, `CeTI`). For post-op recovery tracking, **report both** (a) directional gait vigour (`H1..H5` power + `T_stride`) and (b) similarity to a speed-matched healthy band or the patient's own pre-op / week-1 baseline.

---

### 6. On-chip byte budget, FLOPs, and compression fidelity — **PASS**
| Field in future daily SUMMARY v3 | Encoding | Bytes | On-chip computation |
|---|---|---:|---|
| 32-point mean `|a|` stride template | `uint8[32]` (`0.01 g`, `0..2.55 g`) | 32 | Linear resample per stride + running mean (~160 FLOPs) |
| Harmonics `H1..H10` × 3 axes (`x,y,z` or `|a|`) | `uint8[30]` (`log10` in `[-6, 0]`) | 30 | 10-bin Goertzel/DFT on 32-pt daily mean once/day (~960 FLOPs) |
| Mean stride time `T_stride` | `uint16` (ms) | 2 | Running mean of inter-peak intervals |
| Mean duty factor | `uint8` (`0.5%` step) | 1 | `argmin(a_x)` in 45–75% of daily mean template |
| Stride waveform SD (`wave_sd`) | `uint8` (`0.005 g` step) | 1 | Running variance across strides |
| Valid stride count (`n_strides`) | `uint16` | 2 | Counter |
| **Total** | — | **68 bytes/day** | **~1,200 FLOPs/stride (`< 0.05 ms` on Cortex-M33)** |

- **Measured compression loss (`68`-byte quantised vs full float32 `101`-pt across `n = 263` people)**: **`r = 0.99985`**, **`MAE = 0.28 pts`**, **`max error = 1.72 pts`** (visually confirmed in `plot3_gait_score_and_compression.png`).

---

### What a longitudinal patient study must collect to validate the score
1. **Cohort & visits**: `>= 30–40` TKA / articulating-spacer patients (matching Ghaffari et al. 2025's `n = 31` / `17` complete), recorded **pre-op (or week 1 post-op)** and at **weeks 2, 4, 6, 12, and 26**.
2. **PROMs at every visit**: **KOOS** (Pain, Symptoms, ADL, QoL), **EQ-5D-5L + VAS**, **Oxford Knee Score (OKS)**, and patient-reported anchor ("much better / slightly better / same / worse") to define clinical responders and MCID.
3. **Objective anchors at each visit**: **10-meter walk test (10MWT)** at both self-selected and fast speed (separates true gait-quality recovery from pure speed increase!), **Timed Up and Go (TUG)**, goniometer knee ROM, and aid used (walker / crutches / cane / none).
4. **Device logging**: continuous daily 68-byte gait-template summaries plus raw 50 Hz verification recordings during the clinic 10MWT.

## 5. Problems and open questions
- **No longitudinal post-op or PROM data**: all datasets tested here are cross-sectional (`KneE-PAD`, `WearGait-PD`, `Marpino`, `CeTI`) or synthetic (`A1`), so responsiveness to recovery and AUC vs PROMs cannot be measured yet.
- **Speed confounding**: paired `SelfPace` vs `HurriedPace` produces larger SPM differences (`~75%` of cycle) than `WG-PD` vs `Control`, so any clinical recovery score must condition on or report stride speed (`T_stride`) alongside waveform similarity.
- **Checked DOIs**: `10.1002/jor.70058` (Ghaffari et al., *J Orthop Res* 2025;43:2165–2177, provided in the task prompt). No unverified DOIs were cited.

## Manager's check (24 Nov 2026)
- **Cross-dataset confound.** The two "significant" groups (KneE-PAD knee patients, A1 aid walkers) come from other
  sources than the WearGait-PD controls (other labs, other IMUs, other virtual-implant paths; A1 is synthetic). The only
  same-dataset comparison (WG-PD vs WG-Control) shows **nothing**. So the knee / aid differences (SPM regions,
  H1..H5 d = -1.6) may be dataset effects, not gait effects. Not yet shown that the method detects knee impairment.
- **Score too noisy for one person.** The 0-100 score's within-person MDC95 is 14-28 points, while knee patients vs
  controls differ by 2 points (87.4 vs 89.4) and walking faster moves it by 9. As built, it cannot track one patient's
  recovery; the harmonic powers and stride time are the better candidates. Speed must be reported with any score.
- Kept: the stride trigger, the 68-byte daily template budget and its compression test (r 0.9999) are useful as they are.
