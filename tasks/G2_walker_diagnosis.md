# Task G2 (worker gemini): why walker / crutch gait is called "still" (analysis only)

Branch `gemini/G2`, new from `main` in `kneil_v4_gemini`. Report `tasks/G2_report.md`, committed last. Read
`docs/PLAN_walker_gait.md` (this is its step 1). **No model training, no change to existing code or results**; new
analysis code goes to `pipeline/diag_walker_gait.py` (version line, log to `cache\`), outputs under `cache\g2\`.

## Do
1. **The motions**: for the 8 spacer-period personas of the viewer (`old_14`..`old_21`) and, for contrast, slow
   healthy walking (`old_00`, 0.5 m/s treadmill; Caicedo 0.6 m/s) and real still windows (standing/sitting from the
   window file): speed, cadence, steps per 4 s window, pause share, stance/swing of the implant leg.
2. **The decision**: per window, the V4 forest's votes per class (real export, `KNEIL_results\v4\tinyml_final_v4_lp6`
   joblib, or the chip library as the viewer does) and the 20 chip features. Which features separate these windows
   from real `still` and from slow walking? Show 3 plots under `cache\g2\` (e.g. the 2-3 most decisive features:
   walker windows vs still vs slow walking).
3. **Plausibility**: compare the personas' speed, cadence and pause share with published walker / crutch gait after
   knee surgery or in older adults (give the references you used; if you cannot access a source, say so). Are the
   personas realistic, too slow, too regular?
4. **Label rule proposal**: when should a 4 s window with an aid be "walking" (e.g. at least N steps or N heel strikes of
   either leg in the window)? Count how the 8 personas' windows would be labelled under 2-3 candidate rules.
5. **Public data**: list datasets with walker / rollator / crutch gait and body-worn IMUs or markers (name, people,
   sensors and positions, whether a shank or ankle signal exists, licence, download size). Say which could go through
   our virtual implant (needs a shank IMU with gyroscope, or leg markers).

## Report
The tables and plots above; a one-paragraph answer to "why still?" with the evidence; the label-rule table; the dataset
list. Measured numbers only; mark assumptions.
