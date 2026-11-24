# F1 report: 3.2 kHz bench burst in the implant firmware

## 1. Status

Done, with one required deviation: the burst command is CONTROL **0x15**, not 0x13, because 0x13 is already the
daily-summary command (`Q`) and stealing it would break the existing PC app. The rest of the firmware, protocol,
tests, capture tool and bench plan are complete. Nothing was pushed or flashed.

## 2. Files

Firmware worktree (`kneil_firmware_agent`, branch `agent/F1`, commit `89477a6`):
- `boards/es4l15ba1_nrf54l15_cpuapp.overlay` — I2C21 at `I2C_BITRATE_FAST` (400 kHz), with the reason.
- `src/bma580_fifo.c/.h` — refactored 50 Hz/FIFO configuration, `bma580_fifo_set_3k2()` /
  `bma580_fifo_restore_50hz()`, I2C-error and FIFO-overflow counters (reset after the boot handshake), getters.
- `src/kneil_burst.c/.h` — **new** pure 64:1 averaging (3200 -> 50 Hz), host-tested.
- `src/kneil_live.c` — CONTROL `0x15`; BURST characteristic `a8f50007` / CCC; 2 s capture state machine in the
  acq thread; 38,400-byte static frame buffer; 10 ms FIFO timer; 50 Hz restore + immediate first read; BURST
  packets sent by the BLE thread at 10 ms intervals (LIVE first); LIVE flag bit 3; INFO line with id, frames,
  measured rate, overflows, I2C errors; extended INFO counters; firmware version 0.6.0.
- `CMakeLists.txt` — adds `src/kneil_burst.c`; `src/README.md` — burst description.
- `protocol/kneil_proto.h/.c` — `KNEIL_UUID_BURST`, `KNEIL_PKT_BURST`, BURST header/length limits, CONTROL
  `0x15`, LIVE flag `0x08`, `kneil_burst_t`, encode/decode.
- `protocol/test_kneil_proto.c` — BURST round trip, lengths, 39-frame maximum, MTU table, command bytes.
- `protocol/README.md` — UUID/table, BURST packet, CONTROL `0x15`, why not 0x13, flag bit 3.
- `pc_app/kneil/protocol.py` — `UUID_BURST`, `PKT_BURST`, `Burst` dataclass, decode, flag bit 3.
- `pc_app/tests/test_protocol.py` — BURST decode tests and flag property.
- `tools/burst_capture.py` — **new** direct-BLE capture (bleak): scan `KNEIL-*`, subscribe LIVE + BURST + INFO,
  send `0x15`, save `burst_<time>.npz` (x, y, z, fs, INFO, burst id, MTU), plot signal and Welch PSD 0-1.6 kHz
  per axis, `--repeat N --gap s`.
- `tools/README.md` — the new tool and its requirements.
- `tests/test_burst_avg.c` — **new** host test for the 64:1 averaging.
- `docs/BENCH_BURST.md` — **new** one-page bench plan for the owner.

Workspace (`kneil_v4_agent`, branch `agent/F1`): `tasks/F1_report.md` (this file), committed last.
No bridge changes.

## 3. Commands

Environment (no `nrfutil`/`west` on PATH), same as E2:

```powershell
$tc = "C:\ncs\toolchains\0b393f9e1b"
$env:PATH = "$tc;$tc\mingw64\bin;$tc\bin;$tc\opt\bin;$tc\opt\bin\Scripts;$tc\opt\nanopb\generator-bin;$tc\opt\zephyr-sdk\arm-zephyr-eabi\bin;$env:PATH"
$env:PYTHONPATH = "$tc\opt\bin;$tc\opt\bin\Lib;$tc\opt\bin\Lib\site-packages"
$env:ZEPHYR_TOOLCHAIN_VARIANT = "zephyr"; $env:ZEPHYR_SDK_INSTALL_DIR = "$tc\opt\zephyr-sdk"
$env:ZEPHYR_BASE = "C:\ncs\v3.1.0\zephyr"
```

```powershell
# in kneil_firmware_agent
west build -d build_kneil -b es4l15ba1/nrf54l15/cpuapp . --pristine=always -- `
  "-DBOARD_ROOT=C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_firmware_agent" "-DEXTRA_CONF_FILE=kneil.conf"
west build -d build_kneil --domain kneil_firmware_agent -t ram_report
west build -d build_kneil --domain kneil_firmware_agent -t rom_report

# host tests
gcc -std=c99 -Wall -Wextra -o test_kneil_proto protocol\test_kneil_proto.c protocol\kneil_proto.c
test_kneil_proto
gcc -std=c99 -Wall -Wextra -Iprotocol -Isrc -o test_burst_avg tests\test_burst_avg.c src\kneil_burst.c -lm
test_burst_avg

# PC app
cd pc_app
python -m unittest discover -s tests

# syntax / argument check of the capture tool (bleak is not installed here)
python -m py_compile tools\burst_capture.py
python tools\burst_capture.py --help
```

## 4. Acceptance checks

### 4.1 Build, warnings, flash and RAM — PASS

- `west build ... --pristine=always`: success (`merged.hex` written), **0 warnings, 0 errors** in the build log.
  The direct `west build -d build_kneil` re-run returned exit code 0.
- Baseline (same tree before F1, E2 build): **386,636 B flash / 53,793 B RAM**.
- F1: **389,280 B flash (26.62 % of 1,428 KB) / 93,136 B RAM (48.38 % of 188 KB)**.
- Delta: **+2,644 B flash, +39,343 B RAM**. The RAM delta is the 38,400-byte frame buffer plus the two thread
  stacks (BLE 1536 -> 3072) and the burst state/code; no dynamic allocation.
- The generated `zephyr.dts` shows `i2c21` `clock-frequency = <0x61a80>` = **400,000 Hz**.

### 4.2 Protocol tests and PC app tests — PASS (39 PC tests)

- C protocol test: `PROTOCOL TEST: PASS` (includes BURST encode/decode, 2-frame example, 39-frame maximum,
  wrong-length rejection, MTU 247/23 limits, CONTROL bytes).
- PC app: **39 tests, OK** (was 35): BURST decode, wrong length, 39/40-frame limits, LIVE flag bit 3.
- The BURST packet is 7 header bytes + 6n; at MTU 247 `n = 39` (packet 241 bytes). The example bytes are identical
  in the C and Python tests.

### 4.3 64:1 averaging host test — PASS

`tests/test_burst_avg.c`: 6400 inputs (2 s at 3.2 kHz) -> **100 outputs (50.0 Hz)**, 10 checks, 0 failed. Each
output equals the independent arithmetic mean of its 64-sample block (within 0.51 mg), including negative values;
a partial group does not emit; reset clears the accumulator.

### 4.4 Firmware behaviour — PASS by code/host checks (not on hardware)

- 3.2 kHz value: `ACC_CONF_1 = 0xAB` (HPM, normal filter, `acc_odr = 0xB`), datasheet BST-BMA580-DS000-05
  **p. 93**, register 0x31; range stays `ACC_CONF_2 = 0x0E` (±8 g).
- Acquisition: switch, 10 ms FIFO reads (about 32 frames/read; FIFO full in about 45 ms), static
  `int16_t burst_raw[6400][3]` = **38,400 B**, restore with the same 50 Hz/FIFO configuration, immediate first
  50 Hz read 20 ms after the restore.
- Classifier: every 64 burst samples are averaged and pushed with a 20 ms timestamp; 100 averages over the burst.
- BURST send: one burst at a time; a request during capture/send is refused with an INFO line; BURST packets are
  sent after the burst by the BLE thread, one every 10 ms, LIVE drained first each loop; an INFO line after the
  last packet gives id, frames, measured rate (`frames*1000/elapsed_ms`), overflow and I2C-error counts.
- LIVE: flag bit 3 is set while a burst is acquiring or being sent (a spare bit exists, as allowed by the task).
- Contingency: link loss during capture/send aborts the send and returns the state to idle; a failed 50 Hz
  restore restarts the sensor and resets the classifier.

### 4.5 Bench plan — PASS

`docs/BENCH_BURST.md` is the one-page plan: flash command, 30 min soak at 400 kHz with the INFO counters,
5 fixed + 5 loosened bursts with a repeatable tap, expected NPZ/plot (signal + Welch 0-1.6 kHz), pass/fail.
It notes that the BMA580 bandwidth at ODR 3.2 kHz is about 850 Hz (datasheet Table 3), so energy above that is
sensor-attenuated even though the plot shows 0-1.6 kHz.

### 4.6 Capture tool — PASS (offline checks only; no device)

- `py_compile` OK; `--help` lists all options.
- `parse_burst()` decoded the protocol example exactly: id 3, seq 42, first 128, 2 frames.
- The NPZ + plot path was exercised on 6400 synthetic frames: `.npz` (6400 frames, 0 missing, fs 3200) and a PNG
  with three time plots and three Welch spectra were written. The live BLE path was **not** run because `bleak`
  is not installed in this Python (numpy/scipy/matplotlib are).

## 5. Problems and open questions

1. **CONTROL byte deviation (important).** The task says `0x13`, but `0x13` is already `KNEIL_CTRL_SUMMARY` / `Q`
   in protocol v2 (`kneil_live.c`, PC app `CONTROL_BYTES`). Reusing it would make an older PC app's "send summary"
   command trigger a burst, against "older centrals keep working". I used the next free byte **0x15** for the burst;
   `0x13` remains the daily summary. The capture tool sends 0x15. If the manager insists on 0x13, one of the two
   commands must move and the PC app/bridge tests must change; please decide.
2. **No hardware test.** Nothing was flashed. The 400 kHz soak, 3.2 kHz FIFO drains, measured rate, BURST transfer
   and the tap spectra must be checked by the owner with `docs/BENCH_BURST.md`. Real bus errors and overflow
   counts are unknown until then.
3. **`bleak` missing.** `tools/burst_capture.py` was syntax-checked and its packet/NPZ/plot functions were tested
   with synthetic data, but no BLE capture was possible here. Install with `python -m pip install bleak` (not done,
   per the rules). The capture tool requires ATT MTU 247 for a reasonable transfer; at MTU 23 it works but is very
   slow (2 frames/packet).
4. **Sensor bandwidth.** At ODR 3.2 kHz the datasheet lists about 850 Hz effective bandwidth (Table 3), while the
   task asks for plots to 1.6 kHz. The 400-650 Hz loosening mode is inside; the 1.6-3.4 kHz mode is not reliably
   observable with this setting. The B1 note and the bench plan say this.
5. **0x13 conflict could hide a second issue:** the SUMMARY subscription is now cleared on disconnect (it was not
   before). This is a small correctness fix, not a protocol change; no older central is affected.
6. **No on-chip spectrum / watch exciter.** Not in F1, as instructed.
7. **Burst buffer size is fixed** at 2 s x 3200 Hz x 3 axes x 2 B = 38,400 B; a longer burst or an extra axis would
   need a RAM decision (93,136 B of 188 KB used now).
8. **The bridge is unchanged** and does not subscribe to BURST; the PC tool uses direct BLE, as required. A future
   bridge path would need a new text line or pass-through.
