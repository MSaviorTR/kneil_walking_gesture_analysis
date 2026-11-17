# Task: KNEIL live viewer — a PC app (and its BLE bridge) that shows in real time what my implant prototype recognises

You are helping me (engineering PhD student; English is not my first language: short, plain sentences) write a desktop
app that connects to my sensor (a Nordic nRF54L15 board running an activity classifier) and shows live what it
recognises. Another AI tool writes the sensor firmware from the same protocol, so **follow the protocol below exactly**.
I use **Windows 11, VS Code, Python 3.12**.

**Hardware chain:** KNEIL board (nRF54L15, BLE peripheral) → BLE → **Seeed XIAO nRF52840** (BLE central, the bridge)
→ USB serial → PC app. You write **two things**: the bridge firmware for the XIAO and the PC app (protocol section C).
For the bench, the app can also read the nRF54L15 DK's own USB port directly (section B, same text lines).

## Technology
- **Bridge (XIAO nRF52840):** nRF Connect SDK / Zephyr, board target `xiao_ble`, USB CDC ACM serial port, built as a
  **UF2** file (`CONFIG_BUILD_OUTPUT_UF2=y`) so I can flash it by double-tapping reset and copying the file to the XIAO
  drive. If the SDK route causes problems, the Arduino IDE with the Seeed nRF52 board package and the Bluefruit library
  is acceptable: ask me first. Use the XIAO's RGB LED: blue blinking = scanning, green = connected, red = error or lost.
- **PC app:** Python with **PySide6** (window), **pyqtgraph** (fast plots), **pyserial** (USB), numpy. Optional third
  transport: direct BLE from the PC with **bleak**, for when no bridge is at hand.
The window must never freeze: run BLE (asyncio, e.g. with `qasync`) and serial reading off the GUI thread and pass
data through queues or Qt signals. Give me `requirements.txt` with pinned versions and a `README.md` with the steps.

## What the window shows
1. **Connection bar:** choose the transport: **XIAO bridge** (default; COM port), **DK USB** (COM port) or **direct BLE**
   (optional). With the bridge: *Scan* (lists `KNEIL-*` devices with signal strength from `B,FOUND`), *Connect* (selected
   or AUTO), *Disconnect*; show the bridge state, RSSI and MTU from `B,STATE`. Always show the packet rate and the lost
   packets from the sequence numbers, plus the bridge's `B,DROPS`. Remember the last COM port and device.
2. **Current activity:** big coloured label (class colours from the protocol) with the smoothed class, the raw class
   below it, the vote share if available, and an extra line **"upright and still"** when the class is sitting or standing.
3. **Live acceleration:** x, y, z of the last 10 s from the RAW stream, plus |a|; a checkbox to overlay the same signal
   after a 6 Hz low-pass (2nd-order Butterworth, causal), like the chip uses.
4. **Timeline:** a coloured ribbon of the classes over the last 5 minutes (one block per second).
5. **Session totals:** time per class and per merged group (walking, stairs, upright and still, lying, transitions),
   and the number of transitions (sit-to-stand + stand-to-sit).
6. **Log panel** with the `I` messages, connection events and errors.

## Testing tools (important: this is how I will measure the real accuracy)
- **Ground-truth keys:** while testing I press keys for what I am really doing: `1` walking, `2` stairs up, `3` stairs
  down, `4` sitting, `5` standing, `6` lying, `7` sit-to-stand, `8` stand-to-sit, `9` bed transfer, `0` other. The current
  truth is shown next to the device's answer.
- **Live confusion table** (truth rows x device columns, counts and %) and the accuracy for walking, for "upright and
  still" and overall, updated every second; a button to reset.
- **Recording:** one click starts a CSV session file with every LIVE row (time, classes, vote, flags, means, the truth
  key at that moment) and a second CSV with all RAW samples. File names with date and time.
- **Demo mode** without hardware: generates fake LIVE and RAW data (walking, standing, sitting) following the protocol,
  so I can test the app first. Also **replay** of a recorded session.
- **Time alignment:** the device classifies the window that ends at `t_ms`, so compare it with the truth key of the
  window's centre: 2 s earlier for protocol v2 (4 s window), 1 s earlier for v1 (2 s window). The app must take
  the window length from the LIVE version, and the class table with it.

## Steps (show me each step working before the next)
1. Protocol parsers (text lines `L`/`R`/`I`/`B`, and the BLE binary packets for the bridge and direct BLE) with unit
   tests built from example packets.
2. Demo mode and the main window.
3. **Bridge firmware:** scan, connect (address or AUTO), subscribe to LIVE and RAW, binary → text lines, forward
   `S`/`P`/`T`, `B` state lines, LED states, automatic reconnect. Test it first with a phone app (nRF Connect for Mobile)
   acting as a fake KNEIL device if the board firmware is not ready: give me the exact steps and the bytes to enter.
4. PC app over the bridge (and over the DK's USB port: same parser).
5. Recording, replay, ground-truth keys and the confusion table.
6. Optional: direct BLE with bleak.

## Rules
For the bridge: the BLE callbacks only copy packets into a ring buffer; a separate thread formats and writes them to
USB, so a slow PC never blocks the BLE link (count overflows in `B,DROPS`).
Complete files, not fragments. Print a version line at start. Clear error messages (for example: COM port busy,
Bluetooth off, device not found). Keep the protocol code in one module so it can be changed in one place.

## Shared data protocol (identical in the firmware and the GUI; do not change one side alone)

Units: acceleration in **mg** (int16; ±8 g fits). Device frame: **x anterior, y = subject's left, z superior**
(standing still reads about (0, 0, +1000) mg). All multi-byte values **little-endian**. Time `t_ms` = milliseconds since boot (uint32).

**Classes, protocol v2** (since 17 Nov 2026: 8 classes, 4 s window; the app keeps the v1 table for old packets and
recordings):

| index | name (v2) | GUI colour |
|---|---|---|
| 0 | walking | green |
| 1 | stairs_up | orange |
| 2 | stairs_down | dark orange |
| 3 | still (sitting and standing together) | blue |
| 4 | lying | purple |
| 5 | sit_to_stand | yellow |
| 6 | stand_to_sit | gold |
| 7 | bed_transfer | brown |

The v2 LIVE packet also carries the **posture state** (bits 4-5 of the event byte: 0 unknown, 1 sitting, 2 standing).
The GUI shows `still` in one colour and the posture as text. The accuracy table has a 10th device column
**'still (posture ?)'**: a still window whose posture is unknown goes there, never into sitting. Sitting and standing
accuracy use the windows with a known posture only, and the app shows the share of still windows with an unknown
posture next to them. The old v1 classes (0 walking, 1 stairs_up, 2 stairs_down,
3 sitting, 4 standing, 5 lying, 6 sit_to_stand, 7 stand_to_sit, 8 bed_transfer) stay for v1 packets.

### A. Bluetooth LE (binary)
Advertised name `KNEIL-xxxx` (last 4 hex digits of the device address). Custom service and characteristics:

| UUID | name | properties |
|---|---|---|
| `a8f50001-3e2c-4c6e-9b1a-6b4e45494c00` | KNEIL live service | |
| `a8f50002-3e2c-4c6e-9b1a-6b4e45494c00` | LIVE | notify |
| `a8f50003-3e2c-4c6e-9b1a-6b4e45494c00` | RAW | notify |
| `a8f50004-3e2c-4c6e-9b1a-6b4e45494c00` | CONTROL | write |

**LIVE packet, v2** (22 bytes, once per second when a 4 s window is classified; the app accepts the 20-byte v1
packet too):

| offset | type | field |
|---|---|---|
| 0 | uint8 | type = 0x01 |
| 1 | uint8 | protocol version = 2 |
| 2 | uint16 | sequence number (wraps) |
| 4 | uint32 | t_ms at the end of the window |
| 8 | uint8 | class after the stairs rule (0-7 or 255) |
| 9 | uint8 | class after the majority-of-3 smoothing (0-7 or 255) |
| 10 | uint8 | vote share of the raw class in % (forest only; 255 = not available) |
| 11 | uint8 | flags: bit0 self-test passed, bit1 input low-pass on, bit2 small model (tree) in use |
| 12 | int16 x3 | mean x, y, z of the window (mg) |
| 18 | uint16 | battery in mV (0 = not measured) |
| 20 | uint8 | raw class (argmax before the stairs rule; 0-7 or 255) |
| 21 | uint8 | event flags: bit0 sit-to-stand counted, bit1 stand-to-sit, bit2 bed transfer; bits 4-5 posture |

**RAW packet** (every 0.5 s while raw streaming is on): `uint8 type = 0x02`, `uint8 n` (samples in this packet),
`uint16 sequence`, `uint32 t_ms of the first sample`, then `n` samples of `int16 x, y, z` (mg) at 50 Hz.
Normally n = 25 (158 bytes; request ATT MTU 247 and data length extension). If the MTU is smaller, the firmware
sends more, shorter packets with n = floor((MTU - 3 - 8) / 6).

**SUMMARY packet (v2)**: `uint8 type = 0x04` + the 40-byte daily summary (format 2: minutes per class, the still
minutes split by posture, event counts, mean sit-to-stand time, steps, cadences, seated tilt). The app shows it in a
panel and sends Q to ask for it; Z resets the daily metrics in the device.

**CONTROL writes** (1 byte): `0x10` start raw streaming, `0x11` stop raw streaming, `0x12` run the self-test now
(the next LIVE packet reports the result in its flags), `0x13` send the daily summary now, `0x14` reset the daily
metrics.

### B. USB serial (text, for the bench; the DK's virtual COM port, 115200 baud, 8N1)
One line per message, comma-separated, ending with `\n`:
- `L,<seq>,<t_ms>,<class>,<class_smoothed>,<vote_pct>,<flags>,<mean_x_mg>,<mean_y_mg>,<mean_z_mg>,<battery_mV>`
- `R,<seq>,<t_ms_first>,<n>,x1,y1,z1,x2,y2,z2,...` (same content as the RAW packet)
- `I,<free text>` for information lines (boot, self-test result, model name and size). The GUI shows them in its log.
Commands from the PC are the same single letters on their own line: `S` start raw, `P` stop raw, `T` self-test.

### C. BLE bridge to the PC (Seeed XIAO nRF52840 on USB)
The PC does not use its own Bluetooth: a **Seeed XIAO nRF52840** is the BLE central. It connects to `KNEIL-xxxx`,
subscribes to LIVE and RAW, and writes the received packets to its USB serial port **as the text lines of section B**
(`L`, `R`, `I`), byte for byte the same format as the DK's USB port, so the PC uses one parser for both cables.
Commands `S`, `P`, `T` from the PC are written to CONTROL as `0x10`, `0x11`, `0x12`. The bridge adds only its own
`B` lines:
- `B,SCAN` (PC -> bridge): scan 5 s; the bridge answers `B,FOUND,<name>,<address>,<rssi_dBm>` per device and `B,SCAN_DONE`.
- `B,CONNECT,<address>` or `B,CONNECT,AUTO` (the strongest `KNEIL-*`); `B,DISCONNECT`.
- `B,STATE,<idle|scanning|connecting|connected|lost>,<name>,<address>,<rssi_dBm>,<mtu>` (bridge -> PC) on every change
  and every 2 s while connected; `B,DROPS,<count>` if its USB buffer overflowed; `B,VERSION,<text>` at start-up.
The bridge requests ATT MTU 247 and data length extension, reconnects by itself after a link loss (state `lost`, then
`connecting`), and never changes the content of `L`/`R`/`I` lines. The KNEIL firmware needs nothing special for the
bridge: it is an ordinary BLE central.
