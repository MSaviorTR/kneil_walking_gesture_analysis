# Task G3 (worker gemini): why the two synthetic aid-gait sources disagree (analysis only)

Branch `gemini/G3`, new from `main`. Report `tasks/G3_report.md`, committed last. Read `tasks/A1_report.md`
(DeepSeek's experiment) and your own `tasks/G2_report.md` first. **Analysis only**: no training for a deployable
model, no change to existing code or results; new code `pipeline/diag_aid_gap.py` (version line, log), outputs under
`cache\g3\`.

## The problem
- Source 1, the new generator (`pipeline/aid_gait.py`, 462 personas from 21 Camargo people, A1): a forest trained with
  it recognises held-out aid gait at 99 %.
- Source 2, the 8 spacer personas of the old HTML viewer (`old_14`..`old_21`, AB07 strides; reproduced in
  `viewer/kneil_viewer.py`): the same forest still calls the ultra-slow walkers (`old_14`, `old_20`) 0 % walking.
- Removing AB07 from training changes nothing (A1 report 5.2), so it is not leakage. Neither source is real data.

## Find the cause
1. **Processing chain, side by side**: for each source, from joint angles to the 20 chip features: sampling rate
   (the old viewer embeds acc at 100 Hz, G2/V3 audit), resampling, low-pass, implant point and mount (the old viewer
   uses `sample_sensor()` jitter; A1 adds a random mount and 2-8 Hz "roughness"), how strides are stitched and pauses
   inserted (smooth vs abrupt), the weight-bearing "gain" of A1 (an assumption), gravity/frame handling. List every
   difference; mark each as measured from the code or assumed.
2. **Signals**: matched pairs (same aid type, similar speed and pause share, e.g. A1 pick-up walker 0.2 m/s vs
   `old_14`; A1 crutches vs `old_15`): plot 20 s of x/y/z at 50 Hz after the chip low-pass, the magnitude spectrum, and
   one stride overlaid. Where do they differ (amplitude, spectrum, pause shape, swing-phase peak)?
3. **Features**: the 20 features of the two sources (and real still, and real slow walking 0.5-0.6 m/s) as boxplots;
   which features separate source 1 from source 2 most (effect size)? Do they match the A1 forest's root splits
   (`hf_ratio`, `mean_z`, `ptp_m`, `mean_m`, `jerk_m`)?
4. **Swap test**: change one step of source 2's chain to source 1's (e.g. remove the roughness, use the same mount,
   same stitching) and re-run the A1 aid1.0 forest (from `KNEIL_results\v4\stepF`, or retrain the same variant in
   `cache\` only) on the changed signals; which single change moves `old_14`/`old_20` from 0 % to walking? Do the
   reverse on source 1 if useful.
5. **Which is closer to reality?** Compare both with real slow walking we have (Caicedo 0.6 m/s, WearGait-PD slow
   walkers, Camargo treadmill 0.5 m/s), on the features that differ. Say what real walker/crutch recordings must show
   to decide (a short checklist for the owner's recording: speeds, pauses, aids, durations, what to mark with the
   truth keys).

## Report
The difference table, the plots, the effect sizes, the swap-test result per change, and the recording checklist.
Measured numbers only; mark assumptions.
