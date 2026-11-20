# V2 fix (manager review, 20 Nov 2026)

Good structure and the numbers match A1-A4. Same branch `agent/V2` (`base: existing`). Fix the points below, re-run,
write `tasks/V2_fix_report.md` (five sections), commit it last. Old figures must stay pixel-identical (C1 as in V2).

## Errors
1. **(f) row styles are on the wrong rows** (sorting bug): "Lencioni 50" and "simulated*" are red, "PAMAP2 7†" is
   italic. Must be: datasets with < 10 people (PAMAP2, Marpino) red with the dagger, the simulated row italic, all
   others normal. Set the style from the row's own data after sorting, and add an assert that every red label has a
   dagger and the italic label is the simulated row.
2. **Tick labels spill out of their cards**: in (f) "WearGait-PD 109" and in (g) "PAMAP2 (7) down · precision" start
   left of the card edge (g's labels almost touch card f). `check_layout()` missed this: it must also check tick
   labels, axis labels, legend texts and annotation texts (`ax.get_tightbbox()` per axes inside its card is a simple
   way), and markers vs value labels (below). Shorten the (g) labels if needed, e.g. "Luo ↑ recall", "PAMAP2† ↓ prec."
   with a one-line key "↑ stairs up, ↓ stairs down".
3. **(g) value labels sit on the grey dots** (Luo up recall "43" on the grey 50; PAMAP2 up precision "25" on the grey
   26). Put each V4 label on the side away from the grey dot (left of the blue dot when V4 < today). Check in code that
   no value label's bbox intersects any marker.
4. **(g) note is not accurate**: on PAMAP2 stairs-down recall also falls (53 -> 38) and stairs-up precision does not
   improve (26 -> 25). Write instead: "Precision rises on Luo (up 41 -> 86, down 29 -> 69); recall falls for Luo stairs
   up (50 -> 43) and on PAMAP2 (7 people: up 39 -> 24, down 53 -> 38), where stairs-up precision does not improve."
   (numbers from the log, not typed: format them from the same values).
5. **Measured lane / C1 say "CV by person, 9 datasets"**, but the CV results cover 8 real datasets + simulation
   (Caicedo has no CV row, as you noted). Write "CV by person: 8 real datasets + simulation" in both. Panel (a) stays
   "312 people in 9 public datasets" (training windows).

## Look ("fancy" = clean and confident)
6. **(a) waffle**: now a small striped block (dots overlap, the bottom row is cut). Make it the main element of the
   card: a square grid of about 20 x 20 dots, no overlap (marker size from the cell size), filling the left ~55 % of
   the card, legend on the right in one column, total "312 + 82 simulated" above. Order the dots by dataset.
7. **(b)**: label the lever arm "r" next to the dashed line (it is not visible now) and write "x anterior", "z up".
8. **(h)**: drop the legend (it crosses the 4 s line); label each line at its right end ("stairs F0.5", "sit-to-stand
   recall (sim.)"); y axis "%"; the 4 s values must not sit on a line.
9. **(e)**: "e" touches the title ("eKey numbers"): same letter/title spacing as the other cards; "7.9 →" like
   "17.5 →".
10. **(i)**: remove the card title "i Where it stands" (the band label says it); "0.9 false events per hour".
11. **(d)**: more space between the boxes; arrowheads must not touch box edges or text.
12. More space between the subtitle and the band label "1 · HOW IT WORKS".

## Files and diagnostics
13. Fonts: overview SVG with text as paths (`svg.fonttype = 'path'`, so it looks the same in PowerPoint/Inkscape);
    PDF with embedded TrueType (`pdf.fonttype = 42`), check that the PDF contains `/FontFile2`. Make SVGs reproducible
    (`svg.hashsalt` fixed, `metadata={'Date': None}`) so re-runs do not change old SVG files.
14. **People count diagnostic** (no data change): `CLAUDE.md` and the firmware docs say V3 used "real implant-site
    data of 265 people" from WearGait-PD, CeTI, PAMAP2, MHEALTH, KneE-PAD and Marpino, which implies about 183
    WearGait-PD people; the W4 window file has 109. Count unique people per dataset in the stage 2 index
    (`KNEIL_results\virtual_implant\stage2\...index*.csv`, do not count `stage2_index_all.csv` twice) and in the W2 and
    W4 window files, explain the difference (ids, filters, plausibility rule, min_share, ...), and write the definition
    used in the figure ("people with at least one 4 s training window") in FIGURES.md.

## Checks
`--only overview` and the full run clean; extended `check_layout()` reports 0 outside / 0 overlaps / 0 label-marker
hits; old PNGs SHA-identical (C1 changed only for point 5); the people table in the report.
