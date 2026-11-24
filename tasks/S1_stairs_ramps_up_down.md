# Task S1 (worker gemini): merge stairs and ramps into "going up" / "going down"? (experiment only)

Branch `gemini/S1`, new from `main`. Report `tasks/S1_report.md`, committed last. New code `pipeline/cv_updown.py`
(version line, log, resume). Outputs only under `KNEIL_results\v4\stepG\` (new allowed folder for this task). **No
export, no chip, library or protocol change**: the owner decides after the numbers.

## Owner's idea (24 Nov 2026)
Classes 1/2 become **going up** / **going down** = stairs + ramps, to raise accuracy. Same number of classes (8), so the
LIVE packet would not change; only the class names in the PC app and the watch.

## Facts to start from
- V4 has **never seen a ramp window**: ramps are left out of training (E1 report: a Camargo ramp file gave all counters
  0). `pipeline/camargo_replay.py` already labels `ramp_up` / `ramp_down` (classes 4/5 there).
- Known weak point on the owner's real device: **fast walking is called stairs**. Merging could make this worse
  (gentle ramps look like level walking). Measure it, do not assume.

## Data with ramps / slopes (check what is really there and say so)
- Camargo 2021: real shank IMU through `vimp` (22 people, ramps 5.2-18 deg in the trial names) **and** the replay.
- Luo 2020 (irregular surfaces): `SlpU` / `SlpD` slope trials next to `StrU` / `StrD` and `FE`, if present in our copy.
- Anything else with labelled ramps in `G:\My Drive\Walking_Gesture_Datasets` (list it; do not download).

## Variants (5-fold CV by person, 3 seeds, W = 4 s, hop 1 s, V4half settings, stairs rule 0.6)
1. **V4half today** (ramps unseen; evaluate ramp windows anyway: what does it say on ramps?)
2. **R-walk**: ramp windows labelled walking.
3. **M-all**: classes 1/2 = stairs + all ramps.
4. **M-steep**: ramps >= a slope cut (try 8 and 10 deg) into up/down, gentler ramps as walking.
For the merged variants also sweep the vote-share rule 0.5 / 0.6 / 0.7 / 0.8.

## Metrics, mean (sd) over seeds
- up / down recall and precision; stairs-only recall; ramp recall per slope band;
- **walking called up/down (%)** per dataset, especially fast walking (Lencioni fast, Luo FE, WearGait hurried,
  Camargo treadmill >= 1.4 m/s);
- no regression: walking recall per dataset, still, lying, sit-to-stand / stand-to-sit event recall, false events/hour;
- model size (nodes).

## Report
The table for all variants, the confusion matrices (walking / up / down / still at least), how many people and windows
each number rests on (ramps come from few people), and a one-screen summary for the owner (numbers only, no
recommendation). Measured numbers only; mark assumptions.
