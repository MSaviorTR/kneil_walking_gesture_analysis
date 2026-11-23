# Task W6: fix the watch findings of Gemini's review G1

Read `tasks/G1_report.md` (on `main`): an independent review of your KNEIL code in the watch. The manager checked F1,
F2, F3 and F6 in the code: they are real. Fix **F1-F9** as the report suggests, in the watch worktree
`C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\guder_watch_agent`, new branch `agent/W6` from the watch repo's `main`
(`6096726`; leave `dependencies.lock` uncommitted). Report `tasks/W6_report.md` on `agent/W6` from `main` in
`kneil_v4_agent`. Never push, never flash.

## Points
- **F1 (crash)**: the `status` console command in KNEIL mode reads `bmode[3]` of a 3-entry array. Add "kneil", declare
  the array `[BLE_MODE_COUNT]` and add a `_Static_assert` on its size. Search the whole watch code for every other
  table indexed by `ble_mode_t` and do the same.
- **F2**: CONTROL queue: lock the queue and `ctrl_busy`; set `ctrl_busy` before `ble_gattc_write_flat()` (clear it if
  the call fails); clear the queue on disconnect and host reset; `kneil_central_send_ctrl()` returns false when full.
- **F3**: `apply_roles()`: switch off the central(s) that become inactive before switching on the new one. This
  changes `ble_service.c` (upstream code): keep it to the order of the two calls and say so in the report.
- **F4**: `scan_window_cb()` checks `active && synced && conn == NONE`, uses the lock for `cand[]`, `n_cand`,
  `dev_name`, `dev_rssi`; `kneil_central_set_active(false)` cancels a pending connect (`ble_gap_conn_cancel()`).
- **F5**: no LIVE CCCD -> drop the connection ("no LIVE CCCD").
- **F6**: link-line buffer to 96 bytes (check the other `snprintf` buffers in `ui_kneil.c` against their longest text).
- **F7**: no `connected` after the mode was switched off; log a failed `ble_gattc_exchange_mtu()`.
- **F8**: fill in an empty candidate name from a later packet.
- **F9**: reset `last_refresh_us` in `ui_kneil_create()`; close the confirm dialog when page 1 leaves KNEIL.

For each NimBLE call you add (`ble_gap_conn_cancel`, ...), quote its header line in the report (as in W5).

## Checks
Host tests (counts; add tests where the logic is host-testable, e.g. the CONTROL queue and the role order as pure
functions), `idf.py build` (EIM profile) with no new warnings, size before/after, simulator scenarios still render.
