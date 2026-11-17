# W1 fix (manager review, 17 Nov 2026)

Good work; host tests rerun by the manager: 75 + 35 + 62 PASS; the protocol copy equals the KNEIL firmware (only line
endings differ). Two points to fix, then the build parts if ESP-IDF is installed. Same branches (`base: existing`):
watch code on `agent/W1` in `guder_watch_agent`, report on `agent/W1` in `kneil_v4_agent`. Never push, never flash.

## 1. Mode change at run time can crash the UI (bug)
`ui_init()` builds page 1 as the face OR the KNEIL page from the mode at boot, but `refresh_cb()` / `tile_changed()`
call `ui_kneil_active()`, which reads the **current** setting. Settings -> Mode cycles Phone -> Sensor -> Both -> KNEIL
at run time, so after one tap page 1 still holds the face widgets while `ui_kneil_refresh()` is called (and the
reverse when leaving KNEIL): NULL / wrong LVGL objects.
Fix: remember which page was built (static flag set in `ui_init`). When the mode enters or leaves KNEIL, rebuild page 1
on the LVGL thread (clean the tile, create the other page, refresh) and update the flag; refresh only what was built.
Show the cycle KNEIL -> Phone -> ... -> KNEIL in the simulator (or, if it cannot run, a host-level test of the flag
logic) and explain in the report how it is safe.

## 2. Keep `apply_roles()` as it was
The added `if(ble_gap_adv_active() && !peripheral_on()) ble_gap_adv_stop();` before the `synced` check is not needed
(the original code already stops advertising when the peripheral is off, after the sync check) and calls NimBLE before
sync. Remove it; keep only the `kneil_central_set_active(kneil_on())` line. With the KNEIL mode not selected,
`ble_service.c` must behave exactly as upstream.

## 3. Build parts of W1 (only if ESP-IDF v5.5.5 is now installed; check as in W1)
W1 checks 3 and 4: `idf.py build` (fix compile errors in the new files only), `idf.py size` before (upstream/main in a
separate build folder) and after, warnings in new files, simulator screenshots incl. the scanning state and the mode
cycle. If ESP-IDF is still missing: say so and stop after points 1 and 2.

## Report
`tasks/W1_fix_report.md` (five sections), committed last in `kneil_v4_agent`. Host tests (counts) again.
