# W6 report: the G1 watch findings F1-F9

## 1. Status

Done. All nine findings of `tasks/G1_report.md` are fixed on `agent/W6` in the watch worktree; the host tests
pass, the ESP-IDF 6.1 build has no new warnings, the binary grows by 1,520 bytes, and the simulator still
renders every scenario. Nothing was flashed or pushed.

## 2. Files

Watch worktree (`guder_watch_agent`, branch `agent/W6` from `main` 6096726; 4 commits, not pushed):

- `main/kneil_ctrl_queue.c`, `.h` — **new**: the CONTROL ring buffer as pure C (push/take/done/requeue/reset),
  `KNEIL_CTRL_QUEUE_SIZE` = 4 as before.
- `main/ble_roles.c`, `.h` — **new**: `ble_roles_plan(central_on, kneil_on, steps)`, the switch order used by
  `apply_roles()` (inactive roles off first, then active roles on).
- `main/kneil_central.c` — F2, F4, F5, F7, F8.
- `main/ble_service.c` — F3 in `apply_roles()` (`ble_roles_plan()` instead of the two fixed calls); the local
  `MODE_TXT` is `[BLE_MODE_COUNT]` with a `_Static_assert` (F1). No other change in this upstream file.
- `main/usb_console.c` — F1: `bmode[BLE_MODE_COUNT]` gains `"kneil"` + `_Static_assert`.
- `main/ui/ui_diag.c` — F1: `mode_txt[BLE_MODE_COUNT]` gains `"KNEIL device"` + `_Static_assert`.
- `main/ui/ui_settings.c` — F1: `_Static_assert` on the existing `BLE_MODE_TXT[BLE_MODE_COUNT]`.
- `main/ui/ui_kneil.c` — F6 (`buf[96]`), F9a (`last_refresh_us = 0` in `ui_kneil_create()`), F9b
  (`ui_kneil_destroy()` closes the reset dialog).
- `main/ui/ui.c` — F9b: `build_page1()` calls `ui_kneil_destroy()` when it leaves KNEIL mode.
- `main/ui/ui_internal.h` — declaration of `ui_kneil_destroy()`.
- `main/CMakeLists.txt` — the two new source files.
- `test/host/run.sh`, `test/host/test_kneil.c` — the new pure modules in the `kneil_tests` binary;
  `test_ctrl_queue()` (F2) and `test_role_plan()` (F3): 48 new checks.

Workspace (`kneil_v4_agent`, branch `agent/W6` from `main`): `tasks/W6_report.md` (this file).

Commits: `fe0ecb8` (new pure modules + tests), `ae1d81f` (F1, F3), `57f12e2` (F2, F4, F5, F7, F8), `545d31b`
(F6, F9). The report is committed last, separately.

## 3. Commands

```powershell
git switch -c agent/W6 main                       # in guder_watch_agent and in kneil_v4_agent
& "C:\Program Files\Git\bin\bash.exe" -lc "cd guder_watch_agent/test/host && SAN= PYTHON=python ./run.sh"
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
cd guder_watch_agent ; idf.py build
& "C:\Program Files\Git\bin\bash.exe" -lc "cd guder_watch_agent/test/sim && ./run.sh"
git add <the files above> ; git commit ...        # four commits; dependencies.lock never staged
```

## 4. Acceptance checks

### F1 — `status` reads `bmode[3]` of a 3-entry table — PASS

`BLE_MODE_KNEIL` is 3 and `BLE_MODE_COUNT` is 4; the table is now
`static const char *const bmode[BLE_MODE_COUNT] = { "phone", "sensor", "phone+sensor", "kneil" };` with a
`_Static_assert` on its element count. The whole watch code was searched for other tables indexed by
`ble_mode_t`: four exist and all have `BLE_MODE_COUNT` entries and a `_Static_assert` now:

| table | file | mode names |
|---|---|---|
| `bmode` | `main/usb_console.c` (console `status`) | phone, sensor, phone+sensor, **kneil** |
| `mode_txt` | `main/ui/ui_diag.c` (Diagnostics) | phone only, sensor only, phone + sensor, **KNEIL device** |
| `BLE_MODE_TXT` | `main/ui/ui_settings.c` (Settings button) | Phone only, Sensor only, Phone + sensor, KNEIL device |
| `MODE_TXT` | `main/ble_service.c` (startup log) | phone, sensor, phone + sensor, kneil device |

No table indexed by `ble_mode_t` remains smaller than the enum.

### F2 — CONTROL queue races and lost bytes — PASS

- `ctrl_queue` (`head`, `count`, `busy`) and the `conn`/`h_ctrl` snapshots are only touched under `lock`, in
  `kneil_central_send_ctrl()`, `ctrl_kick()` and `on_ctrl_written()`. `h_ctrl` is written under the same lock
  in `on_chrs()`, and `conn` in the GAP callbacks.
- `kneil_ctrl_queue_take()` sets `busy` **before** returning the byte, so it is already true when
  `ble_gattc_write_flat()` is called; the old "set busy after the call" window is gone.
- If `ble_gattc_write_flat()` returns non-zero, `busy` is cleared and the byte is put back at the front
  (`kneil_ctrl_queue_requeue()`), so it is not lost.
- The queue, its count and `busy` are cleared on `BLE_GAP_EVENT_DISCONNECT`, in `kneil_central_on_reset()`,
  on a new connection and when KNEIL mode is switched off. A completion for a write started before one of
  those events is recognised by its generation number and does not clear `busy` of the next connection.
- `kneil_central_send_ctrl()` returns `false` when the queue is full (and, as before, when there is no
  CONTROL handle or no connection). The queue holds 4 bytes, unchanged.
- Host test `test_ctrl_queue()`: FIFO order, full → `false` and no overwrite, one write in flight, failed
  start → requeue, reset while busy, and ring wrap — 32 checks, all pass.

### F3 — role switch order — PASS

`apply_roles()` now calls `ble_roles_plan(central_on(), kneil_on(), steps)`:

| new state | steps, in order |
|---|---|
| Sensor only / Phone + sensor (leaving KNEIL) | **KNEIL off**, sensor central on |
| KNEIL device | sensor central off, **KNEIL on** |
| Phone + sensor | sensor central on, KNEIL on |
| Bluetooth off | sensor central off, KNEIL off |

`test_role_plan()` checks all four states and that no `on` step precedes an `off` step (16 checks). The KNEIL →
Sensor-only case that stayed idle (`ble_gap_disc_active()` was still KNEIL's) now switches KNEIL off first.

**Shape of the upstream change:** `apply_roles()` still makes exactly the same two calls per switch (one per
central) as upstream; only their order changed. The order itself is the new pure `ble_roles_plan()` so the host
test can cover it. Nothing else in `ble_service.c` was touched except the F1 `MODE_TXT` table.

### F4 — scan-window lifecycle and lock — PASS

- `scan_window_cb()` returns immediately unless `active && synced && conn == BLE_HS_CONN_HANDLE_NONE`.
- `cand[]`, `n_cand`, `dev_name` and `dev_rssi` are written/read under `lock` (`remember_locked()` from the
  NimBLE task, the selection in the timer callback, `set_link_dev()` elsewhere). The chosen candidate is
  copied to a local `struct candidate` before `ble_gap_connect()`, not referenced through the shared array.
- `start_scan()` reads `conn` under the lock too and clears `n_cand` under it.
- `kneil_central_set_active(false)` calls `ble_gap_conn_cancel()` when `ble_gap_conn_active()` is true, after
  cancelling discovery and before dropping an established connection.
- There is a second `active && synced` check after the scan cancel and before `ble_gap_connect()`. If a mode
  switch still loses that race, the connect event sees `active == false`, sets the model to `off` and drops
  the connection; it never stays `connected` or `connecting`.

NimBLE calls added (header of this ESP-IDF, `…\components\bt\host\nimble\nimble\nimble\host\include\host\`):

| call | header line (quoted) | verdict |
|---|---|---|
| `ble_gap_conn_active()` | `int ble_gap_conn_active(void);` (`ble_gap.h:3452`) — "Indicates whether a connect procedure is currently in progress. @return 0: No connect procedure in progress; 1: Connect procedure in progress." | **PASS** (gate for the cancel) |
| `ble_gap_conn_cancel()` | `int ble_gap_conn_cancel(void);` (`ble_gap.h:3444`) — "Aborts a connect procedure in progress. @return 0 on success; BLE_HS_EALREADY if there is no active connect procedure." | **PASS** (only called when active; a non-zero return is logged) |

### F5 — LIVE without a CCCD — PASS

Both paths drop the connection with the reason `no LIVE CCCD` and log it: no CCCD found by the descriptor
discovery (`on_sub_dsc()`) and an empty descriptor range (`subscribe_next()`). A missing CCCD for INFO or
SUMMARY is still only a warning and the subscription moves on, as before.

### F6 — link/meta line buffer — PASS

`buf` is 96 bytes. Longest text at the extreme values
(`RSSI -128 dBm   MTU 65535   v2 (8 classes)   packets 4294967295   gaps 4294967295`) is 81 characters + NUL.
The other `snprintf()` uses in `ui_kneil.c` were measured against their longest text: link line 33, raw/vote
line 31, posture line 45 characters; the summary buffer is 192 bytes and its two lines total at most 179
characters + NUL (all class/event counters at 65535, cadence `6553.5`).

### F7 — no `connected` after the mode went off; MTU failure logged — PASS

- `on_mtu()` sets `connected` only when `active` and `conn == c`.
- `subscribe_next()` returns at entry when `!active || conn == BLE_HS_CONN_HANDLE_NONE`, and re-checks both
  before its final `subscribed → connected`.
- `BLE_GAP_EVENT_CONNECT` checks `active` before it sets `connected`; with the mode off it sets `off` and drops.
- `ble_gattc_exchange_mtu()`'s return value is logged (`MTU exchange failed to start: %d`), and a failed MTU
  procedure is logged in `on_mtu()` (`MTU exchange failed: %d (subscriptions continue at the default MTU)`).

### F8 — empty candidate name filled later — PASS

When a candidate is updated, `cand[i].name` is filled from the new packet if it is still empty and the packet
carries a name. The shared copy/normalisation is `remember_name()`, also used for new candidates.

### F9 — page lifecycle — PASS

- (a) `ui_kneil_create()` sets `last_refresh_us = 0`, so summary and INFO are filled on the first refresh after
  a rebuild instead of waiting up to 2 s.
- (b) `ui_kneil_destroy()` calls `confirm_close()`; `build_page1()` calls it when page 1 leaves KNEIL, before
  `lv_obj_clean(tile)`. The dialog lives on `lv_layer_top()`, so this is the only thing that removes it from
  the watch face.

### Host tests — PASS

```text
75/75 checks passed
app_state: 35/35 checks passed
kneil tests: 155 checks, 0 failed       (107 before; +48: 32 queue, 16 role order)
KNEIL TEST: PASS
contract: 200 emulator frames, 10% deliberately corrupted
ok=177 checksum_err=23 format_err=0 ignored=0
```

(`ok`/`checksum_err` split varies per run by design; the corrupted fraction is 10 %.)

### `idf.py build` (ESP-IDF 6.1, EIM profile) — PASS

0 errors; 0 warnings from the project's files. The full build printed the same 11 pre-existing
`Atomic_*_u32 defined but not used` warnings from the FreeRTOS kernel's `atomic.h` as before W6; the
incremental rebuild of the changed files printed none. Size:

| | binary | free of 0x800000 |
|---|---|---|
| before (6096726, W5 build) | `0x155760` (1,398,624 B) | 83 % |
| after (agent/W6) | `0x155d50` (1,400,144 B) | 83 % |

+`0x5F0` = 1,520 bytes for the two new modules, the locks and the extra checks.

### Simulator — PASS

All six scenarios render: `live`, `alert`, `demo`, `uncal`, `nodata`, `kneil` (17 screenshots, including
`00_splash`, `07_kneil_scanning`, `08_kneil_connected`, `09_kneil_reset_dialog`, `10_mode_phone_face`,
`11_mode_kneil_again`).

## 5. Problems and open questions

1. **Hardware not tested** (nothing flashed, as instructed). The fixes are static and host/build-tested; the
   next watch run should show `no LIVE CCCD` only for a device that really lacks it, and the CONTROL buttons
   should keep working after a fast completion.
2. **`dependencies.lock` was rewritten by this build and is left uncommitted**, as the task says. The build
   changed `idf` `5.5.5 → 6.1.0`, lock format `2.0.0 → 3.0.0`, and added `espressif/usb 1.6.1`. No other
   generated file is tracked; `sdkconfig`, `build/` and `managed_components/` stay ignored.
3. **F3 shape:** the task said "keep it to the order of the two calls". `apply_roles()` still makes exactly two
   setter calls per switch, one per central, but the order comes from the new pure `ble_roles_plan()` (the task
   also asked for the role order as a host-testable pure function). If you prefer the loop to be written out as
   explicit `if`s in `ble_service.c`, it is a small follow-up; the behaviour and the host test would not change.
4. **Small remaining timer race:** `esp_timer_stop()` does not stop a callback that is already running, so a
   KNEIL→other switch can still interleave with the last instructions of `scan_window_cb()`. The second
   `active && synced` check narrows it, and a connect that slips through is cancelled or dropped in
   `BLE_GAP_EVENT_CONNECT` (model set to `off`), but the radio can be used for one short attempt. Fully closing
   it would need the mode lock held across `ble_gap_connect()`, which I did not do because it adds a lock-order
   dependency with NimBLE that the review did not ask for.
5. **`_Static_assert` limit:** it proves the table has `BLE_MODE_COUNT` elements, not that every element is
   non-NULL; C has no compile-time check for a missing initializer. All four tables are fully initialised
   today.
6. **Observation, not fixed (outside F1-F9):** `ui_diag.c`'s role lines use
   `phone_role = enabled && mode != BLE_MODE_SENSOR` and `sensor_role = enabled && mode != BLE_MODE_PHONE`, so
   in KNEIL mode Diagnostics still claims a phone and a sensor role although `peripheral_on()` and
   `central_on()` are both false. The F1 fix only makes the mode name (`KNEIL device`) correct. Say the word
   and I will change those two lines in a follow-up.
