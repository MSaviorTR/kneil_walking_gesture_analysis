# Task S1 Report (worker gemini): Merge Stairs and Ramps into "Going Up" / "Going Down"?

## 1. Status
done

## 2. Files
- `pipeline/cv_updown.py` (added, `cv_updown 1.0`): extracts Camargo 2021 ramp trials (real shank IMU via `vimp` + simulated replay, 6 surveyed inclinations `5.2°..18.0°`) and fast treadmill trials (`>= 1.4 m/s`), combines them with Luo 2020 `SlpU`/`SlpD` from `windows_W4s.npz`, runs 5-fold person-grouped CV × 3 seeds (`W = 4 s`, `hop = 1 s`, `V4half` settings) across all 5 variants and vote-share thresholds `0.5 / 0.6 / 0.7 / 0.8`, and saves resumable caches, predictions, CSVs, confusion matrices, and `owner_summary.md` under `KNEIL_results\v4\stepG\cv_updown\`.
- `tasks/S1_report.md` (added): this report.

Outputs (not committed; all under the allowed `KNEIL_results\v4\stepG\cv_updown\`):
- `camargo_cache\ab*.npz` (22 per-person caches)
- `preds\pred_<variant>_seed<0,1,2>.npz` (15 CV prediction files)
- `cv_updown_results.csv`, `dataset_counts.json`, `confusion_matrices_t06.json`, `owner_summary.md`, `cv_updown_log.txt`

No export, no chip, library, or protocol change; no existing pipeline files modified.

## 3. Commands
```powershell
git switch -c gemini/S1 main

# 2-person subset test first (isolated to cache/test_v4)
$env:KNEIL_V4_OUT = "C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_gemini\cache\test_v4"
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe pipeline\cv_updown.py --max-people 2 --seeds 0 --variants V4half M-all --out-name test2

# Full experiment: 22 Camargo + 30 Luo people, 5 variants x 3 seeds x 5 folds + vote sweep
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe pipeline\cv_updown.py
```

## 4. Acceptance checks

### 4.1 Audit of ramp / slope data in `G:\My Drive\Walking_Gesture_Datasets` — **PASS**
Every dataset folder on `G:` was checked:
- **Camargo et al. 2021** (`22` zips `AB06`..`AB30`; `20` people have valid ramp trials; `AB25` and `AB28` yielded `0` pure 4 s ramp windows): 6 surveyed inclinations from `conditions/ramp_<1..6>_*.mat`: **`5.2°`, `7.8°`, `9.2°`, `11.0°`, `12.4°`, `18.0°`**. Extracted up to 4 trials/incline/person (balanced left/right) for both **real shank IMU via `vimp`** (`distance=0.22 m, anterior=-0.02 m`, calibrated per person) and **simulated replay** (`camargo_replay.py`), plus **fast treadmill `>= 1.4 m/s`** (`22` people).
- **Luo et al. 2020** (`30` people, real shank IMU via `vimp`, already in `windows_W4s.npz` with `y = -1`): `SlpU` (`6,910` windows) and `SlpD` (`6,916` windows). Exact slope angle is **not reported** in Luo et al. 2020 (outdoor cement upslope/downslope); therefore `M-steep8` and `M-steep10` do **not** assign an assumed angle to Luo slopes (they are excluded from `M-steep` training and evaluated separately as their own band).
- **All other datasets checked (`0` ramp/slope files found)**: `Clement et. al. 2025`, `van der Aalst et. al. 2017`, `Ivanov et. al. 2026`, `Faliagka et. al. 2023`, `har70`, `harth`, `Rodríguez et. al. 2020`, `WearGait-PD`, `CeTI-Age-Kinematics`, `Lencioni et. al. 2019`, `Marpino`, `PAMAP2`, `MHEALTH`.

**Exact people & window counts:**

| Dataset / Slope band | People | Total windows | Up windows | Down windows | Notes |
|---|---:|---:|---:|---:|---|
| `Camargo ramp real` (all 6 slopes) | 20 | 2,791 | 1,553 | 1,238 | real shank IMU via `vimp` |
| — `5.2°` / `7.8°` / `9.2°` | 5 / 20 / 20 | 34 / 412 / 503 | 21 / 238 / 282 | 13 / 174 / 221 | `5.2°` has only 5 people, 34 win |
| — `11.0°` / `12.4°` / `18.0°` | 20 / 20 / 20 | 550 / 584 / 708 | 306 / 319 / 387 | 244 / 265 / 321 | steep bands |
| `Camargo ramp sim` (all 6 slopes) | 20 | 2,791 | 1,553 | 1,238 | kinematic replay (`camargo_replay`) |
| `Luo slope` (`SlpU` / `SlpD`) | 30 | 13,826 | 6,910 | 6,916 | angle not reported in Luo 2020 |
| `Camargo tm >= 1.4 m/s` (real / sim) | 22 | 7,525 / 7,525 | — | — | fast level walking (`y = 0`) |
| Base real stairs: `Luo` / `PAMAP2` | 30 / 7 | 6,232 / 1,984 | 3,226 / 1,043 | 3,006 / 941 | from `windows_W4s.npz` |
| Base real walking (8 datasets) | 305 | 75,403 | — | — | from `windows_W4s.npz` |
| Base real `still` | — | 83,416 | — | — | from `windows_W4s.npz` |

---

### 4.2 One-screen owner summary (`theta = 0.60`, mean (sd) over 3 seeds; numbers only) — **PASS**
(Exact copy of `KNEIL_results\v4\stepG\cv_updown\owner_summary.md`; `V4half` reproduces A1/D2 baseline exactly: Luo stairs `43.4 / 89.2%`, Lencioni fast `0.6%`, Luo FE `1.2%`, WearGait hurried `1.1%`, real still->walk `0.7%`, nodes `16,131`.)

| Metric | V4half | R-walk | M-all | M-steep8 | M-steep10 |
|---|---:|---:|---:|---:|---:|
| Merged real up recall (stairs+ramps), % | 13.6 (0.2) | 12.8 (0.9) | 48.8 (0.5) | 14.7 (0.6) | 14.3 (0.5) |
| Merged real up precision, % | 92.4 (2.3) | 96.5 (1.2) | 54.3 (0.8) | 95.0 (1.0) | 96.1 (0.4) |
| Merged real down recall (stairs+ramps), % | 32.1 (0.5) | 25.7 (1.3) | 71.3 (1.0) | 33.3 (0.4) | 34.4 (0.3) |
| Merged real down precision, % | 82.2 (2.3) | 86.7 (1.1) | 61.0 (0.8) | 82.0 (0.4) | 82.2 (0.9) |
| Luo stairs up / down recall, % | 43.4 / 89.2 | 41.1 / 82.6 | 44.2 / 82.5 | 37.0 / 89.3 | 40.2 / 90.5 |
| PAMAP2 stairs up / down recall, % | 23.6 / 38.0 | 24.3 / 37.2 | 15.0 / 27.9 | 21.0 / 36.0 | 21.7 / 38.8 |
| Luo `SlpU` / `SlpD` called up/down, % | 1.0 / 9.5 | 0.5 / 1.8 | 61.2 / 81.7 | 0.9 / 9.4 | 0.8 / 11.2 |
| Camargo real ramp `5.2 / 7.8 / 9.2°` recall, % | 0.0 / 2.7 / 5.4 | 0.0 / 2.6 / 4.2 | 7.8 / 13.9 / 15.1 | 5.9 / 13.2 / 18.5 | 0.0 / 7.0 / 11.0 |
| Camargo real ramp `11.0 / 12.4 / 18.0°` recall, % | 5.6 / 7.6 / 12.7 | 4.3 / 6.7 / 10.2 | 22.7 / 27.8 / 29.6 | 26.1 / 31.6 / 38.4 | 18.4 / 23.2 / 32.2 |
| Real walking called up/down (all), % | 1.0 (0.2) | 0.5 (0.1) | 13.3 (0.5) | 0.8 (0.0) | 0.8 (0.0) |
| Lencioni fast walking called up/down, % | 0.6 (0.2) | 0.6 (0.3) | 1.1 (0.4) | 0.4 (0.3) | 0.3 (0.2) |
| Luo FE walking called up/down, % | 1.2 (0.5) | 0.7 (0.4) | 40.6 (1.9) | 1.2 (0.2) | 0.9 (0.1) |
| WearGait HurriedPace called up/down, % | 1.1 (0.2) | 1.1 (0.1) | 0.7 (0.1) | 1.0 (0.4) | 1.0 (0.0) |
| Camargo tm `>= 1.4 m/s` real called up/down, % | 0.2 (0.3) | 0.2 (0.3) | 1.5 (0.8) | 0.3 (0.1) | 0.2 (0.1) |
| Real still called walking, % | 0.7 (0.0) | 0.6 (0.0) | 0.6 (0.0) | 0.7 (0.0) | 0.7 (0.0) |
| Real lying recall, % | 93.5 (0.2) | 93.3 (0.1) | 93.4 (0.1) | 93.4 (0.2) | 93.3 (0.2) |
| Sim transition event recall (STS+S2S), % | 81.7 (1.6) | 82.4 (1.5) | 80.1 (1.9) | 82.9 (1.1) | 81.8 (2.0) |
| Camargo false events / h | 0.0 (0.0) | 0.0 (0.0) | 0.0 (0.0) | 0.0 (0.0) | 0.0 (0.0) |
| Forest nodes (fold 0) | 16,131 (1,108) | 16,593 (744) | 17,928 (763) | 15,869 (836) | 16,587 (489) |

---

### 4.3 Per-dataset walking recall, Camargo simulated ramps & vote-share sweep (`0.5..0.8`) — **PASS**

**Walking recall per real dataset (`theta = 0.60`, mean %):**

| Dataset | V4half | R-walk | M-all | M-steep8 | M-steep10 |
|---|---:|---:|---:|---:|---:|
| WearGait-PD | 86.4 | 84.0 | 85.2 | 85.6 | 85.9 |
| CeTI | 98.9 | 98.3 | 95.6 | 98.4 | 98.6 |
| Luo | 97.7 | 99.4 | **55.2** | 98.0 | 97.9 |
| Lencioni | 98.2 | 97.9 | 98.4 | 98.1 | 98.2 |
| KneE-PAD | 71.3 | 67.9 | 69.9 | 70.3 | 69.1 |
| Marpino | 97.4 | 97.1 | 97.3 | 97.1 | 97.2 |
| PAMAP2 | 92.3 | 93.7 | 95.0 | 95.7 | 94.6 |
| MHEALTH | 100.0 | 100.0 | 100.0 | 99.5 | 99.7 |

**Camargo simulated ramp recall per slope (`theta = 0.60`, mean %) and `tm >= 1.4 sim -> up/down`:**
- `V4half`: `5.2°` `14.7%`, `7.8°` `36.4%`, `9.2°` `43.2%`, `11.0°` `51.0%`, `12.4°` `60.7%`, `18.0°` `73.8%` | `tm>=1.4 sim -> ud`: `0.9%`
- `R-walk`: `6.9 / 26.9 / 31.5 / 37.6 / 45.4 / 59.9%` | `tm>=1.4 sim -> ud`: `0.7%`
- `M-all`: `58.8 / 77.7 / 85.1 / 89.8 / 94.7 / 91.6%` | `tm>=1.4 sim -> ud`: `3.0%`
- `M-steep8`: `44.1 / 80.5 / 87.2 / 91.7 / 93.1 / 93.8%` | `tm>=1.4 sim -> ud`: `0.9%`
- `M-steep10`: `42.2 / 76.7 / 84.2 / 90.4 / 93.7 / 93.5%` | `tm>=1.4 sim -> ud`: `0.8%`

**Vote-share rule sweep (`theta = 0.5 / 0.6 / 0.7 / 0.8`) for merged variants (mean over 3 seeds, %):**

| Variant | `theta` | Merged up rec / prec | Merged dn rec / prec | Luo st up / dn | Luo FE -> ud | Lenc fast -> ud | WG hur -> ud | Cam tm14 real -> ud |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `M-all` | 0.5 | 66.7 / 48.2 | 78.5 / 53.6 | 61.9 / 90.7 | 62.0 | 4.8 | 3.9 | 5.0 |
| `M-all` | 0.6 | 48.8 / 54.3 | 71.3 / 61.0 | 44.2 / 82.5 | 40.6 | 1.1 | 0.7 | 1.5 |
| `M-all` | 0.7 | 22.8 / 65.7 | 60.3 / 66.7 | 20.7 / 65.4 | 18.6 | 0.1 | 0.1 | 0.1 |
| `M-all` | 0.8 | 2.1 / 89.4 | 47.0 / 72.5 | 3.6 / 40.7 | 6.7 | 0.0 | 0.0 | 0.0 |
| `M-steep8` | 0.5 | 23.4 / 80.6 | 43.1 / 67.6 | 51.6 / 94.6 | 3.7 | 1.1 | 5.0 | 3.2 |
| `M-steep8` | 0.6 | 14.7 / 95.0 | 33.3 / 82.0 | 37.0 / 89.3 | 1.2 | 0.4 | 1.0 | 0.3 |
| `M-steep8` | 0.7 | 7.3 / 98.1 | 24.4 / 92.7 | 23.7 / 77.1 | 0.2 | 0.0 | 0.1 | 0.0 |
| `M-steep8` | 0.8 | 2.3 / 97.7 | 15.2 / 97.9 | 8.6 / 54.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| `M-steep10` | 0.5 | 22.8 / 88.1 | 43.8 / 68.9 | 55.1 / 94.9 | 3.4 | 1.4 | 3.9 | 1.6 |
| `M-steep10` | 0.6 | 14.3 / 96.1 | 34.4 / 82.2 | 40.2 / 90.5 | 0.9 | 0.3 | 1.0 | 0.2 |
| `M-steep10` | 0.7 | 7.7 / 97.9 | 25.0 / 93.1 | 26.4 / 79.4 | 0.2 | 0.0 | 0.1 | 0.0 |
| `M-steep10` | 0.8 | 2.9 / 98.3 | 15.5 / 98.0 | 10.7 / 55.4 | 0.0 | 0.0 | 0.0 | 0.0 |

---

### 4.4 4×4 Confusion matrices (`walking`, `up`, `down`, `still`, real base + all real ramps, `theta = 0.60`, mean counts over 3 seeds) — **PASS**

Rows = true (`walk`, `up` = real stairs_up + real ramps_up, `down` = real stairs_down + real ramps_down, `still`); columns = predicted (`walk`, `up`, `down`, `still`):

**V4half:**
| True \ Pred | walk | up | down | still |
|---|---:|---:|---:|---:|
| walk | 70,188 | 110 | 622 | 4,483 |
| up | 10,649 | 1,733 | 219 | 131 |
| down | 8,075 | 22 | 3,886 | 118 |
| still | 612 | 9 | 0 | 82,596 |

**R-walk:**
| True \ Pred | walk | up | down | still |
|---|---:|---:|---:|---:|
| walk | 69,753 | 35 | 310 | 5,304 |
| up | 10,814 | 1,624 | 166 | 127 |
| down | 8,851 | 17 | 3,111 | 122 |
| still | 534 | 8 | 0 | 82,656 |

**M-all:**
| True \ Pred | walk | up | down | still |
|---|---:|---:|---:|---:|
| walk | 60,401 | **5,044** | **4,954** | 5,004 |
| up | 5,825 | 6,217 | 558 | 132 |
| down | 3,152 | 195 | 8,623 | 131 |
| still | 516 | 5 | 0 | 82,721 |

**M-steep8:**
| True \ Pred | walk | up | down | still |
|---|---:|---:|---:|---:|
| walk | 70,034 | 68 | 561 | 4,740 |
| up | 10,426 | 1,866 | 324 | 117 |
| down | 7,931 | 20 | 4,031 | 118 |
| still | 617 | 10 | 0 | 82,574 |

**M-steep10:**
| True \ Pred | walk | up | down | still |
|---|---:|---:|---:|---:|
| walk | 70,086 | 44 | 593 | 4,680 |
| up | 10,488 | 1,821 | 308 | 115 |
| down | 7,799 | 20 | 4,164 | 118 |
| still | 584 | 10 | 1 | 82,617 |

## 5. Problems and open questions
- **Luo 2020 slope angle is unreported**: `Luo` contributes `13,826` of the `16,617` real ramp windows (`83%`), but Luo et al. 2020 does not report the exact inclination angle of `SlpU`/`SlpD`. In `M-all`, adding Luo `SlpU`/`SlpD` as `up`/`down` causes `40.6%` of `Luo FE` (flat even walking) to be misclassified as `up`/`down` (and `walk_Luo` recall drops `97.7% -> 55.2%`), because Luo's outdoor slope looks close to Luo's flat walking in the 20 chip features.
- **Camargo `5.2°` band is small**: only `5` of `22` Camargo subjects (`34` windows) had pure `>= 60%` 4 s ramp windows at `5.2°` (at `5.2°`, vertical pelvis velocity `vy` in `camargo_replay.kinematic_labels` frequently falls below the `0.12 m/s` threshold), and `AB25`/`AB28` had `0` ramp windows. All other Camargo slope bands (`7.8°..18.0°`) have `20` people and `412–708` windows each.
- **Real vs simulated Camargo ramp gap**: on Camargo simulated ramps (`11°–18°`), `M-steep8`/`M-steep10` reach `90–94%` recall, whereas on the matching Camargo real shank IMU (`vimp`) ramps they reach `18–38%` (up from `5.6–12.7%` in `V4half`), reflecting the real-shank `vimp` vs clean-replay gap.
- **No recommendation** is made here (per task instructions); the owner decides from the numbers above.
