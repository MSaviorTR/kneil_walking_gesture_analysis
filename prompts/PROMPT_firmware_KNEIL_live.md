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

**Classes** (index = the classifier output; 255 = no result yet):

| index | name | GUI colour |
|---|---|---|
| 0 | walking | green |
| 1 | stairs_up | orange |
| 2 | stairs_down | dark orange |
| 3 | sitting | blue |
| 4 | standing | light blue |
| 5 | lying | purple |
| 6 | sit_to_stand | yellow |
| 7 | stand_to_sit | gold |
| 8 | bed_transfer | brown |

Sitting (3) and standing (4) are hard to tell apart at the tibia; the GUI must also show them together as
**"upright and still"**.

### A. Bluetooth LE (binary)
Advertised name `KNEIL-xxxx` (last 4 hex digits of the device address). Custom service and characteristics:

| UUID | name | properties |
|---|---|---|
| `a8f50001-3e2c-4c6e-9b1a-6b4e45494c00` | KNEIL live service | |
| `a8f50002-3e2c-4c6e-9b1a-6b4e45494c00` | LIVE | notify |
| `a8f50003-3e2c-4c6e-9b1a-6b4e45494c00` | RAW | notify |
| `a8f50004-3e2c-4c6e-9b1a-6b4e45494c00` | CONTROL | write |

**LIVE packet** (20 bytes, once per second when a 2 s window is classified):

| offset | type | field |
|---|---|---|
| 0 | uint8 | type = 0x01 |
| 1 | uint8 | protocol version = 1 |
| 2 | uint16 | sequence number (wraps) |
| 4 | uint32 | t_ms at the end of the window |
| 8 | uint8 | class (raw, 0-8 or 255) |
| 9 | uint8 | class after the majority-of-3 smoothing (0-8 or 255) |
| 10 | uint8 | vote share of the winning class in % (forest only; 255 = not available) |
| 11 | uint8 | flags: bit0 self-test passed, bit1 input low-pass on, bit2 small model (tree) in use |
| 12 | int16 x3 | mean x, y, z of the window (mg) |
| 18 | uint16 | battery in mV (0 = not measured) |

**RAW packet** (every 0.5 s while raw streaming is on): `uint8 type = 0x02`, `uint8 n` (samples in this packet),
`uint16 sequence`, `uint32 t_ms of the first sample`, then `n` samples of `int16 x, y, z` (mg) at 50 Hz.
Normally n = 25 (158 bytes; request ATT MTU 247 and data length extension). If the MTU is smaller, the firmware
sends more, shorter packets with n = floor((MTU - 3 - 8) / 6).

**CONTROL writes** (1 byte): `0x10` start raw streaming, `0x11` stop raw streaming, `0x12` run the self-test now
(the next LIVE packet reports the result in its flags).

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
