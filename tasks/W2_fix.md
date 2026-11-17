# W2 fix (manager review, 17 Nov 2026)

Very good: upstream builds unchanged with v6.1, agent/W1 builds with no project warnings (+15 kB image, +960 B DIRAM),
old pages pixel-identical. Two points, same branches (`base: existing`). Never push, never flash.

## 1. Keep the default mode exactly as upstream
Your `refresh_cb()` fallback "NULL active tile = page 1" also changes the **face** in the default mode (it now refreshes
before the first swipe). The owner's rule is that the watch's existing functionality stays as it is, even where upstream
may have a bug. Scope the fallback to KNEIL mode only (`tile == NULL && built_kneil`). With KNEIL not selected,
`refresh_cb()` must behave as upstream. Write the possible upstream bug (face frozen until the first swipe, if it also
happens on hardware) as a note for the owner in the report; do not fix it.

## 2. KNEIL page: no clipped text
In `08_kneil_connected` the link line is cut at the right edge ("packets 40"). Let it wrap (or shorten it) so nothing is
clipped at 410 px; check the other KNEIL captures for the same.

## Checks
`idf.py build` (EIM profile as in W2), host tests (counts), simulator: KNEIL captures again, and the old scenarios still
pixel-identical to upstream. Report `tasks/W2_fix_report.md`, committed last in `kneil_v4_agent`.
