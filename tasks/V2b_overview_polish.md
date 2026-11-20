# Task V2b: polish the overview figure (layout only)

Branch `agent/V2b`, new from `main` in `kneil_v4_agent` (V2 is merged). Report `tasks/V2b_report.md`, committed last.
Only `pipeline/make_figures.py` (overview code and `check_layout()`), the three `docs/figures/OVERVIEW_kneil_v4.*`
files, the log and, if a caption changes, `docs/FIGURES.md`. **No number, text content or data changes**; all other
figures stay byte-identical (PNG and SVG; the SVGs are reproducible now).

## Fix
1. **(b) Virtual implant is crowded**: "x anterior" almost touches the formula/validation text column; "spacer" touches
   the spacer bar; "z up" sits against the femur. Give the schematic more room (e.g. narrow the text column or put the
   formula and the validation lines under the drawing) so every label has clear space around it.
2. **Panel letters**: the gap between the letter and the title differs between cards ("e" almost touches "Key
   numbers"; "f" and "g" have a wider gap than a-d and h). Use one helper so all nine cards have the same letter x
   offset from the card edge and the same letter-to-title gap.
3. **Band 3 card**: there is empty space at the top of the card above the three lanes (left over from the removed
   title). Start the lanes near the card top, or make the card shorter and give the space to band 2.

## Make the check catch this next time
4. `check_layout()`: besides "no overlap" and "inside the card", require a **minimum gap**: every pair of texts at least
   6 px apart and every text at least 6 px inside its card edge (pixels of the 300 dpi PNG). Labels that belong
   together on purpose (for example a number and its "→") may be listed as exceptions in the code, with a comment.
   Report the smallest gap found before and after the polish.

## Checks
`--only overview` and the full run clean; the extended check passes (0 problems); other figures byte-identical (SHA of
PNG and SVG); the overview PNG at 300 dpi, SVG (text as paths), PDF (`/FontFile2`). Show before/after crops of (b),
the panel titles and band 3 in the report (paths to PNG crops saved under `cache\`, not committed).
