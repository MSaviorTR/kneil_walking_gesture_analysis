# Task V2c: overview figure, band 3 overlap (layout only)

Same branch `agent/V2b` (`base: existing`; V2b is not merged yet). Report `tasks/V2c_report.md`, committed last.
Same limits as V2b: layout only, no number or text change, all other figures byte-identical.

## Review of V2b (manager)
Panel letters, (b) and the minimum-gap rule are good. One defect: in band 3 the three lane boxes now **cut through
the top of the watch-log line** ("Owner's watch log, 17 Nov 2026: ..."): the lanes' bottom edges cross the text, and
the line also nearly touches the card's bottom edge. Your report said the check does not measure the lane rectangles;
that is exactly where it failed.

## Fix
1. Give band 3 enough height: the lanes end at least 20 mil above the watch-log line, and the line at least 20 mil
   above the card edge. Take the height from the empty space between band 3 and the footer (about 0.25 in now), not
   from bands 1-2.
2. Extend `check_layout()` to drawn boxes: every `FancyBboxPatch`/`Rectangle` used as a lane or box (band 3 lanes,
   the (d) boxes) must keep the 20 mil gap to every text that is not inside it, and the texts inside a box must be
   20 mil inside its edges. Report the smallest box-to-text gap.
3. Optional, only if it fits the 20 mil rule: put "x anterior" next to the tip of the x arrow in (b) instead of under
   "implant".

## Checks
`--only overview` and the full run clean; the extended check 0 problems; other figures byte-identical; a crop of band 3
before/after under `cache\` (not committed).
