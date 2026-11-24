# Task R1 (worker gemini): gait recovery score from the implant, after Ghaffari et al. 2025 (analysis only)

Branch `gemini/R1`, new from `main`. Report `tasks/R1_report.md`, committed last. New code `pipeline/gait_score.py`
(version line, log, resume). Outputs under `cache\r1\` and `KNEIL_results\v4\stepI\` (new allowed folder).
**Analysis only**: no chip, library or protocol change. `pip install spm1d` is allowed.

## Owner's idea (24 Nov 2026)
Score activity and healing progress the way Ghaffari et al. (J Orthop Res 2025;43:2165-2177,
doi 10.1002/jor.70058) do after TKA. Their method (the owner's PDF; the manager read it):
- thigh accelerometer, **12.5 Hz**, 31 patients, 2 weeks before to 90 days after TKA; walking bouts > 60 s, the 3
  longest per day; strides from peaks of the vector magnitude, foot contact / foot off, time-normalised cycles;
- 6 Hz 4th-order Butterworth on |a|; **SPM** (spm1d, repeated-measures ANOVA + Bonferroni post-hoc t-tests) on the
  mean |a| stride waveform per period (pre-op, months 1, 2, 3): differences mainly in mid-stance and terminal swing;
- **power of the first 5 FFT harmonics** per stride, per axis and |a|; stride time and duty factor; weekly changes vs
  weekly EQ-5D-3L / VAS change; LASSO logistic regression, responder AUC 0.80-0.81 (17 patients with full PROMs).

## Our differences (keep in mind, say what they change)
Tibia, not thigh; 50 Hz (harmonics up to ~10 usable); implant fixed in the bone (no re-attachment error); the chip
already finds walking windows; we have **no post-op longitudinal data and no PROMs**, so the score can only be tested
for sensitivity to gait impairment and for repeatability, not validated against recovery.

## Do
1. **Stride extraction** from the implant signal (`windows`/stage-2 data, real datasets): bouts of walking, strides
   from the tibia signal (the sagittal swing peak is clearer at the tibia than |a|; compare both), time-normalised to
   101 points; stride time, stance share (duty factor) if foot contact can be found; quality rules (say which).
2. **Features**: mean |a| and per-axis stride waveform; power of harmonics 1-10 per axis and |a|; stride time; duty
   factor; stride-to-stride variability.
3. **Sensitivity**: SPM1D two-sample tests (and the harmonic powers, effect sizes) between groups we have: knee
   patients (KneE-PAD, Marpino) vs healthy of similar age; Parkinson vs controls (WearGait-PD); walking-aid gait
   (A1 personas) vs normal; slow vs normal speed in the same people (speed is the main confounder: show it, and
   compare at matched speed).
4. **Repeatability**: within-person between-bout and between-session spread of each feature (MDC95), as in L1.
5. **A score**: a 0-100 "gait similarity" score of a person's daily mean stride vs (a) a healthy reference band and
   (b) the person's own baseline (first week). Show it on the groups above and how it moves with speed.
6. **On-chip cost**: what a daily summary would need (e.g. a 32-point mean |a| stride template x 1 byte + 10 harmonic
   powers x 3 axes x 1 byte + stride time + duty factor), bytes and FLOPs per stride, and how much the score loses
   when built from that compressed form instead of the full data.

## Report
Plots (SPM curves with the significant regions, harmonic boxplots, score per group), the repeatability table, the byte
budget, a one-screen summary, and what a longitudinal patient study must collect to validate the score (PROMs, visits).
