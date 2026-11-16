# D0 report: window-length loaders and a check of the C features

## 1. Status

Done — all deliverables in place; acceptance check 3 exceeds the literal 1e-5 limit on 4 of 9 datasets by exactly one
float32 ULP in the two tilt features (cause diagnosed, not a pipeline difference; decision needed, see 5.1).

## 2. Files

- `pipeline/features_ref.py` (new): numpy float64 reference of `kneil_features()` (C), 20 features in `KF_*` order, `NAMES`.
- `pipeline/test_features_window.py` (new): C vs reference check at 2/3/4/5 s, log + CSV table in `stepD/D0`.
- `pipeline/stage3_v4.py` (new): window builder for any window length, V4 loaders (Luo, Lencioni), per-window metadata, CLI.
- `tasks/D0_report.md` (new): this report.

No other file was changed. `kneil_tinyml/`, `pipeline/stage2.py`, `stage3.py`, `stage2_v4.py`, `vimp.py`, `CLAUDE.md`,
`AGENTS.md`, `README.md` are untouched.

## 3. Commands

```
# 1. feature check (writes only KNEIL_results\v4\stepD\D0)
python pipeline/test_features_window.py

# 2. small end-to-end run (test output in the worktree cache)
$env:KNEIL_V4_OUT = "C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_agent\cache\test_v4"
python pipeline/stage3_v4.py --win 2 --max-people 2

# 3. full builds (write only KNEIL_results\v4\stepD\windows)
Remove-Item Env:KNEIL_V4_OUT
python pipeline/stage3_v4.py --win 2      # 334,291 windows, 1.3 min
python pipeline/stage3_v4.py --win 3      # 318,602 windows, 0.7 min
python pipeline/stage3_v4.py --win 4      # 304,349 windows
python pipeline/stage3_v4.py --win 5      # 290,745 windows
python pipeline/stage3_v4.py --win 2      # resume: loads the npz, exit code 0
```
Environment: Python 3.12.10, numpy 2.5.4, scipy 1.18.1, pandas 3.0.6, gcc MSYS2 16.2.0 (UCRT64).
Scratch checks (git-ignored, `cache\`): `check_regression.py`, `diag_regression.py`, `diag_atan2.py`, `check_lengths.py`,
`diag_v4_loaders.py`.

## 4. Acceptance checks

### 4.1 Part 1 feature table — PASS

`pipeline/test_features_window.py`, log `KNEIL_results\v4\stepD\D0\test_features_window_log.txt`, table
`test_features_window_diffs.csv`. 3 Luo people (1.npz, 2.npz, 3.npz, 10 trials each = 30 filtered streams) + 200 random
windows + 1 constant window per length:

| window | windows compared | features FAIL | zcr crossing-count mismatches | constant window finite |
|---|---|---|---|---|
| 2 s (100) | 665 (464 Luo + 200 + 1) | 0 | 0 | yes |
| 3 s (150) | 635 (434 + 200 + 1) | 0 | 0 | yes |
| 4 s (200) | 605 (404 + 200 + 1) | 0 | 0 | yes |
| 5 s (250) | 575 (374 + 200 + 1) | 0 | 0 | yes |

All 20 features PASS at all four lengths. Largest absolute C-vs-reference differences: `tilt_sag_deg` 2.25e-05,
`ac_m_10s` 1.48e-05, `jerk_m` 1.08e-05, `ac_m_05s` 9.74e-06; everything else <= 1e-05. The tolerance is
`1e-4 + 1e-3*max|ref|`, so the angle features (values up to ~180 deg) have the largest allowance and the small ones
(<=1e-4) are the tightest — all pass. `zcr_z_hz` values differ by <= 7.6e-07 (float32 rounding of `zc*fs/n`); the
zero-crossing **count** is identical in every window.

### 4.2 Small run `--win 2 --max-people 2` — PASS

20,096 windows in 0.1 min, counts printed per dataset (reproduced exactly when repeated after deleting the cache and
re-extracting the simulation zips). Output: `cache\test_v4\stepD\windows\windows_W2s.npz`.

### 4.3 Regression against the V3 cache — 5/9 datasets PASS, 4/9 exceed the limit by one ULP

V3 cache: `KNEIL_results\virtual_implant\stage3\stage3_windows.npz` (274,952 windows). New: `windows_W2s.npz`
(334,291 windows = 274,952 old + 59,339 Luo/Lencioni).

| dataset | n V3 | n V4 | max abs dX | y same | grp same | criterion |
|---|---|---|---|---|---|---|
| WearGait-PD | 82,250 | 82,250 | 3.81e-06 | yes | yes | PASS |
| CeTI | 72,412 | 72,412 | **1.53e-05** | yes | yes | FAIL |
| Camargo simulated | 50,415 | 50,415 | 3.81e-06 | yes | yes | PASS |
| PAMAP2 | 24,551 | 24,551 | **1.53e-05** | yes | yes | FAIL |
| MHEALTH | 24,301 | 24,301 | **1.53e-05** | yes | yes | FAIL |
| v1.6 synthetic | 9,626 | 9,626 | **1.53e-05** | yes | yes | FAIL |
| KneE-PAD | 5,559 | 5,559 | 7.63e-06 | yes | yes | PASS |
| Marpino | 4,404 | 4,404 | 1.91e-06 | yes | yes | PASS |
| Caicedo older adults | 1,434 | 1,434 | 3.81e-06 | yes | yes | PASS |

Window counts, row order (`grp`), `y` and `lab` are identical for all nine datasets. Diagnostic result:

- Only `tilt_sag_deg` and `tilt_cor_deg` differ; the other 18 features are **bit-identical** (max abs difference 0.00e+00).
- The difference is exactly one float32 ULP: 1.53e-05 = `np.spacing(float32(180.0))`; relative difference <= 1.03e-07
  (= 0.9 x float32 eps). It only shows up where |angle| >= ~128 deg, which is why the absolute 1e-5 limit is crossed.
- Cause: `atan2f` in the C code rounds differently in the two libms. Both implementations deviate from the
  correctly-rounded float32 value in a similar share of windows (V3 cache 1713/5000, local build 1291/5000 windows of
  CeTI), i.e. both are within 1 ULP and they disagree with each other. The V3 cache was computed on Colab (glibc);
  this build is MSYS2 UCRT64 gcc 16.2.0. Same source, same data, same filtering — no way to reproduce the old last bit
  without that libm.
- Rows with at least one differing value — always only features 11 and 12, `tilt_sag_deg` / `tilt_cor_deg`, never any
  other feature: WearGait-PD 32,948/82,250, CeTI 28,883/72,412, Camargo 20,039/50,415, PAMAP2 9,179/24,551,
  MHEALTH 9,558/24,301, v1.6 3,571/9,626, KneE-PAD 2,105/5,559, Marpino 1,763/4,404, Caicedo 554/1,434.

I did not change the comparison. With a relative/ULP criterion (`max|dX| <= 1e-5 + 2 ULP of the value`) all nine
datasets pass; that decision is the manager's (5.1).

### 4.4 Window counts for 2/3/4/5 s — PASS

Full builds. Windows per dataset (total, all labels):

| dataset | 2 s | 3 s | 4 s | 5 s |
|---|---|---|---|---|
| Caicedo older adults | 1,434 | 994 | 554 | 242 |
| Camargo simulated | 50,415 | 46,913 | 44,430 | 41,517 |
| CeTI | 72,412 | 69,358 | 66,304 | 63,313 |
| KneE-PAD | 5,559 | 3,507 | 1,701 | 983 |
| Lencioni | 8,253 | 7,094 | 5,935 | 4,776 |
| Luo | 51,086 | 47,666 | 44,246 | 40,826 |
| MHEALTH | 24,301 | 24,291 | 24,281 | 24,271 |
| Marpino | 4,404 | 4,251 | 4,098 | 3,945 |
| PAMAP2 | 24,551 | 24,544 | 24,537 | 24,530 |
| WearGait-PD | 82,250 | 80,950 | 79,650 | 78,350 |
| v1.6 synthetic | 9,626 | 9,034 | 8,613 | 7,992 |
| **ALL** | **334,291** | **318,602** | **304,349** | **290,745** |

Scaling against `max(0, T - W + 1)` summed over the index rows (T from the `seconds` column): measured/expected =
0.999 WearGait-PD, 0.998 CeTI, 0.999 Marpino, 1.000 MHEALTH, 1.000 PAMAP2, 0.997 Luo, 1.000 Lencioni,
0.949-0.986 KneE-PAD (median recording 3.8 s, so the 0.1 s rounding of `seconds` matters); mean 0.997.

Per-label counts are in `KNEIL_results\v4\stepD\D0\window_counts_by_length.csv` (dataset x label x window length).
Totals fall monotonically for every dataset. **Per-label counts are not monotonic** for WearGait-PD (walking 28,878 ->
33,417 -> 28,592 -> 31,209), Marpino (walking 2,040 -> 2,203 -> ...) and CeTI (sitting 22 -> 6 -> 0 -> 0): the label is
a majority vote with a 60 % threshold, so a longer window can move a window from "no chip class" into a class or back.
That is the label rule working as specified, not a loader error.

### 4.5 Luo and Lencioni at 2 s — PASS

- Luo: 51,086 windows, 30 people. walking **24,816**, stairs_up **3,946**, stairs_down **3,724** (step C check: ~24,800 /
  3,900 / 3,700), standing 766, and 17,834 windows with y = -1 (calibration 2,346, slope_up 7,630, slope_down 7,632,
  mixed 226). 0 flagged.
- Lencioni: 8,253 windows, 50 people. `role == 'train'`: 5,446 windows, all `walking` (y = 0). `role == 'test'`: 2,807
  windows, all y = -1, labels `stairs_up` / `stairs_down`. `role == 'other'`: 2,071 index rows skipped. 0 flagged.
- Cache keys: `X, Xr, y, src, ds, grp, task, lab, rec, surface, speed_abs, speed_rel, adult, role, W`; `W = 100`,
  `X` float32 (334,291 x 20), `Xr` NaN only where no tilt copy exists (sim + Caicedo, 18.4 %).

## 5. Problems and open questions

1. **Decision needed on check 3.** The 1e-5 absolute limit is tighter than one float32 ULP for angles above ~128 deg.
   18 of 20 features are bit-identical; the two tilt features differ by one ULP because `atan2f` is a different libm
   in the Colab build that made the V3 cache. Options: (a) accept a relative/ULP criterion, (b) compare the reference
   (float64) features instead of the C ones for the regression, (c) regenerate the V3 cache once with this build and
   compare bit-exactly from now on. I recommend (a) or (c); I did not change the check.
2. **Assumption: `Xr` for Luo and Lencioni.** The task asked for the `rot_y` + `rng.uniform(-5, 5)` tilt copy only for
   the old stage 2 data. I applied the same treatment to the V4 rows (the `rng` argument of `load_stage2_v4` would
   otherwise be unused). If V4 tilt copies are not wanted, it is one line.
3. **`max_people` picks the first N people in sorted string order**, so Luo takes 1, 2, ... but Lencioni takes Subject1,
   Subject10, Subject11, ... (lexicographic). Fine for smoke tests, but worth knowing when reading test-run counts.
   Caicedo's `max_people` filters by subject (2 subjects = 20 streams), not by stream.
4. **`test_features_window.py` must run against the real `KNEIL_V4_OUT`**: it reads the Luo stage 2 npz from
   `<V4_OUT>/stage2/Luo`. With `KNEIL_V4_OUT` pointed at a cache it stops with "no Luo npz". It only writes
   `stepD/D0`, so the real path is safe.
5. **Simulation cache is now crash-safe**: `cache\sim\{v16,cam}` is extracted through a `.tmp` folder and renamed, so an
   interrupted extraction cannot leave a partial folder that a later run trusts (the stage 3 original created the
   folder before writing). Deleted and re-extracted during testing; the 2-person run reproduced 20,096 windows exactly.
6. `speed_abs` / `speed_rel` in the Lencioni index are empty (NaN) for stairs rows; the loader writes `''` for missing
   metadata (no `'nan'` strings).
7. `adult` holds `'True'`/`'False'` as asked; it exists only for Lencioni, so Luo rows have `''` there, as do `surface`
   for Lencioni and `role`/`speed_*` for Luo.
8. Luo windows labelled `mixed` (226 at 2 s) come from the 60 % majority rule and are kept with y = -1, as specified.
   Luo standing (766 at 2 s) comes only from the still-detection codes in the stage 2 generator, not from a labelled task.
