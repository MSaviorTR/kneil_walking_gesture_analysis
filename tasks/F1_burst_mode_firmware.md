# Task F1 (worker deepseek): high-rate burst mode in the implant firmware (bench version)

Firmware worktree `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_firmware_agent`, new branch `agent/F1` from the
firmware repo's `main` (`718301d`). Report `tasks/F1_report.md` on `agent/F1` from `main` in `kneil_v4_agent`.
Never push, **never flash** (the owner flashes and runs the bench test). Read `docs/BURST_LOOSENING.md` first.

## Owner's decision (24 Nov 2026)
Bench version of the loosening burst: **BMA580 at 3.2 kHz, 3 axes, I2C bus at 400 kHz** (option 1 of the B1 note).
The owner approves this firmware and protocol addition; nothing else the chip or the PC app depends on may change.

## Facts (checked by the manager)
- BMA580 on `i2c21` at address 0x18, with the TEMP118 on the same bus; `boards/es4l15ba1_nrf54l15_cpuapp.overlay`
  sets the bus to 100 kHz (`I2C_BITRATE_STANDARD`) to rule out bus faults during earlier debugging.
- `src/bma580_fifo.c` already runs the 1024-byte FIFO (7 bytes per frame with the header, 146 frames) at 50 Hz, +-8 g.
  At 3.2 kHz: 22.4 KB/s of FIFO data, the FIFO fills in about 45 ms; a 400 kHz bus carries about 40 KB/s.
- RAM: 51,632 B of 188 KB used (README); a 2 s x 3.2 kHz x 3 axes x 2 B buffer is 38,400 B.
- BLE: services and characteristics in `src/kneil_live.c`; protocol in `protocol/README.md` (+ `kneil_proto.c/.h`,
  unit tests, the PC app's `protocol.py`). The last UUID used is SUMMARY `a8f50006`.

## Do
1. **Bus at 400 kHz** (`I2C_BITRATE_FAST`) in the overlay, with a comment why. Count I2C errors and FIFO overflows in
   the existing INFO/drop counters so the owner's soak test can see them.
2. **Burst command**: CONTROL `0x13` = one burst of 2 s at 3.2 kHz (refused with an INFO line if one is running or
   sent). The acquisition thread switches the BMA580 to 3.2 kHz (high-performance mode; datasheet register values,
   cite the page), drains the FIFO on a watermark or a timer often enough that it never overflows, stores the frames
   in a static 38,400-byte buffer, then restores the 50 Hz configuration exactly as `bma580_fifo_start()` sets it.
3. **Keep the classifier running**: during the burst, feed the 50 Hz pipeline with the mean of every 64 burst samples
   (3200 / 64 = 50 Hz), so LIVE, the windows and the daily metrics see no gap. Mark the burst in the LIVE flags only if
   a spare bit exists; otherwise leave LIVE unchanged.
4. **New optional characteristic BURST** `a8f50007-...` (notify): packets `uint8 type = 0x05, uint8 burst id,
   uint16 sequence, uint16 first frame index, uint8 n`, then n frames of `int16 x, y, z` (mg, device frame), n by the
   MTU as RAW does. Sent after the burst, at a rate that never delays LIVE. End with an INFO line: burst id, frames,
   measured rate (from the frame count and the k_uptime), overflows, I2C errors. Older centrals that do not know
   BURST keep working (no other packet changes). Update `protocol/README.md`, `kneil_proto.c/.h` + its unit test, and
   the PC app's `protocol.py` + its test (decode only).
5. **PC capture tool** `tools/burst_capture.py` (Python, `bleak`, the PC's own Bluetooth; the bridge is not changed):
   connect to `KNEIL-*`, subscribe LIVE + BURST + INFO, send `0x13`, save `burst_<time>.npz` (x, y, z, fs, INFO
   lines), plot the signal and a Welch spectrum (0-1.6 kHz) per axis. A `--repeat N --gap s` option for the bench.
6. Not now: the on-chip spectrum and the watch-driven exciter (later tasks).

## Checks
1. `west build` of the KNEIL live app (the same command as E2) with no new warnings; flash and RAM before/after.
2. Protocol unit tests and PC app tests pass (counts), including a BURST packet round trip.
3. A host test of the 64:1 averaging (a 3.2 kHz test signal -> the expected 50 Hz samples).
4. A one-page bench plan for the owner: flash, 30 min soak at 400 kHz with the INFO counters (no I2C errors, no
   overflows), then bursts with a tap test on the bench spacer (fixed vs loosened), what the plots should show.
