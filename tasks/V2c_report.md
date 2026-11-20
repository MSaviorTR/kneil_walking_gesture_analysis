# V2c report: band 3 overlap and the box-aware layout check

## 1. Status

Done. The band-3 lanes no longer touch the watch-log line, `check_layout()` now measures drawn boxes against texts
(and texts inside them), the overview is rebuilt with 0 problems, and every other figure is byte-identical.

## 2. Files

- `pipeline/make_figures.py` — band 3 gets its height from the space above the footer (gridspec bottom 0.075 → 0.050,
  band-3 ratio 1.05 → 1.30); the lanes and the watch-log line repositioned; new `_BOXES` registry and box-vs-text
  check; the (d) boxes enlarged/moved so their labels are 20 mil inside them.
- `docs/figures/OVERVIEW_kneil_v4.png` (3899 x 2244, 300 dpi), `.svg` (text as paths), `.pdf` (TrueType).
- `docs/figures/make_figures_log.txt` — the check line now includes the box count and the smallest box-text gap.
- `tasks/V2c_report.md` (this file).

No numbers, no texts, no captions changed; no other figure changed.

## 3. Commands

```
python pipeline/make_figures.py --only overview
python pipeline/make_figures.py
```

Crops (not committed, `cache\`): `v2c_before_band3.png`, `v2c_after_band3.png` (band 3 from the V2b PNG in git HEAD
and from the new PNG).

## 4. Acceptance checks

1. **Runs clean** — PASS: `--only overview` and the full run exit 0 (about 6 s / 10 s).
2. **Extended check, 0 problems** — PASS:
   `layout check: 137 texts, 9 cards, 8 boxes, 0 label/marker hit(s), 0 problem(s); smallest text-text gap 21 mil,
   smallest text-card margin 35 mil, smallest box-text gap 25 mil`.
   The box rule: every text whose centre lies inside a drawn box must be at least 20 mil inside its edges, every text
   outside must keep 20 mil from the box; the smallest gap is reported. Run on the V2b code, the same check reported
   the defect directly: `lane Measured/Simulated only/Not yet tested: text outside it by only -5 mil: "Owner's watch
   log, 17 Nov 2026..."` (the line was 5 mil *inside* the lanes), plus two (d) boxes whose labels filled them
   (BLE v2 -9 mil, PC app 1 mil). Those are fixed.
3. **Band 3** — PASS: the lanes end 25 mil above the watch-log line and the line sits 22 mil above the card edge
   (crop: `cache/v2c_before_band3.png` shows the lane borders crossing the line; `cache/v2c_after_band3.png` shows the
   gap). The height came from the footer space: the gridspec's bottom moved from 0.075 to 0.050 and band 3's ratio from
   1.05 to 1.30. The actual card heights: band 1 1.952 → 1.926 in, band 2 2.392 → 2.359 in (the proportional split
   lost 0.03 in each), band 3 1.025 → 1.252 in (+0.23). Bands 1-2 were not deliberately reduced.
4. **Other figures byte-identical** — PASS: `git status` shows only the three overview files, the log and the script.
5. **Optional 'x anterior'** — **not done**: next to the arrow tip (inset x 0.78) the label would run into the
   formula/validation column (the card is only 3.03 in wide); it stays under 'implant', which now has clear space.

## 5. Problems and open questions

1. The (d) boxes grew to satisfy the "text 20 mil inside" rule: the BLE box is 0.180 of the card (was 0.145) and the
   PC-app box 0.47 x 0.195 (was 0.44 x 0.155) — visually slightly larger, same text.
2. The box check treats a box as a rectangle from `get_window_extent()`; the rounded corners are inside it, so the
   rule is conservative there.
3. Bands 1-2 lost 0.03 in each through the proportional GridSpec split when band 3 grew. Everything still passes the
   20 mil rule; if the owner wants the old band 1-2 heights exactly, the cards would have to be placed with explicit
   positions instead of a GridSpec.
4. The check still cannot judge contrast or aesthetics; the crops (band 3, (b), panel titles) are the visual record.
