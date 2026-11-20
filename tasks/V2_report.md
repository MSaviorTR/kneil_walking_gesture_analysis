# V2 report: one overview figure (graphical abstract) of KNEIL V4

## 1. Status

Done. `pipeline/make_figures.py` is at 1.1 with a one-slide overview (`--only overview`), written as PNG (300 dpi),
SVG and PDF, all numbers reused from the same loaders as A1-C1, the layout checked in code, and the old figures unchanged
except C1.

## 2. Files

- `pipeline/make_figures.py` (v1.1) — new `fig_overview()`, the card helpers and `check_layout()`, `--only NAME`
  (default: all ten figures), `save(..., pdf=True)`, version 1.1; C1's "V4 implant firmware" item replaced as the
  manager asked.
- `docs/figures/OVERVIEW_kneil_v4.png` (3899 x 2244 px, 300 dpi), `OVERVIEW_kneil_v4.svg` (166 kB),
  `OVERVIEW_kneil_v4.pdf` (87 kB, vector text).
- `docs/figures/make_figures_log.txt` — new `[overview]` section with every plotted number and its source.
- `docs/FIGURES.md` — intro updated (ten figures, `--only overview`, PDF) and a new first section for the overview
  (image, 4-sentence caption, sources, limits).
- `docs/figures/C1_future_work.png/.svg` — regenerated with the corrected firmware item (expected change).
- `tasks/V2_report.md` (this file).

## 3. Commands

```
python pipeline/make_figures.py --only overview
python pipeline/make_figures.py
python -c "import matplotlib.image as m; print(m.imread('docs/figures/OVERVIEW_kneil_v4.png').shape)"
python -c "import xml.etree.ElementTree as ET; ET.parse('docs/figures/OVERVIEW_kneil_v4.svg'); print('svg ok')"
# PDF: header %PDF-1.4, contains /Type /Page, ends %%EOF (see 4.3)
```

## 4. Acceptance checks

1. **`--only overview` runs clean, prints every number with its source** — PASS (exit 0, 7-8 s; full run 10.6 s). The log
   prints, for example:

   ```
   [overview] sources: people = windows_v11/W4s ... walking/stairs/called = D2 pred_* + stairs_rule (0.6) and
   D3 stairs_rule_results.csv (today); window-length curves = D3 CSVs; sizes = tasks/E2_report.md; packet sizes =
   ../kneil_firmware/protocol/kneil_proto.h; colours = ../kneil_firmware/pc_app/kneil/protocol.py
      (a) people: WearGait-PD=109, Lencioni=50, Caicedo older adults=41, ... total real=312; simulated=60+22=82
      (c) sizes: forest 157366 B, classifier 3436 B, firmware 386664 B flash / 51632 B RAM (tasks/E2_report.md)
      (e) key numbers: Luo FE 17.47 -> 1.22, Lencioni fast 12.84 -> 0.61, WearGait hurried 7.91 -> 1.13
      (f) walking recall: MHEALTH=100.0->100.0, ... KneE-PAD=64.3->71.3
      (g) stairs (today -> V4+rule): Luo up · recall=50.4->43.4, ... PAMAP2 (7) down · precision=18.9->35.4
      (h) window: F0.5 2s=76.0, 3s=78.3, 4s=82.4, 5s=84.8; STS 2s=83.3, 3s=81.1, 4s=78.1, 5s=64.3
   ```

   Full run: all ten figures written. Old PNGs compared by SHA-256 before/after: **A1, A2, A3, A4, A5, B1, B2, B3
   byte-identical; C1 changed** (the new firmware item, as requested). The old SVGs differ only in matplotlib's embedded
   `dc:date` and the random clip-path ids (geometry identical; the byte-identical PNGs prove it).
2. **Every overview number equals A1-A4 / the log** — PASS. The overview calls the same `lookup()` (D2 predictions +
   windows, 0.6 rule) and the same CSV columns as A1-A4; the printed values match the A1/A2/A3/A4 logs exactly:

   | overview panel | value | same value in |
   |---|---|---|
   | e Luo level walking | 17.47 → 1.22 | A1 `Luo surface=FE` 17.47 → 1.22 |
   | e Lencioni fast | 12.84 → 0.61 | A1 `Lencioni speed_abs=fast` 12.84 → 0.61 |
   | e WearGait-PD hurried | 7.91 → 1.13 | A1 `WearGait-PD rec=HurriedPace` 7.91 → 1.13 |
   | f walking recall, 9 rows | e.g. KneE-PAD 64.3 → 71.3, Luo 80.2 → 97.7 | A2 log (same rows) |
   | g stairs, 8 rows | Luo up 50.4→43.4 / 41.3→85.9, PAMAP2 down 52.6→38.0 / 18.9→35.4 | A3 log (same rows) |
   | h Luo stairs F0.5 | 76.0 / 78.3 / 82.4 / 84.8 | A4 log |
   | h STS recall (simulated) | 83.3 / 81.1 / 78.1 / 64.3 | A4 log |
   | c sizes | 157 kB forest, 3.4 kB classifier, 387 kB / 52 kB firmware | `tasks/E2_report.md` (157,366 / 3,436 / 386,664 / 51,632 B) |
   | d packet sizes | LIVE 22 B/s, SUMMARY 41 B/min | `kneil_proto.h` (22 / 41) |
   | a people | 312 real + 82 simulated | B1 log (same people counts) |
3. **PNG/SVG/PDF open; nothing overlaps or is cut off** — PASS. PNG 3899 x 2244 px (300 dpi), SVG parses, PDF is a
   valid 1-page %PDF-1.4 file with vector text. The layout is checked *in code* after drawing (`check_layout()`):
   every text object's `get_window_extent()` must lie inside its card's bbox (cards and their inset axes) and inside the
   figure, and no two texts may intersect (axis-aligned boxes shrunk by 0.6 px, so touching is allowed). Result:
   **139 texts, 9 cards, 0 outside, 0 overlapping**; the run aborts with a non-zero exit if any check fails (it did
   during development, and the problems were fixed rather than silenced).
4. **Report: panel list, font sizes, simplifications** — see below.

### Panel list

| | panel | content |
|---|---|---|
| header | title + subtitle | 20 pt bold title, 11 pt subtitle |
| 1 | a Data | waffle, one dot per person: 9 real datasets (filled, dataset colours) + 82 simulated streams (hollow), 2-column legend with counts, "312 people in 9 public datasets" |
| 1 | b Virtual implant | stylised femur / spacer / tibia, shank IMU, lever arm r, implant point, axes x (anterior) and z (superior), formula and the Camargo validation |
| 1 | c On the chip | 7-step pipeline, measured sizes (forest 157 kB flash, classifier 3.4 kB RAM, firmware 387 kB / 52 kB) |
| 1 | d Live view | implant → BLE v2 (LIVE 22 B/s · SUMMARY 41 B/min · INFO) → XIAO bridge → PC app; and directly → Güder watch (KNEIL mode) |
| 2 | e Key numbers | three large numbers: 17.5→**1.2**, 12.8→**0.6**, 7.9→**1.1** (% walking called stairs) |
| 2 | f Walking recognised | dumbbells (grey today → blue V4), sorted, people counts, dagger < 10, simulated italic |
| 2 | g Stairs: the honest trade-off | 8 dumbbells (Luo/PAMAP2 up/down × recall/precision); the falling recalls are printed in red and the note says the rule trades recall for precision |
| 2 | h Window length | Luo stairs F0.5 and simulated STS recall over 2-5 s, 4 s marked, 4 s values annotated |
| 3 | i Where it stands | three lanes (measured / simulated only / not yet tested), 4 items max, plus the owner's watch-log line |
| footer | | definitions (today, V4, simulated) and the source pointer |

### Font sizes

main title 20 pt, subtitle 11, panel letters and titles 12, key numbers 24, body text 9 (card text, chart labels and
legends, status lanes, band labels), footer 8 (the task calls the footer "small, grey").

### Simplified or dropped

- (b) is a **stylised** schematic (rounded blocks for femur/spacer/tibia), not anatomical; the lever arm is the vector
  from the shank IMU to the implant point with the length labelled "r" (Luo's 0.26 m is data-driven, so no single value
  is printed).
- (c) merges "events (R1) + posture" and "daily summary" into one step and gives the sizes as two text lines; the MTU
  and the single-tree option are not shown.
- (d) shows the watch as a **second, direct** BLE consumer (not through the PC app); RAW is noted only in the log, not
  drawn, to keep the card clean.
- (h) is optional in the task; it is kept but compact (two lines, 4 s values annotated).
- (a) uses short dataset names ("Caicedo" for "Caicedo older adults") to fit 9 pt; the full name is in the sources.
- (f) shows the 8 CV datasets + simulated. Caicedo is in the waffle (a) but has no CV row in the D tables (it is the
  external marker set), so it is not in the dumbbells.

## 5. Problems and open questions

1. **The watch-log line is not in a file**: "Owner's watch log, 17 Nov 2026: the implant runs the V4 firmware (the watch
   found its protocol-v2 SUMMARY characteristic); the watch live view needed three BLE fixes, final check pending" is
   the manager's fact. `docs/FIGURES.md` cites it as the owner's watch log, not as a result file.
2. **A4-compatible legibility**: the canvas is 13.33 x 7.5 in with body text 9 pt; printed on A4 landscape (scale ~0.88)
   that is about 7.9 pt on paper. If the owner wants >= 9 pt *after* scaling, the canvas must grow (e.g. 15 x 8.4 in) —
   the layout is code, one constant.
3. **PDF fonts**: the SVG/PDF embed text as text (`svg.fonttype = none`), so the PDF uses the viewer's DejaVu Sans
   metrics; on a machine without it the text may reflow slightly. The PNG is the safe copy for printing.
4. **C1 changed** (expected) with the corrected firmware item; its text is the manager's wording, verbatim.
5. The overview re-uses A1-A4's numbers, so if the step D results change, both the detail figures and the overview move
   together; nothing is typed by hand.
