# V1 fix (manager review, 18 Nov 2026)

Good set; numbers checked against the summary. Same branch `agent/V1` (`base: existing`). Fix these, re-run
`make_figures.py`, write `tasks/V1_fix_report.md` (five sections), commit it last.

## Content
1. **Rule 0.6 vs the summary (your point 1) — keep 0.6 in the figures** (it is what the chip runs). But
   `docs/STEP_D_SUMMARY.md` quotes the tuned-rule numbers (theta 0.5) under "vote share >= 0.6". Add a short
   "Correction (18 Nov 2026)" section there with the 0.6 numbers from your log: Lencioni fast, Luo FE, WearGait-PD
   HurriedPace walking-called-stairs; Luo stairs up/down recall and precision; PAMAP2 stairs up/down recall and precision;
   and say which file they come from. Do not change the old tables (history stays).
2. **A1 title**: neutral wording for talks: "Fast walking misread as stairs" (no "owner").
3. **B2 is wrong about the watch**: the watch is a BLE central that connects to the implant **directly**, in parallel
   to the XIAO bridge, not through the PC app. Draw: BLE packets -> XIAO bridge -> PC app, and BLE packets -> Guder
   watch (KNEIL mode). Also shrink the empty space in the boxes (box height from the text).
4. **C1**:
   - title "Where the evidence stands and what comes next" (the left column is results, not a plan);
   - "watch KNEIL mode" moves out of *Validated*: on hardware the first three flashes found three BLE bugs (W3-W5,
     `tasks/W3..W5_report.md`); put "watch live view on hardware (3 BLE bugs fixed, final check pending)" under
     *Not yet tested*;
   - add under *Not yet tested*: "V4 implant firmware on the real device (built, not yet run)";
   - box height from the text (less empty space).
5. **A5**: the simulated `still` row has 32 % predicted walking. Check what those windows are (source files and
   activity labels; e.g. weight shifting or the simulation's standing with sway) and write one sentence in the A5
   limits in `docs/FIGURES.md`. Do not change the data.
6. **B1**: Marpino (5 people) is missing from the dataset list; add it (from the window file). Box heights from the text.

## Layout
7. **A2**: the value labels overlap near 100 % (MHEALTH, CeTI, simulated). Put the labels inside the bar end (white
   text) or give the x axis room to 110; nothing may overlap.
8. **A4**: the y-axis labels of the three panels overlap each other on the left; shorten them or use panel titles.

## Checks
Re-run; per-panel sources printed; all PNG/SVG regenerated; the correction section's numbers match the log.
