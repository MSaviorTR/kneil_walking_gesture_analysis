# Task G1 (worker gemini): independent review of the watch's KNEIL Bluetooth code (read only)

Branch `gemini/G1`, new from `main` in `kneil_v4_gemini`. Report `tasks/G1_report.md`, committed last. **Change no
code anywhere.** You only read.

## What to review
The KNEIL mode of the Güder smartwatch (ESP32-S3, ESP-IDF 6.1, NimBLE), written by the other worker, in the owner's
watch repo `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\guder_watch` (branch `main`, commit `6096726`; read the files
there, do not switch branches or commit in that folder):
- `main/kneil_central.c/.h` (BLE central: scan, connect, MTU, service/characteristic/descriptor discovery,
  subscriptions, notifications, CONTROL writes, reconnect)
- `main/kneil_state.c/.h` (page model, UUID bytes, descriptor-range helpers)
- `main/ui/ui_kneil.c`, the KNEIL parts of `main/ui/ui.c` and `main/usb_console.c`, `main/ble_service.c`
- the protocol copy `components/kneil_proto/` (must equal `..\kneil_firmware\protocol\kneil_proto.c/.h`)

Ground truth to check against:
- NimBLE headers and sources of this ESP-IDF: `C:\esp\v6.1\esp-idf\components\bt\host\nimble\nimble\nimble\host\`
  (`include\host\ble_gatt.h`, `ble_gap.h`, `ble_hs.h`, `src\ble_gattc.c`, `src\ble_gap.c`)
- the KNEIL protocol: `..\kneil_firmware\protocol\README.md` and the implant side `..\kneil_firmware\src\kneil_live.c`
  (what the implant really offers and sends)

Context: on real hardware the first three flashes failed in this code (a wrong UUID byte, the wrong CCCD chosen,
the wrong start handle for descriptor discovery); all three are fixed. The host tests cannot see wrong API use, so this
review is the only check before the next flash.

## Look for (at least)
1. Every NimBLE call: argument meaning, handles, lengths, return codes, callback signatures and their return values,
   what happens on `BLE_HS_EDONE` and on errors; GATT procedures started while another is still running.
2. Connection life cycle: disconnect during discovery or subscription, reconnect, stale handles or state, timers,
   scan restart, the mode being switched off mid-connection, two connections at once.
3. Thread safety: data shared between the NimBLE host task and the LVGL/UI task or the console (locks, copies,
   torn reads of structs, strings).
4. Notification handling: mbuf length checks, buffer sizes, v1 vs v2 packets, packets from the wrong handle.
5. Anything the implant (`kneil_live.c`) does that the watch does not expect (e.g. connection parameter updates, MTU,
   INFO lines when subscribing, SUMMARY timing).
6. UI: anything that can crash or freeze the watch (NULL widgets, rebuild while data arrives).

## Report format
Section 4 of the report: a table of findings, most severe first: `id | severity (crash / wrong data / degraded /
cosmetic) | file:line | what happens, in which situation | evidence (quote the header or the code line) | suggested fix
in words`. Then a list of things you checked and found correct (one line each). Say clearly what you could not check.
Do not propose style changes.
