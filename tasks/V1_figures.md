# Task V1: figures — accuracy, data handling, future work

Branch `agent/V1`, new from `main` in `kneil_v4_agent`. Report `tasks/V1_report.md`, committed last. Read `AGENTS.md`.
Only this repository; never push.

Goal: a small set of clear figures the owner can show (talks, supervisor meetings, thesis draft). Three groups.
**Every number in a figure must come from a file** (no number typed from memory); the script reads it and the report
says which file and column each panel uses.

## Output
- `pipeline/make_figures.py` (version 1.0): reads the result files, writes every figure as **PNG (300 dpi) and SVG**
  to `docs/figures/` (small files; commit them), prints the source of each panel, logs to `docs/figures/make_figures_log.txt`.
  matplotlib only (3.11 is installed; no new packages). It must run in under 2 minutes from the cached CSVs (no
  retraining, no window rebuilding).
- `docs/FIGURES.md`: one section per figure: the image, a 2-3 sentence caption in plain English, the source files, and
  what the numbers do **not** show (limits).

## Style
- 16:9-friendly size (e.g. 10 x 5.6 in) or a single column (6.5 in wide) for the thesis; readable at slide size
  (font >= 11 pt).
- One colour-blind-safe palette for the whole set; the same class always has the same colour (use the 8-class v2
  colours of `..\kneil_firmware\pc_app\kneil\protocol.py` `CLASS_COLOURS_V2` for classes); "today / V3" always grey,
  "V4" always one accent colour.
- Error bars = sd over the 3 seeds where the source has them; say "mean of 3 seeds, CV by person" on each accuracy
  figure. Mark simulated data as **simulated** in the panel itself.
- No chart junk: no 3D, no shadows, light grid only.

## A. Data accuracy (measured; cross-validation by person)
Sources: `KNEIL_results\v4\stepD\D1..D3\` (CSVs and summaries), `docs/STEP_D_SUMMARY.md`, `tasks/D1..D3_report.md`,
`tasks/E1_report.md`. V2/V3 per-dataset walking from `CLAUDE.md`'s table is allowed only if you also find it in a
results file under `KNEIL_results` (say which); otherwise leave V2 out.
1. **A1 Walking called stairs** (the owner's device problem): Lencioni fast walkers, Luo flat walking, WearGait-PD
   HurriedPace — today (V3recipe 2 s, no rule) vs V4half 4 s without rule vs V4half 4 s + rule (vote >= 0.6).
2. **A2 Walking recognised per dataset**: V3recipe 2 s vs V4half 4 s (+ rule), all datasets in the D results; show
   the number of people per dataset under each label; flag datasets with < 10 people.
3. **A3 Stairs**: Luo stairs up / down, recall and precision, today vs V4half 4 s vs V4half 4 s + rule; PAMAP2 as a
   second, weaker panel (7 people).
4. **A4 Window-length trade-off**: x = window length 2/3/4/5 s, lines: Luo stairs F0.5, simulated sit-to-stand event
   recall, false transition events per hour (second axis or small multiples). Mark the chosen 4 s.
5. **A5 Confusion matrix**, 8 classes, V4half 4 s, rule applied, row-normalised %, pooled over the CV predictions
   (`stepD\D2\pred_V4half_W4s_8cls_seed*.npz`, mean over seeds) with the window counts per row; one version for real
   data only, one for simulated only (sit-to-stand / stand-to-sit / bed transfer exist mostly in simulation).

## B. Data handling (diagrams, drawn with matplotlib patches/arrows; no numbers except sizes that are in reports)
1. **B1 Training data pipeline**: public datasets (shank IMUs, motion suits, markers, simulation) -> virtual implant
   (rigid-body transfer, one tibia frame per person, plausibility rule) -> implant-site 50 Hz signals -> 6 Hz low-pass
   -> 4 s windows, 1 s hop -> 20 C features (same C code as the chip) -> forest 20 x depth 10 -> CV by person ->
   export (emlearn) -> `kneil_tinyml` v2.0. Put dataset names and people counts from the reports.
2. **B2 On the device and after**: accelerometer 50 Hz -> low-pass -> window -> features -> forest -> stairs rule ->
   events (R1) + posture state -> daily metrics (40-byte summary) -> BLE (LIVE 22 B / s, SUMMARY 41 B, INFO) ->
   XIAO bridge -> PC app (live view, truth keys, recording) and Guder watch (KNEIL mode, live view). Sizes from E1/E2
   reports (RAM 3.4 kB classifier, 157 kB forest flash).
3. **B3 What leaves the implant** (privacy/energy view): raw stream only on request (RAW) vs the normal 1 Hz class
   packet and the daily summary; bytes per day for each (computed from the protocol sizes; say it is computed, not
   measured on air).

## C. Future work (a roadmap, clearly a plan, not results)
**C1** one figure, three columns: *validated* (measured: CV numbers, host/protocol tests, builds), *simulated only*
(transition events, bed transfer), *not yet tested* (real device recordings with truth keys, spacer-period gait with
walker/crutches, posture split on real people, watch as a full bridge, retraining with the owner's own recordings,
energy/battery measurement on the implant). Items from `docs/STEP_D_SUMMARY.md` "What is not proven yet", the E/W
reports' open questions, and the README. Plain text boxes; no dates unless they are in a file.

## Acceptance checks
1. `python pipeline/make_figures.py` runs clean and prints, per panel, the source file and the values plotted.
2. Spot check in the report: for A1, A3 and A4, print the plotted numbers next to the same numbers in
   `docs/STEP_D_SUMMARY.md`; they must match (or explain why, e.g. different pooling).
3. `docs/FIGURES.md` lists all figures with captions and limits; all images open; SVG and PNG for each.
4. No new package installed; no file outside `pipeline/make_figures.py`, `docs/figures/`, `docs/FIGURES.md`,
   `tasks/V1_report.md` changed.
