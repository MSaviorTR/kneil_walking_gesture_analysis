# Task G2 Report (worker gemini)

## 1. Status
done

## 2. Files
- `pipeline/diag_walker_gait.py` (added: read-only diagnosis of the 8 spacer personas vs slow healthy walking and real `still`, outputs to `cache/g2/`)
- `tasks/G2_report.md` (added: this report)

## 3. Commands
```powershell
git switch -c gemini/G2 main
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe pipeline/diag_walker_gait.py
```

## 4. Acceptance checks

### Why `still`? (one-paragraph answer)
The 4 ultra-slow walker personas (`old_14`, `old_18`, `old_19`, `old_20`: average speed `0.19–0.23 m/s`, moving speed `0.28–0.36 m/s`, `33–41 %` pause share, `1.0–2.7` steps per 4 s window) are classified as `still` in **96–100 %** of windows (`16.1–19.1` of 20 trees voting `still`), **not** because they look identical to real `still`, but because the V4 forest had no walking training data below `~0.5 m/s` and placed its `still` vs `walking` intensity cutoffs right in the empty gap above walker gait. Specifically, tracing all 20 trees on the 108 walker windows shows the decisive splits are `ptp_m <= 0.315 g` (root split in 4/20 trees), `jerk_m <= 0.731 g/s`, `std_m <= 0.062 g`, and `mean_m <= 1.015–1.019 g`: the walker medians (`std_m = 0.0503 g`, `ptp_m = 0.3453 g`, `jerk_m = 0.5539 g/s`, `mean_m = 0.9933 g`, `std_x = 0.2307 g`) fall just below those thresholds, yet remain **4.2x–7.7x higher than real `still`** (`std_m = 0.0065 g`, `ptp_m = 0.0447 g`, `jerk_m = 0.1208 g/s`, `std_x = 0.0544 g`). By contrast, the 4 faster crutch/no-aid personas (`old_15`, `old_16`, `old_17`, `old_21`: `0.41–0.75 m/s`, `std_m = 0.1458 g`, `jerk_m = 1.6695 g/s`) clear those cutoffs and are classified `walking` in **77–100 %** of windows. One exception is `old_19` (non-weight-bearing walker, implant leg held in the air: `std_x ~ 0.09 g`, `1.04` steps/4 s), which genuinely overlaps noisy `still`. For the other three walker personas (`old_14`, `old_18`, `old_20`), the 5x–8x margin above real `still` means adding aid-gait training data in Steps 2–3 can recover walker walking without hurting real `still` precision.

---

### 1. The motions: 8 spacer personas vs slow healthy walking and real `still` — **PASS**
Measured from `pipeline/diag_walker_gait.py` (`v_avg` = overall horizontal speed, `v_mov` = speed during `walking` label, `pause` = `standing` label share, `cad` = overall cadence both legs with 0.45 s refractory per leg, `stp/4s` = mean steps per 4 s window, `stR%` = implant-leg stance/held share during moving intervals):

| Motion ID | Dur | `v_avg` (m/s) | `v_mov` (m/s) | Pause (%) | Cadence (stp/min) | Steps / 4 s | Implant stance (%) | V4 `still` (%) | V4 `walk` (%) | Mean votes (of 20 trees) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `old_14` early walker | 30.0s | 0.20 | 0.33 | 41% | 36.0 | 2.37 | 71% | **100.0%** | 0.0% | still 18.3, walk 1.0, lying 0.4 |
| `old_15` crutches | 16.2s | 0.44 | 0.54 | 20% | 77.8 | 5.08 | 60% | 0.0% | **100.0%** | walk 16.9, still 2.3, st_up 0.8 |
| `old_16` later no-aid | 17.1s | 0.75 | 0.75 | 0% | 122.7 | 8.36 | 60% | 0.0% | **100.0%** | walk 14.9, still 4.3, st_dn 0.8 |
| `old_17` PWB crutches | 16.6s | 0.43 | 0.51 | 16% | 75.9 | 5.00 | 58% | 23.1% | **76.9%** | walk 11.4, still 8.2, st_up 0.2 |
| `old_18` toe-touch walker | 30.0s | 0.23 | 0.36 | 37% | 40.0 | 2.67 | 62% | **96.3%** | 3.7% | still 16.1, walk 3.8, sts 0.1 |
| `old_19` NWB walker (leg held) | 30.0s | 0.19 | 0.28 | 34% | 16.0 | 1.04 | 100%* | **100.0%** | 0.0% | still 18.8, sts 0.6, lying 0.6 |
| `old_20` static spacer walker | 30.0s | 0.23 | 0.33 | 33% | 40.0 | 2.59 | 71% | **100.0%** | 0.0% | still 19.1, walk 0.8 |
| `old_21` static spacer crutches | 17.5s | 0.41 | 0.49 | 18% | 72.1 | 4.71 | 62% | 14.3% | **85.7%** | walk 10.9, still 6.9, st_dn 1.8 |
| `old_00` AB07 treadmill 0.5 m/s | 16.0s | 0.50 | 0.50 | 0% | 78.8 | 5.38 | 58% | 7.7% | **92.3%** | walk 15.1, still 4.5, st_up 0.2 |
| `old_06` Caicedo 0.6 m/s | 8.5s | 0.60 | 0.60 | 0% | 70.4 | 4.80 | 53% | 0.0% | **100.0%** | walk 19.4, st_up 0.4, still 0.2 |
| Real `still` (`windows_W4s.npz`) | — | 0.00 | 0.00 | 100% | 0.0 | 0.00 | 100% | — | — | n = 83,416 real still windows |

\*In `old_19`, the right (implant) leg is held off the ground with low vertical velocity while hopping on the left leg (16 steps/min = left leg only).

---

### 2. Decisive features and diagnostic plots — **PASS**
Feature medians across the 5 groups (`windows_W4s.npz` real still n=83,416; walker personas n=108; crutch/no-aid personas n=54; slow healthy n=18; real walking n=75,403), plus count of appearances on V4 tree paths routing walker windows to `still`:

| Feature | Real Still | Walker (`still`) | Crutch (`walk`) | Slow 0.5–0.6 m/s | Real Walk | Path count |
|---|---:|---:|---:|---:|---:|---:|
| `mean_z` (g) | 0.9954 | 0.9395 | 1.0028 | 0.9511 | 0.9374 | 2,100 |
| `jerk_m` (g/s) | 0.1208 | **0.5539** | 1.6695 | **0.9933** | 4.5412 | 1,671 |
| `std_x` (g) | 0.0544 | **0.2307** | 0.3352 | **0.3307** | 0.5875 | 1,569 |
| `hf_ratio` | 0.3310 | 0.1872 | 0.1685 | 0.1282 | 0.1989 | 1,454 |
| `std_y` (g) | 0.0213 | 0.0603 | 0.1026 | 0.0849 | 0.2208 | 1,447 |
| `ptp_m` (g) | 0.0447 | **0.3453** | 0.7352 | **0.4239** | 1.5667 | 1,414 |
| `std_m` (g) | 0.0065 | **0.0503** | 0.1458 | **0.0833** | 0.3165 | 1,297 |
| `mean_m` (g) | 1.0013 | **0.9933** | 1.0810 | **1.0344** | 1.1844 | 1,220 |
| `std_z` (g) | 0.0083 | **0.0641** | 0.1481 | **0.1569** | 0.3782 | 949 |
| `max_m` (g) | 1.0260 | 1.1943 | 1.4992 | 1.2733 | 2.1540 | 512 |

- Key V4 forest thresholds on `still` paths: `ptp_m <= 0.315 g` (4/20 root splits), `jerk_m <= 0.731 g/s`, `std_m <= 0.062 g`, `mean_m <= 1.015 g`.
- **3 plots generated and visually verified under `cache/g2/`**:
  - `cache/g2/plot1_feature_scatter.png`: 2D scatter (`std_m` vs `ptp_m`, and `jerk_m` vs `std_x`) with forest split thresholds overlaid.
  - `cache/g2/plot2_feature_profiles.png`: Boxplots of the top 6 intensity features (`std_m`, `ptp_m`, `jerk_m`, `std_x`, `std_z`, `max_m`) showing the clear separation between Real still and Walker personas.
  - `cache/g2/plot3_persona_votes_and_rules.png`: Per-persona V4 tree vote shares alongside walking-window shares under Rules A, B, and C.

---

### 3. Plausibility vs published walker / crutch gait — **PASS**
- **Published clinical norms** (from web literature search; direct full-text paywalled PDFs were not accessed, values come from indexed clinical summaries / NIH PubMed abstracts and project refs in `pipeline/kneil_v1.py`):
  - **Standard (pick-up) walker**: Forces a discontinuous stop-and-go cycle (lift/advance frame -> step into frame -> pause); gait speed routinely drops **below 0.50 m/s** (often **0.20–0.45 m/s** in acute post-arthroplasty / frail older adults), with markedly reduced cadence and prolonged double-limb support (Physiopedia / Marquette Univ. instrumented walker studies; NIH PMC early TKA walker vs wheeled-walker comparisons).
  - **Wheeled walker / rollator**: Continuous rolling preserves momentum; significantly faster than pick-up walkers immediately post-TKA (typically **0.45–0.85 m/s**).
  - **Bilateral crutches (3-point partial weight-bearing)**: Published prospective cohorts report **0.40–0.44 m/s** (±0.22) for forearm crutches and **0.45–0.50 m/s** (±0.26) for axillary crutches, with cadence **50–90 steps/min** depending on step-to vs step-through pattern (NIH PMC / Youdas et al. PWB crutch studies).
  - **Early unassisted post-TKA**: `Debbi et al. ISB 2013` (cited in `kneil_v1.py`) reports **0.72 m/s** at 2 months post-TKA; `Cushner et al. 2024` (implanted tibial IMU, first 6 weeks) reports speed rising +50% and cadence +22% over the first 6 weeks.
- **Verdict on the 8 personas**:
  - **Crutch personas (`old_15`, `old_17`, `old_21`: `0.41–0.44 m/s`, `72–78 steps/min`, `16–20 %` pauses)** are **very realistic** and sit squarely inside published PWB crutch ranges (`0.40–0.50 m/s`, `50–90 steps/min`).
  - **Walker personas (`old_14`, `old_18`, `old_20`: `0.20–0.23 m/s` average, `0.33–0.36 m/s` moving, `36–40 steps/min`, `33–41 %` pauses)** are **plausible for acute pick-up-walker / early spacer gait** (lift-place-step stop-and-go), though **on the slow and overly regular side** (fixed periodic pause inserted every single stride from one AB07 stride template; real rollator/front-wheeled-walker users are faster and more continuous, while real pick-up-walker users have irregular pause lengths).
  - **`old_16` (later no-aid, `0.75 m/s`, `122.7 steps/min`)**: speed matches Debbi 2013 (`0.72 m/s`), though cadence is slightly high because it recomposes short AB07 strides.
  - **`old_19` (NWB walker, leg held, `0.19 m/s`, `16 steps/min`)**: represents an extreme one-legged hop; clinically rare for articulating spacers (WBAT) and physically near-still at the held tibia.

---

### 4. Label rule proposal for 4 s aid-gait windows — **PASS**
Candidate rules for labelling a 4 s window as `"walking"` (otherwise `"still"` if upright and no transition):
- **Rule A (`>= 1 step` in 4 s)**: at least 1 foot contact (either leg) in the 4 s window.
- **Rule B (`>= 2 steps` in 4 s, i.e. >= 1 stride / >= 30 steps/min)**: at least 2 foot contacts (either leg) in the 4 s window.
- **Rule C (`>= 2 steps` AND `>= 50 %` moving in 4 s)**: at least 2 foot contacts and at least 2.0 s of active stepping (excludes windows dominated by a long standing rest with 1–2 shuffling steps).

| Persona | Total 4 s win | `lbl >= 60%` (V4 default) | `lbl >= 50%` | **Rule A (`>= 1` stp)** | **Rule B (`>= 2` stp)** | **Rule C (`>= 2` stp & `>= 50%` mov)** |
|---|---:|---:|---:|---:|---:|---:|
| `old_14` early walker | 27 | 9/27 (33%) | 27/27 (100%) | 27/27 (100%) | **27/27 (100%)** | 27/27 (100%) |
| `old_15` crutches | 13 | 13/13 (100%) | 13/13 (100%) | 13/13 (100%) | **13/13 (100%)** | 13/13 (100%) |
| `old_16` later no-aid | 14 | 14/14 (100%) | 14/14 (100%) | 14/14 (100%) | **14/14 (100%)** | 14/14 (100%) |
| `old_17` PWB crutches | 13 | 13/13 (100%) | 13/13 (100%) | 13/13 (100%) | **13/13 (100%)** | 13/13 (100%) |
| `old_18` toe-touch walker | 27 | 20/27 (74%) | 25/27 (93%) | 27/27 (100%) | **27/27 (100%)** | 25/27 (93%) |
| `old_19` NWB walker (leg held) | 27 | 22/27 (81%) | 27/27 (100%) | 26/27 (96%) | **2/27 (7%)** | 2/27 (7%) |
| `old_20` static spacer walker | 27 | 22/27 (81%) | 27/27 (100%) | 27/27 (100%) | **27/27 (100%)** | 27/27 (100%) |
| `old_21` static spacer crutches | 14 | 14/14 (100%) | 14/14 (100%) | 14/14 (100%) | **14/14 (100%)** | 14/14 (100%) |

- **Recommended rule for Step 2**: **Rule B (`>= 2 steps` of either leg in the 4 s window)** or **Rule C (`>= 2 steps` AND `>= 50 %` moving)** — both cleanly label all continuous/stop-and-go weight-bearing walker and crutch personas (`old_14`–`18`, `old_20`–`21`) as `walking` (93–100%), while naturally excluding `old_19` (NWB leg-held hopping where the implant tibia barely moves and would otherwise force the forest to lower its threshold into real `still`) and excluding genuine standing rests > 2 s (Rule C). Notice also why `stage3_v4`'s default `min_share = 60%` drops 18/27 windows of `old_14` when pauses are 41%!

---

### 5. Public datasets with walker / rollator / crutch gait — **PASS**
(Details gathered from public repository listings; download sizes marked *not listed* where not shown on the landing snippet without downloading.)

| Dataset | People | Aid / condition | Sensors & positions | Shank / ankle or leg markers? | Licence | Download size | Usable in our virtual implant? |
|---|---|---|---|---|---|---|---|
| **GAITEX** (Impaired gait & rehab exercises, arXiv / open repo) | Multi-subject (normal + impaired/orthosis) | Orthosis-assisted / impaired gait & rehab | 9 body-worn IMUs + 68 full-body optical markers + OpenSim IK | **Yes** (lower-limb IMUs + 68 full-body markers + OpenSim IK) | CC BY-NC-ND 4.0 | Not listed | **Yes (non-commercial)** — full lower-limb IMUs + OpenSim IK can run directly through `camargo_replay` / `vimp.py`; check NC-ND terms before shipping a commercial model. |
| **Rollator Movement Motion Sensing Data** (Univ. of Salford, Figshare) | Healthy adults (small initial cohort) | 4-wheeled rollator straight-line walking | IMU on rollator + optical motion capture in gait lab | **Partial** (optical MoCap tracks rollator/user; IMU is on rollator, not shank) | CC BY 4.0 | Not listed | **Only if full leg markers are included** in the MoCap export (not verified without downloading); rollator-mounted IMU alone cannot go through `vimp.py`. |
| **Real-World Indoor Dynamic Skeleton Dataset of Elderly Abnormal Gait** (Zenodo `10.5281/zenodo.23028481`) | Older adults | Abnormal gaits incl. **crutch-assisted walking** | 3D skeleton / depth-camera tracking (no body-worn IMU) | **No shank IMU** (coarse 3D skeleton joints only) | CC BY 4.0 | Not listed | **No** for direct `vimp.py` (noisy depth-camera skeleton derivatives are too noisy for virtual-implant acceleration); could only inspire kinematic cadence/pause priors. |
| **Apollo Smart Walker Dataset** (Mendeley Data / GitHub) | Healthy / walker users | Smart walker walking & turns | Smartphone IMU (acc/gyr/mag) mounted on walker + video | **No** (walker-mounted IMU only) | Open (Mendeley) | Not listed | **No** — no body-worn shank IMU or leg markers. |
| **Univ. of Seville Instrumented Crutch Datasets** (UPCommons / MDPI) | Healthy / PWB volunteers | Forearm crutches, partial weight-bearing | Instrumented crutches (load + IMU) + Vicon optical MoCap | **Partial** (Vicon optical MoCap in lab, but public UPCommons releases are mostly spatiotemporal/crutch matrices) | Open (varies by paper) | Small (MBs) | **Unlikely** unless raw lower-limb Vicon marker trajectories are included; useful as plausibility reference. |

**Takeaway for Step 2**: Public open-access datasets with **shank IMUs (with gyroscope) or raw leg markers during walker/crutch gait** are scarce; `GAITEX` (orthosis/impaired, CC BY-NC-ND 4.0) is the strongest candidate to inspect, and **Step 2's synthetic persona generator + Step 6's real-device recording with walker and crutches** will be the primary data sources.

## 5. Problems and open questions
- Download sizes and exact marker sets for `GAITEX` and Salford `Rollator Movement Motion Sensing Data` could not be verified without downloading the archives (not downloaded per G2 analysis-only scope).
- `old_19` (non-weight-bearing walker, implant leg held in the air) sits close to noisy `still` in feature space (`std_x ~ 0.09 g`, `std_m ~ 0.03 g`); owner/Step 2 should decide whether NWB one-legged hopping should be excluded from `"walking"` (as Rule B/C naturally do) so real `still` precision is not degraded.
- Existing code and results were not modified (`pipeline/diag_walker_gait.py` is a new file; all outputs are in `cache/g2/`).
