# Task W5: descriptor discovery called with the wrong start handle (found on hardware, 17 Nov 2026)

After W4 the owner's log shows, on every connect:
`5 characteristics: LIVE 21, INFO 29, SUMMARY 32, CONTROL 27` -> `discover all descriptors; chr_val_handle=22
end_handle=22` -> `E NimBLE: ble_att_clt_tx_find_info rc=3` -> `disconnecting: descriptor discovery failed`.
Cause: `main/kneil_central.c:290` calls `ble_gattc_disc_all_dscs(conn, sub_first, sub_last, ...)`. NimBLE's second
argument is the **characteristic value handle**; it searches from value + 1 to end itself. Passing `sub_first`
(= value + 1 = 22) makes it search 23..22 (empty) and it returns BLE_HS_EINVAL (3).

Branch `agent/W5` from the watch repo's `main` (`787af53`) in `guder_watch_agent`; report `tasks/W5_report.md` on
`agent/W5` from `main` in `kneil_v4_agent`. Never push, never flash. Leave `dependencies.lock` uncommitted.

## Do
1. Pass `sub_value` (the value handle) and `sub_last` to `ble_gattc_disc_all_dscs()`. Keep the range filter in
   `kneil_cccd_for()`.
2. Read the NimBLE header of this ESP-IDF (`C:\esp\v6.1\esp-idf\components\bt\host\nimble\nimble\nimble\host\include\host\ble_gatt.h`
   and `ble_gattc.c`) and check **every** NimBLE GATT/GAP call in `kneil_central.c` for the meaning of each argument
   (handles, lengths, callbacks, return codes). Quote the header line for each in the report. This is the third
   hardware-only bug; the host tests cannot see API misuse, so this review is the check.
3. Put the arguments of the discovery call into a small pure function (e.g. `kneil_dsc_disc_args(value, next_def,
   svc_end, &start_arg, &end_arg)` returning start_arg = value handle) and host-test it with the log layout
   (LIVE 21 -> (21, 22), INFO 29 -> (29, 31), SUMMARY 32 -> (32, 33)). It must fail on the W4 code.

## Checks
Host tests (counts), `idf.py build` (EIM profile), no new warnings. Expected log on the watch:
`subscribed LIVE: value 21 cccd 22`, `... INFO: value 29 cccd 30`, `... SUMMARY: value 32 cccd 33`, then
`first LIVE packet, v2, class ...`.
