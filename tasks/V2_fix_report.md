# V2 fix report: overview figure, second pass

## 1. Status

Done. All fourteen review points are addressed, the overview was rebuilt, the layout check now covers tick labels and
value labels, the SVGs/PDF meet the font requirements, the old figures are unchanged (C1 only, for the CV wording), and
the people counts are explained with a table.

## 2. Files

- `pipeline/make_figures.py` — (f) styles from the sorted rows + asserts; (g) short labels, value labels away from the
  grey dot, note generated from the values; (a) 20 x 20 waffle; (b) lever-arm label and axis words; (d) spacing; (e)
  alignment; (h) right-end labels, no legend, `%` axis; (i) no title, full wording; `check_layout()` extended
  (`ax.get_tightbbox()` per axes inside its card, label/marker hits); overview SVG with text as paths, `svg.hashsalt`
  fixed, no `dc:date`, `pdf.fonttype = 42`; C1 CV wording.
- `docs/figures/OVERVIEW_kneil_v4.png/.svg/.pdf` — regenerated (PNG 3899 x 2244; SVG 381 kB paths; PDF 78 kB, TrueType).
- `docs/figures/C1_future_work.png/.svg` — only for point 5 ("8 real datasets + simulation").
- `docs/figures/make_figures_log.txt` — new values and the check summary.
- `docs/FIGURES.md` — overview limits: the definition of "people" (CV group with a 4 s window), the Marpino/PAMAP2/
  Caicedo details and the 265 = 109 + 32 + 28 + 10 + 8 + 78 split.
- `tasks/V2_fix_report.md` (this file).

## 3. Commands

```
python pipeline/make_figures.py --only overview
python pipeline/make_figures.py
python -c "import re; s=open('docs/figures/OVERVIEW_kneil_v4.svg').read(); p=open('docs/figures/OVERVIEW_kneil_v4.pdf','rb').read(); print('text',len(re.findall(r'<text',s)),'date','dc:date' in s,'fontfile2',b'/FontFile2' in p)"
# hashes: Get-FileHash on docs/figures/*.png before/after; SVG hashes before/after a re-run
```

## 4. Acceptance checks

1. **Runs clean** — PASS: `--only overview` exit 0 (7-8 s), full run exit 0 (10.6 s). Extended check:
   `layout check: 137 texts, 9 cards, 0 label/marker hit(s), 0 problem(s)`.
2. **Old figures** — PASS: PNG SHA-256 vs the V2 baseline: A1, A2, A3, A4, A5, B1, B2, B3 **identical**; C1 changed
   (point 5 only); overview new. The old SVGs changed once (matplotlib's date removed and the clip-path ids now come from
   the fixed `svg.hashsalt`); after that, two consecutive runs produce **identical** SVGs for all ten figures.
3. **Fonts** — PASS: overview SVG has **0 `<text>` elements** (text as paths) and no `dc:date`; the PDF contains
   `/FontFile2` (embedded TrueType) and no `/FontFile3`.
4. **Point-by-point**:
   1. (f) styles: red = PAMAP2 7†, Marpino 5†; italic = simulated* (log line `(f) styles: ...`); asserts in code.
   2. Tick labels: `check_layout()` now calls `ax.get_tightbbox()` for every card and inset axes and compares it with the
      card; that found and fixed the (f) x-label and the (g) y-label overflow. (g) labels are now "Luo up · recall",
      "Luo up · prec.", …, "PAMAP2† down · prec.".
   3. (g) value labels are placed on the side away from the grey dot (left, red, when V4 < today); the check asserts no
      label bbox contains a marker (0 hits).
   4. (g) note, generated from the numbers: "Precision rises on Luo (up 41→86, down 29→69). Recall falls for Luo stairs
      up (50→43) and on PAMAP2 (7): up 39→24, down 53→38; its stairs-up precision stays 26→25."
   5. "CV by person: 8 real datasets + simulation" in the measured lane and in C1 (C1's PNG changed for this).
   6. (a) 20 x 20 waffle on the left (dots do not overlap; the last row is complete), one-column legend on the right,
      "312 people + 82 sim." above, dots ordered by dataset.
   7. (b) "r" next to the dashed lever arm (white background), "x anterior", "z up".
   8. (h) no legend; labels "stairs F0.5" and "STS (sim.)" at the right ends; y axis "%"; the 4 s values are offset from
      the curves (82 above, 78 below).
   9. (e) "e Key numbers" spacing fixed; today values right-aligned so "7.9 →" sits like "17.5 →".
   10. (i) no card title; "0.9 false events per hour".
   11. (d) gaps between the boxes, arrowheads stop short of the boxes.
   12. Larger gap between the subtitle and "1 · HOW IT WORKS".
5. **People count diagnostic** — done, no data changed. Unique people per dataset from the stage 2 indexes and from the
   W2/W4 window files:

   | dataset | stage 2 index persons | index rows | W2 groups | W4 groups |
   |---|---|---|---|---|
   | WearGait-PD | 109 | 1,304 | 109 | 109 |
   | CeTI | 32 | 3,126 | 32 | 32 |
   | KneE-PAD | 28 | 2,057 | 28 | 28 |
   | MHEALTH | 10 | 10 | 10 | 10 |
   | PAMAP2 | 8 | 8 | 7 | 7 |
   | Marpino | 78 | 156 | 5 | 5 |
   | Luo | 30 | 3,420 | 30 | 30 |
   | Lencioni | 50 | 3,230 | 50 | 50 |
   | Caicedo older adults | – | – | 44 | 41 |
   | Camargo simulated | – | – | 22 | 22 |
   | v1.6 synthetic | – | – | 60 | 60 |

   The V3 figure "265 people" = **109 WearGait-PD + 32 CeTI + 28 KneE-PAD + 10 MHEALTH + 8 PAMAP2 + 78 Marpino**, so
   WearGait-PD is 109 in the index too: 265 − (32 + 28 + 10 + 8 + 78) = 109, so the review's estimate of about
   183 WearGait-PD people is not what the files contain. The differences to the
   window file are: **Marpino** — the index "person" is the recording file (78 files); the dataset does not say who is
   who, so the CV uses five recording groups (Disability, Elderly, LongDistance, Marzia, Young) and the figure counts 5;
   **PAMAP2** — person 108 has no 4 s window; **Caicedo** — 44 people in W2, 41 in W4 (three have no 4 s window), and it
   is the external marker set (no CV row). The figure's definition, in `docs/FIGURES.md`: *a dot is one cross-validation
   group with at least one 4 s training window*.

## 5. Problems and open questions

1. The (a) "people" count therefore means CV groups: five of the 312 are the Marpino recording groups, not five
   identified people; the caption says so. If the owner prefers "recording groups" for Marpino, the label can say
   "312 groups".
2. `svg.fonttype = 'path'` makes the overview SVG independent of fonts but not selectable/searchable; the PDF keeps
   text with embedded TrueType (`/FontFile2`) for the thesis.
3. The layout check is geometric (AABB of text and axes boxes); it cannot judge contrast or crowding that stays inside
   the boxes, so a human look at the PNG is still needed.
4. Nothing else changed; `git status` before the report shows only the files listed above.
