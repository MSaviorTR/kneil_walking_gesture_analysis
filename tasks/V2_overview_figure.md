# Task V2: one overview figure ("graphical abstract") of KNEIL V4

Branch `agent/V2`, new from `main` in `kneil_v4_agent`. Report `tasks/V2_report.md`, committed last. Read `AGENTS.md`.
Only this repository; never push. No new packages (matplotlib 3.11, numpy, pandas only).

## Goal
One figure that tells the whole V4 story on a single slide: where the data come from, how the implant signal is made,
what runs on the chip, how the result reaches the PC and the watch, what improved (measured), and what is still open.
It must look polished (clear hierarchy, big key numbers, compact modern charts, a clean schematic) and stay honest
(measured vs simulated vs not tested; the costs are shown too, not only the gains).

## Output
- `pipeline/make_figures.py` -> version 1.1: a new function for the overview that reuses the existing loaders (same
  files, same numbers as A1-C1) and a new option `--only overview` to run it alone. All other figures must come out
  unchanged except C1 (see below): compare the PNGs before and after and report the result.
- `docs/figures/OVERVIEW_kneil_v4.png` (300 dpi), `.svg` and `.pdf` (vector, for the thesis and posters).
- A new first section in `docs/FIGURES.md`: the image, a 3-4 sentence caption, sources, limits.

## Canvas and style
- 16:9, 13.33 x 7.5 in (one slide). It must also read when printed on A4 landscape: body text >= 9 pt, panel titles
  12 pt, main title 20 pt, key numbers 24-32 pt.
- White background; each panel on a very light rounded card with a panel letter (a, b, c, ...). No 3D, shadows,
  gradients or clip art. Same palette as A1-C1: grey = today (V3recipe 2 s), one blue accent = V4 (V4half 4 s + rule
  0.6), class colours from `..\kneil_firmware\pc_app\kneil\protocol.py` CLASS_COLOURS_V2, status colours as in C1.
- Use an explicit GridSpec (or constrained layout). Nothing may overlap or be cut off.

## Layout (header + three bands + footer)
**Header**: title "KNEIL V4: an implant that tells walking from stairs"; subtitle "activity recognition in an
instrumented knee spacer: data, chip, link and results (Nov 2026)".

**Band 1, how it works** (left to right, thin arrows between the cards):
- (a) *Data*: a dot grid (waffle), one dot per person, coloured by dataset: the 9 real datasets filled, the simulation
  (60 synthetic personas + Camargo replay, 22) as hollow dots. Legend with counts; print the total number of real
  people. Counts from the window file, as in B1.
- (b) *Virtual implant*: a simple, clean side-view schematic (stylised, not anatomical): femur, spacer insert, tibia;
  the shank sensor on the tibia, the lever arm r to the implant point (2.5 cm below the joint centre, 5 mm anterior),
  device axes x anterior and z superior. Under it the formula f_P = f_S + alpha x r + omega x (omega x r) and
  "validated on Camargo, 22 people: |a| r = 0.93" (from `CLAUDE.md`). If the schematic does not look clean, use a
  labelled block diagram instead and say so in the report.
- (c) *On the chip*: a vertical mini pipeline: 50 Hz accelerometer -> 6 Hz low-pass -> 4 s window, 1 s hop -> 20
  features -> forest 20 trees x depth 10 -> stairs rule (vote >= 0.6) -> events (R1) + posture -> daily summary.
  Measured sizes from `tasks/E2_report.md`: forest 157 kB flash, classifier 3.4 kB RAM, whole firmware 387 kB flash /
  52 kB RAM.
- (d) *Live view*: implant -> BLE (LIVE 22 B every second, SUMMARY 41 B, INFO) -> XIAO bridge -> PC app (live view,
  truth keys, recording); and, directly, the Güder watch (KNEIL mode). Protocol sizes only.

**Band 2, what changed** (measured; label the band "5-fold CV by person, mean of 3 seeds"):
- (e) *Key numbers*: two or three large tiles: walking misread as stairs, Luo level walking 17.5 % -> 1.2 %,
  Lencioni fast walkers 12.8 % -> 0.6 % (and WearGait-PD hurried 7.9 % -> 1.1 % if it fits).
- (f) *Walking recognised per dataset*: a dumbbell chart (grey dot = today -> blue dot = V4, thin line between),
  sorted, the people count next to each name; datasets with < 10 people marked with a dagger; the simulated row in
  italics.
- (g) *Stairs, the honest trade-off*: dumbbells for recall and precision of Luo stairs up, Luo stairs down, PAMAP2
  stairs up, PAMAP2 stairs down (today -> V4 + rule 0.6). Precision rises; Luo stairs-up recall falls (50 -> 43 %) and
  PAMAP2 recall falls: this must be visible, not hidden. PAMAP2 marked (7 people).
- (h) *Window length*: a small two-line chart over 2-5 s: Luo stairs F0.5 and sit-to-stand event recall (label it
  "simulated"), 4 s marked. Optional if space is short; then give the two values at 4 s as text in (e).

**Band 3, where it stands**: one row of three coloured lanes, short items, at most 4 each:
- *Measured*: CV by person on 9 datasets; chip C code = Python model (host test PASS); firmware built, flash and RAM
  measured; BLE protocol v2 and PC app tests PASS.
- *Simulated only*: sit-to-stand / stand-to-sit events (78 % recall at 4 s; 0.9 false events per hour on recordings
  without transitions); bed transfer.
- *Not yet tested*: recordings with the truth keys on the real device; sitting vs standing split on real people;
  spacer-period gait (walker, crutches); energy and battery.
- One line under the lanes, a **manager-provided fact** (not in a file yet; cite it in FIGURES.md as "owner's watch
  log, 17 Nov 2026"): the implant already runs the V4 firmware (the watch found its protocol-v2 SUMMARY
  characteristic); the watch live view needed three BLE fixes and its final check is pending.
- Update C1 the same way: replace "V4 implant firmware on the real device (built, not yet run)" with "V4 implant
  firmware: flashed, BLE v2 service seen by the watch; live classes not yet checked against truth".

**Footer** (small, grey): "Today = V3recipe, 2 s windows. V4 = new data at half weight, 4 s windows, stairs only if
>= 60 % of the trees agree. Simulated = 60 synthetic personas + Camargo replay. Sources: docs/FIGURES.md."

## Acceptance checks
1. `python pipeline/make_figures.py --only overview` runs clean and prints every number in the overview with its
   source. The full run still makes all figures; all old PNGs pixel-identical except C1 (report the comparison).
2. Every number in the overview equals the same number in A1-A4 / the log: list them in the report.
3. PNG (300 dpi), SVG and PDF open. Nothing overlaps or is cut off: check it in code (every text's
   `get_window_extent()` inside its card and not intersecting another text) and say what you checked.
4. Report: the panel list, the font sizes used, and anything you simplified or dropped.
