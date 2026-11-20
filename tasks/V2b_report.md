# V2b report: overview layout polish

## 1. Status

Done. The three layout problems are fixed, `check_layout()` now enforces a 20 mil (6 px at 300 dpi) minimum gap and
reports it, the overview was rebuilt, and every other figure is byte-identical.

## 2. Files

- `pipeline/make_figures.py` — `_card()` puts the letter 0.04 in from the card edge and the title 0.20 in later (inches,
  so identical on all nine cards); the band ratios are `[2.00, 2.45, 1.05]`; (b) redrawn with a wider drawing and a
  text column in its own space, `spacer` with a leader line; band 3 lanes start at the top of the card; `check_layout()`
  adds the 20 mil pairwise/text-to-edge rule, the smallest-gap report, and still checks `ax.get_tightbbox()` per axes and
  the value labels against the markers.
- `docs/figures/OVERVIEW_kneil_v4.png` (3899 x 2244, 300 dpi), `.svg` (text as paths, no date), `.pdf` (TrueType,
  `/FontFile2`).
- `docs/figures/make_figures_log.txt` — new check line with the smallest gaps.
- `tasks/V2b_report.md` (this file).

No caption in `docs/FIGURES.md` changed, no number or text content changed, no other figure changed.

## 3. Commands

```
python pipeline/make_figures.py --only overview
python pipeline/make_figures.py
python -c "import re; s=open('docs/figures/OVERVIEW_kneil_v4.svg').read(); p=open('docs/figures/OVERVIEW_kneil_v4.pdf','rb').read(); print(len(re.findall(r'<text', s)), 'dc:date' in s, b'/FontFile2' in p)"
# crops: cache/v2b_{before,after}_{b,titles,band3}.png (System.Drawing, fractions of the PNG)
```

## 4. Acceptance checks

1. **`--only overview` and the full run** — PASS: both exit 0 (5.8 s / 10.5 s), and the extended check reports
   `137 texts, 9 cards, 0 label/marker hit(s), 0 problem(s)`.
2. **Minimum gap, before/after** — PASS. The same check run on the V2 code found **50 violations**, with the smallest
   text-text gap **-12 mil** (the (a) legend rows '■ Caicedo 41' and '■ CeTI 32' overlapped) and the smallest
   text-to-card margin **9 mil** ('firmware 387 kB flash...' in (c)). After the polish: smallest text-text gap
   **21 mil** ('recall (%)' / '50' in (f)), smallest card margin **32 mil** ('□ simulated 82' in (a)). The rule is
   20 mil = 6 px of a 300 dpi print (0.02 in); gaps are measured from the renderer's text boxes in both axes
   (Chebyshev: a pair is flagged when it is closer than 20 mil horizontally *and* vertically). No exception list was
   needed.
3. **Other figures byte-identical** — PASS: `git status` shows only the three overview files, the log and the script;
   the A1-A5, B1-B3 and C1 PNG and SVG files are unchanged (the SVGs were already reproducible).
4. **Formats** — PASS: PNG 3899 x 2244 at 300 dpi; overview SVG has 0 `<text>` elements and no `dc:date`; the PDF
   contains `/FontFile2`.
5. **Point-by-point**:
   1. **(b) crowded** — the drawing now takes 0.48 of the card width and the formula/validation/point text sits in a
      column starting at 0.52 with 100+ mil margins; 'validated on / Camargo, 22 people: / |a| r = 0.93 / 0.27 g RMS'
      and 'implant point: / 2.5 cm below the / joint, 5 mm anterior' are re-wrapped (same words) so they fit; 'spacer'
      has a leader line; 'x anterior', 'z up', 'implant', 'tibia' and 'r' each have clear space.
   2. **Panel letters** — one helper: letter at 0.04 in, title at 0.20 in from the edge on every card, in inches
      (before, the same axes fraction gave 0.13-0.43 in depending on the card width).
   3. **Band 3** — the lanes now start at the top of the card (0.975) and the watch-log line sits below them; the freed
      height went to band 2 (2.39 in, needed by the 8-row stairs panel and its 3-line note) and band 1 (1.95 in, needed
      by the 10-row one-column legend); band 3 is 1.03 in and just holds header + 4 items + the watch-log line.
6. **Crops** (not committed, under `cache\`): `v2b_before_b.png` / `v2b_after_b.png` (the (b) card),
   `v2b_before_titles.png` / `v2b_after_titles.png` (the panel-title strip), `v2b_before_band3.png` /
   `v2b_after_band3.png` (band 3). The before (b) shows 'x anterior' almost touching 'validated on Camargo', 'spacer'
   against the bar and 'z up' against the femur; the after (b) shows the spaced version. The titles crop shows the
   uniform letter/title spacing; the band-3 crop shows the lanes at the top instead of after a gap.

## 5. Problems and open questions

1. The 20 mil rule is strict for a dense slide: the one-column legend (10 rows at 9 pt) fits in band 1 only because the
   title moved to the top of the card (it was at 0.935 of the card, wasting 0.13 in). The bands' ratios changed
   accordingly; band 3 is now the tightest part.
2. Some labels are necessarily close to their object: the 'r' label sits next to the dashed lever arm, and 'x anterior'
   sits on the tibia block (choosing the other side would collide with the text column). Both pass the 20 mil rule
   against other texts, but a human look at the crops is still worthwhile.
3. The check measures text boxes and axes boxes, not the lane/box rectangles; I placed the band-3 items by eye inside
   the lanes (the crop shows them inside).
4. The overview is the only file with content changes; nothing else in the repository moved.
