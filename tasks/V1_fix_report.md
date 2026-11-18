# V1 fix report: figures, second pass

## 1. Status

Done. All seven review points and both layout points are in, the nine figures were regenerated (PNG + SVG) and the
0.6-rule numbers are recorded in `docs/STEP_D_SUMMARY.md` with their source.

## 2. Files

- `docs/STEP_D_SUMMARY.md` — new section **"Correction (18 Nov 2026): the rule numbers at vote share >= 0.6"**: the
  walking-called-stairs values (Lencioni fast, Luo FE, WearGait-PD HurriedPace), Luo and PAMAP2 stairs up/down
  recall + precision at `theta = 0.6, k = 1, n = 1`, the source files and the reference to the figure log. The old
  tables are unchanged.
- `pipeline/make_figures.py` — A1 title; A2 labels inside the bars (dark on the grey/light-blue series, white on the dark
  blue); A4 panel titles instead of y labels; B1 Marpino + per-box heights from the wrapped text; B2 corrected topology
  and per-box heights; C1 new title and items; `measure()`/`axes_height_in()` helpers so box heights follow the text.
- `docs/figures/*.png`, `docs/figures/*.svg`, `docs/figures/make_figures_log.txt` — all regenerated.
- `docs/FIGURES.md` — A1 caption/title, B1 sources (datasets by sensor type), B2 text (watch parallel to the bridge),
  C1 caption/roadmap items, A5 limit note (the simulated still -> walking cell).
- `tasks/V1_fix_report.md` (this file).

## 3. Commands

```
python pipeline/make_figures.py
python -c "import matplotlib.image as m, glob, os; [print(p, m.imread(p).shape, os.path.getsize(p)//1024) for p in glob.glob('docs/figures/*.png')]"
python -c "import xml.etree.ElementTree as ET, glob; [ET.parse(p) for p in glob.glob('docs/figures/*.svg')]; print('svg ok')"
```

## 4. Acceptance checks

1. **Re-run, sources printed, all images regenerated** — PASS: exit 0 in 7.8 s; the log lists the source and values for
   every panel; 18 images rewritten (A1 153 kB, A2 210, A3 208, A4 184, A5 238, B1 286, B2 250, B3 150, C1 370 kB PNG;
   SVG 14-47 kB; all SVGs parse).
2. **Correction section numbers match the log** — PASS (values copied from `make_figures_log.txt`, same run):

   | correction table | log line |
   |---|---|
   | Lencioni fast 0.61 | `V4half 4 s + rule 0.6 | Lencioni speed_abs=fast: 0.61 % (sd 0.16, n 709)` |
   | Luo FE 1.22 | `… | Luo surface=FE: 1.22 % (sd 0.54, n 3620)` |
   | WearGait-PD HurriedPace 1.13 | `… | WearGait-PD rec=HurriedPace: 1.13 % (sd 0.21, n 5182)` |
   | Luo up 43.4 / 85.9 | `Luo stairs_up recall_pct … 43.4` / `precision_pct … 85.9` |
   | Luo down 89.2 / 69.4 | `Luo stairs_down recall_pct … 89.2` / `precision_pct … 69.4` |
   | PAMAP2 up 23.6 / 25.0 | `PAMAP2 stairs_up … 23.6` / `… 25.0` |
   | PAMAP2 down 38.0 / 35.4 | `PAMAP2 stairs_down … 38.0` / `… 35.4` |
3. **A1 title** — PASS: "A1 Fast walking misread as stairs" (no "owner").
4. **B2 topology** — PASS: BLE packets -> XIAO bridge -> PC app, and BLE packets -> Guder watch on a second branch with
   the label "BLE, direct (central)"; the watch box no longer sits behind the PC app. Box heights now follow the text.
5. **C1** — PASS: title "Where the evidence stands and what comes next"; "watch live view on hardware (3 BLE bugs fixed,
   final check pending)" and "V4 implant firmware on the real device (built, not yet run)" are under *Not yet tested*;
   "watch KNEIL mode" is no longer in *Validated* (now "BLE protocol v2 and the PC app v2: tests and builds PASS"); the
   boxes are as tall as the text.
6. **A5 simulated still -> walking** — PASS (checked, data unchanged): the 32 % comes entirely from the Camargo replay
   — 3,506 of its 8,755 standing windows (40 %) are called walking, the v1.6 synthetic still windows are not affected
   (0 of 1,764). The sentence is in the A5 limits of `docs/FIGURES.md`.
7. **B1 Marpino** — PASS: "Marpino 5" is in the shank-IMU list, taken from the window file like the other counts.
8. **A2 labels, A4 axis labels** — PASS: A2 values are inside the bar ends (no overlap, contrast per series); A4 uses
   one-line panel titles above each panel and offsets the labels at 4 s, so no y labels can collide.

## 5. Problems and open questions

1. The box heights are computed from the wrapped text and the axes height in inches; if the text of a box changes, the
   layout follows automatically. Boxes in one row are top-aligned with ragged bottoms (deliberate: equal heights left
   empty space).
2. The C1 panel uses 10 pt text (the densest figure); the charts are 11-13 pt. It reads at slide size but if the owner
   wants it bigger, the figure needs a taller canvas, not a smaller font.
3. **Rule 0.6 stays in the figures** as the reviewer asked; the step D tables keep the tuned-rule (0.5) history and the
   new correction section gives the 0.6 numbers.
4. Nothing else changed; `git status` before the report showed only the files listed above.
