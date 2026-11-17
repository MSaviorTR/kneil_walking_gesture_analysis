# Task: KNEIL firmware — run the V3 activity model on the nRF54L15 and stream what it recognises

You are helping me (engineering PhD student; English is not my first language: short, plain sentences) put my
activity classifier on a Nordic **nRF54L15 DK** (nRF Connect SDK / Zephyr) and send its results live to a PC app.
I work on Windows 11 with VS Code and the nRF Connect extension. Another AI tool writes the PC app from the same
protocol, so **follow the protocol below exactly**.

## What exists
- `kneil_tinyml` (library v1.1, a Zephyr module: `zephyr/module.yml`, `CMakeLists.txt`, `Kconfig`). Read its `README.md`
  and `include/kneil_tinyml.h` first. API: `kneil_classifier_init()`; `kneil_classifier_push(&c, ax, ay, az)` once per
  sample (in g, device frame), which returns a class index every second (or -1); `kneil_metrics_update()` per class;
  `kneil_selftest()` checks the features and the model against 27 test vectors.
- **Model V3** in `KNEIL_results\tinyml_final_v3_lp6`: copy `kneil_model_forest.h`, `kneil_model_tree.h`,
  `kneil_model_info.h` into `kneil_tinyml\include\` and `kneil_test_vectors.h` into `kneil_tinyml\tests\`. On the PC,
  `python tests\run_host_test.py` must print `HOST TEST: PASS (both models)` before any board work.
  `kneil_model_info.h` must say `KNEIL_MODEL_FS_HZ 50` and `KNEIL_MODEL_LOWPASS_HZ 6` (the library applies the 6 Hz
  low-pass itself). Forest 18,900 nodes (expect about 160 KB of flash), single tree 1,117 nodes
  (`CONFIG_KNEIL_TINYML_MODEL_SMALL=y` if flash is tight). Never edit the generated files.
- Accelerometer: 50 Hz, ±8 g, 16-bit. Ask me for the part number and wiring if they are not in the project.

## Steps (after each step: build, show me the result, wait for my OK)
1. **Module and self-test.** Add the module (`ZEPHYR_EXTRA_MODULES`), `CONFIG_KNEIL_TINYML=y`, `CONFIG_KNEIL_TINYML_FS_HZ=50`,
   `CONFIG_KNEIL_TINYML_SELFTEST=y`. Run `kneil_selftest()` at boot and print the result (pass = 0 feature failures,
   0 class mismatches). Report flash and RAM use (rom_report / ram_report).
2. **Timing.** Measure the cycles of a `kneil_classifier_push()` call that returns a class (DWT cycle counter): mean
   and maximum over 60 windows.
3. **Accelerometer.** 50 Hz ODR, ±8 g, FIFO watermark about 1 s, read the FIFO in a thread (not in the interrupt).
   Map the sensor axes to the device frame and check with the board held still: device z up -> (0, 0, +1 g);
   x up -> (+1, 0, 0); y up -> (0, +1, 0). Show me the three readings. A wrong axis or sign makes walking look like stairs.
4. **USB text stream** (protocol section B): `I` lines at boot (firmware version, model name and node counts from
   `kneil_model_info.h`, self-test result), one `L` line per classified window, `R` lines when raw streaming is on,
   and the commands `S`, `P`, `T`. Keep a sequence counter per message type.
5. **Bluetooth LE** (protocol section A): advertise `KNEIL-xxxx`, the custom service with LIVE / RAW / CONTROL,
   request MTU 247 and data length extension, notify LIVE every second and RAW every 0.5 s while it is on.
   Notifications must never block the sampling or the classifier: use a message queue and drop RAW packets (never LIVE)
   if the link is too slow, and count the drops in an `I` line.
6. **Vote share (optional).** Only if the generated forest header exposes the individual trees: count the votes and
   fill byte 10; otherwise send 255. Do not modify the generated header.

## Rules
- No dynamic memory; no processing in interrupts; the 50 Hz sampling must never stall (BLE and USB run in their own
  threads, lower priority than sampling and classification).
- Small changes, show me diffs, explain in plain words, ask when unsure (pins, sensor, SDK version).
- At the end, give me a short test plan: self-test, timing, axes, then 2 minutes each of standing, sitting, walking and
  lying while the PC app records.

## Shared data protocol (identical in the firmware and the GUI; do not change one side alone)

Units: acceleration in **mg** (int16; ±8 g fits). Device frame: **x anterior, y = subject's left, z superior**
(standing still reads about (0, 0, +1000) mg). All multi-byte values **little-endian**. Time `t_ms` = milliseconds since boot (uint32).

**Classes**: protocol **v2** (17 Nov 2026, step E) has **8 classes, a 4 s window**, a stairs evidence rule, transition
events and a daily summary; version 1 (9 classes, 2 s window) is still accepted by the PC app for old recordings.

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

A v2 LIVE packet also carries the **posture state** (unknown / sitting / standing) that the device derives from the
transition events; the GUI shows it as text next to `still`. Sitting and standing cannot be separated from the window
itself at the tibia, so v2 has one class for both and the posture text is the best estimate of which one it is.
The old v1 table (walking, stairs_up, stairs_down, sitting, standing, lying, sit_to_stand, stand_to_sit, bed_transfer)
is kept in the app for v1 packets and for recordings made before 17 Nov 2026.

### A. Bluetooth LE (binary)
Advertised name `KNEIL-xxxx` (last 4 hex digits of the device address). Custom service and characteristics:

| UUID | name | properties |
|---|---|---|
| `a8f50001-3e2c-4c6e-9b1a-6b4e45494c00` | KNEIL live service | |
| `a8f50002-3e2c-4c6e-9b1a-6b4e45494c00` | LIVE | notify |
| `a8f50003-3e2c-4c6e-9b1a-6b4e45494c00` | RAW | notify |
| `a8f50004-3e2c-4c6e-9b1a-6b4e45494c00` | CONTROL | write |
| `a8f50005-3e2c-4c6e-9b1a-6b4e45494c00` | INFO | notify (text lines) |
| `a8f50006-3e2c-4c6e-9b1a-6b4e45494c00` | SUMMARY | notify (v2: daily summary, 41 bytes) |

**LIVE packet, protocol v2** (22 bytes, once per second when a **4 s** window is classified):

| offset | type | field |
|---|---|---|
| 0 | uint8 | type = 0x01 |
| 1 | uint8 | protocol version = 2 |
| 2 | uint16 | sequence number (wraps) |
| 4 | uint32 | t_ms at the end of the window |
| 8 | uint8 | class **after the stairs rule** (0-7 or 255) |
| 9 | uint8 | class after the majority-of-3 smoothing (0-7 or 255) |
| 10 | uint8 | vote share of the **raw** class in % (forest only; 255 = not available) |
| 11 | uint8 | flags: bit0 self-test passed, bit1 input low-pass on, bit2 small model (tree) in use |
| 12 | int16 x3 | mean x, y, z of the window (mg) |
| 18 | uint16 | battery in mV (0 = not measured) |
| 20 | uint8 | **raw class** (argmax before the stairs rule; 0-7 or 255) — v2 only |
| 21 | uint8 | **event flags**: bit0 sit-to-stand counted in this window, bit1 stand-to-sit, bit2 bed transfer; bits 4-5 posture state (0 unknown, 1 sitting, 2 standing) — v2 only |

The stairs rule: a window predicted stairs_up or stairs_down stays stairs only if the vote share of the predicted
class is at least 60 %, otherwise it becomes walking (owner decision, 17 Nov 2026). Transition events are counted
once per event by the library (rule R1), which is why LIVE carries event flags instead of "count this window".

**RAW packet** (every 0.5 s while raw streaming is on): `uint8 type = 0x02`, `uint8 n` (samples in this packet),
`uint16 sequence`, `uint32 t_ms of the first sample`, then `n` samples of `int16 x, y, z` (mg) at 50 Hz.
Normally n = 25 (158 bytes; request ATT MTU 247 and data length extension). If the MTU is smaller, the firmware
sends more, shorter packets with n = floor((MTU - 3 - 8) / 6).

**SUMMARY packet (v2)**: `uint8 type = 0x04` + the 40-byte daily summary, format 2 (little-endian, packed):

| offset | type | field |
|---|---|---|
| 0 (packet 1) | uint8 | format = 2 |
| 1 | uint8 | number of classes = 8 |
| 2 | uint16 x8 | minutes per class (0-7) |
| 18 | uint16 | minutes of `still` in the sitting posture |
| 20 | uint16 | minutes of `still` in the standing posture |
| 22 | uint16 | minutes of `still` with an unknown posture |
| 24 | uint16 | sit-to-stand events |
| 26 | uint16 | stand-to-sit events |
| 28 | uint16 | bed-transfer events |
| 30 | uint16 | mean sit-to-stand run time, 0.1 s |
| 32 | uint16 | steps |
| 34 | uint16 | walking cadence, steps/min x 10 |
| 36 | uint16 | stairs cadence, steps/min x 10 |
| 38 | int16 | seated shank tilt, deg x 10 |

Sent when the central subscribes to SUMMARY, every 60 s while connected and on CONTROL `0x13`. It needs ATT MTU
>= 44; below that the device sends nothing and one INFO line saying why. The posture split is an assumption: a missed
event puts the following `still` minutes in the wrong bucket.

**CONTROL writes** (1 byte): `0x10` start raw streaming, `0x11` stop raw streaming, `0x12` run the self-test now
(the next LIVE packet reports the result in its flags), `0x13` send the daily summary now, `0x14` reset the daily
metrics (also one INFO line).

### B. USB serial (text, for the bench; the DK's virtual COM port, 115200 baud, 8N1)
One line per message, comma-separated, ending with `\n`:
- `L,<seq>,<t_ms>,<class>,<class_smoothed>,<vote_pct>,<flags>,<mean_x_mg>,<mean_y_mg>,<mean_z_mg>,<battery_mV>[,<raw_class>,<event_flags>]`
  (the two extra values are written for a v2 LIVE message; a v1 packet keeps 10 values)
- `R,<seq>,<t_ms_first>,<n>,x1,y1,z1,x2,y2,z2,...` (same content as the RAW packet)
- `D,<format>,<n_classes>,<min_0>,...,<min_7>,<min_sitting>,<min_standing>,<min_still_unknown>,<n_sts>,<n_s2s>,<n_bed>,<sts_s_x10>,<steps>,<cadence_x10>,<stairs_cadence_x10>,<sit_tilt_x10>`
  (the v2 daily summary; the app decodes it into its summary panel)
- `I,<free text>` for information lines (boot, self-test result, library version, model name and window). The GUI
  shows them in its log.
Commands from the PC are the same single letters on their own line: `S` start raw, `P` stop raw, `T` self-test,
`Q` send the daily summary, `Z` reset the daily metrics.

### C. BLE bridge to the PC (Seeed XIAO nRF52840 on USB)
The PC does not use its own Bluetooth: a **Seeed XIAO nRF52840** is the BLE central. It connects to `KNEIL-xxxx`,
subscribes to LIVE and RAW (and to INFO and SUMMARY when the device has them), and writes the received packets to its
USB serial port **as the text lines of section B** (`L`, `R`, `I`, `D`), byte for byte the same format as the DK's USB
port, so the PC uses one parser for both cables. LIVE v1 (20 bytes) and v2 (22 bytes) are both accepted.
Commands `S`, `P`, `T`, `Q`, `Z` from the PC are written to CONTROL as `0x10`, `0x11`, `0x12`, `0x13`, `0x14`. The
bridge adds only its own `B` lines:
- `B,SCAN` (PC -> bridge): scan 5 s; the bridge answers `B,FOUND,<name>,<address>,<rssi_dBm>` per device and `B,SCAN_DONE`.
- `B,CONNECT,<address>` or `B,CONNECT,AUTO` (the strongest `KNEIL-*`); `B,DISCONNECT`.
- `B,STATE,<idle|scanning|connecting|connected|lost>,<name>,<address>,<rssi_dBm>,<mtu>` (bridge -> PC) on every change
  and every 2 s while connected; `B,DROPS,<count>` if its USB buffer overflowed; `B,VERSION,<text>` at start-up.
The bridge requests ATT MTU 247 and data length extension, reconnects by itself after a link loss (state `lost`, then
`connecting`), and never changes the content of `L`/`R`/`I` lines. The KNEIL firmware needs nothing special for the
bridge: it is an ordinary BLE central.
