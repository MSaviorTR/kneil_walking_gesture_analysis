# E2 report: V4 model in the firmware, BLE protocol v2, PC app

## 1. Status

Done — model V4 runs in the firmware (library 2.0), BLE protocol v2 with the LIVE 22-byte packet and the SUMMARY
characteristic, the bridge and the PC app handle v2 (and still v1), both hardware builds pass with measured
flash/RAM, and all checks below pass. Nothing was flashed and nothing was pushed.

## 2. Files

Firmware worktree (`kneil_firmware_agent`, branch `agent/E2`, one commit `eec25c2`):
- `include/kneil_tinyml.h`, `include/kneil_model_forest.h`, `include/kneil_model_tree.h`,
  `include/kneil_model_info.h`, `include/kneil_selftest.h`: library 2.0 + V4 model (copied from the workspace
  `main`, unchanged).
- `src/kneil_classifier.c`, `src/kneil_metrics.c`, `tests/host_test.c`, `tests/kneil_test_vectors.h`,
  `zephyr/Kconfig`: the same copy (v2.0 sources, 16 test vectors, new Kconfig text).
- `src/kneil_live.c`: uses the library for the class, probabilities and events; LIVE v2; SUMMARY characteristic and
  `0x13`/`0x14`; daily metrics (`kneil_metrics_update` + event-flag deltas + posture); `KNEIL_FW_VERSION 0.5.0`;
  INFO lines with the library version, model name and window.
- `protocol/kneil_proto.h`, `protocol/kneil_proto.c`: version 2 (LIVE v1+v2 decode, SUMMARY encode/decode, `D` line,
  `Q`/`Z` commands), `protocol/test_kneil_proto.c`: new tests.
- `bridge/src/main.c`, `bridge/README.md`: SUMMARY subscription, `D` lines, Q/Z.
- `pc_app/kneil/protocol.py`, `session.py`, `recording.py`, `ui.py`, `transports.py`, `tests/test_protocol.py`,
  `tests/test_session.py`: v2 support with v1 back-compatibility (details in 4.1).
- `docs/kneil_tinyml.md`, `docs/BUILD.md`, `README.md`: v2.0 / model V4 / protocol v2, measured sizes, the
  absolute `BOARD_ROOT` and the `--domain` fix.

Workspace (`kneil_v4_agent`, branch `agent/E2`):
- `prompts/PROMPT_firmware_KNEIL_live.md`, `prompts/PROMPT_gui_KNEIL_live.md`: 8-class table, 4 s window, LIVE v2,
  SUMMARY, posture, Q/Z, window centre 2 s.
- `docs/add_v3_model.py` (v1.1): refuses when the library already has a model with `KNEIL_MODEL_WIN_S`; also fixes
  its library path (`docs/../kneil_tinyml`).
- `tasks/E2_report.md` (this file).

## 3. Commands

Environment (no `nrfutil`/`west` on PATH): set the toolchain environment by hand from
`C:\ncs\toolchains\0b393f9e1b\environment.json`:

```powershell
$tc = "C:\ncs\toolchains\0b393f9e1b"
$env:PATH = "$tc;$tc\mingw64\bin;$tc\bin;$tc\opt\bin;$tc\opt\bin\Scripts;$tc\opt\nanopb\generator-bin;$tc\opt\zephyr-sdk\arm-zephyr-eabi\bin;$env:PATH"
$env:PYTHONPATH = "$tc\opt\bin;$tc\opt\bin\Lib;$tc\opt\bin\Lib\site-packages"
$env:ZEPHYR_TOOLCHAIN_VARIANT = "zephyr"; $env:ZEPHYR_SDK_INSTALL_DIR = "$tc\opt\zephyr-sdk"
$env:ZEPHYR_BASE = "C:\ncs\v3.1.0\zephyr"
```

```
# in kneil_firmware_agent
west build -d build_kneil      -b es4l15ba1/nrf54l15/cpuapp . --pristine=always -- "-DBOARD_ROOT=<abs path>" "-DEXTRA_CONF_FILE=kneil.conf"
west build -d build_kneil_tree -b es4l15ba1/nrf54l15/cpuapp . --pristine=always -- "-DBOARD_ROOT=<abs path>" "-DEXTRA_CONF_FILE=kneil.conf;tree_build.conf"
west build -d bridge/build -b xiao_ble bridge
west build -d build_v3         -b es4l15ba1/nrf54l15/cpuapp . --pristine=always -- "-DBOARD_ROOT=<abs path>" "-DEXTRA_CONF_FILE=kneil.conf"   # V3 baseline
python tests\run_host_test.py
gcc -std=c99 -Wall -Wextra -o test_kneil_proto protocol\test_kneil_proto.c protocol\kneil_proto.c ; test_kneil_proto
cd pc_app ; python -m unittest discover -s tests
# check 3 (temporary script, not committed): builds the library + kneil_proto.c into a DLL with gcc,
# replays 3 simulation CSVs, decodes with pc_app/kneil/protocol.py and compares with pipeline/metrics_ref.py
```

## 4. Acceptance checks

### 4.1 Host test, protocol test, PC tests — PASS

- `python tests\run_host_test.py`: `selftest: 16 vectors, max feature error 0, feature failures 0, class mismatches 0`
  and `HOST TEST: PASS (both models)`; sizes: classifier 3,436 B, metrics 208 B, summary 40 B.
- Protocol unit test: `PROTOCOL TEST: PASS` (LIVE v2 bytes/line, LIVE v1 still decodes to the v1 line, SUMMARY
  bytes/line, commands S/P/T/Q/Z, all length and version errors).
- PC app: **35 tests, OK** (was 25): new tests for LIVE v2 parsing/encoding, v1 back-compatibility, the SUMMARY `D`
  line and packet, the v2 device-column mapping (still + posture), events from the event flags, the 4 s window centre
  and the summary message.

### 4.2 Builds — PASS (measured, not estimated)

| build | flash | RAM |
|---|---|---|
| KNEIL live, forest (V4) | **386,664 B** (26.44 % of 1,428 KB) | **51,632 B** (26.82 % of 188 KB) |
| KNEIL live, single tree (V4) | **238,856 B** (16.33 %) | 51,632 B |
| KNEIL live, forest (V3 baseline, `origin/main` fd74429) | 409,668 B (28.02 %) | 48,708 B |
| bridge (xiao_ble) | 156,112 B (19.35 % of 788 KB) | 68,012 B (25.94 % of 256 KB) |

Model + library symbols (`arm-zephyr-eabi-nm`): V4 forest 157,366 B, V4 tree 9,576 B, V3 forest 193,884 B.
So the V4 forest is **36.5 kB smaller** (15,822 vs 18,302 nodes) and RAM is **+2,924 B** (classifier 2.2 kB -> 3,436 B
for the 4 s window and 8 probabilities, metrics 208 B). Both builds are warning-free; `arm-none-eabi` is not on the
PATH but the NCS toolchain's `arm-zephyr-eabi-gcc` and `-nm` were used.

### 4.3 Replay without hardware — PASS

Three simulation files fed through the host build of the library + `kneil_proto.c`, decoded with `protocol.py`:

| file | windows | classes seen | LIVE v2 decoded | summary vs `metrics_ref.py` |
|---|---|---|---|---|
| `P000_walking.csv` | 27 | 0 walking | 27/27 identical | **identical (40 bytes)** |
| `P000_sitstand.csv` | 34 | 3 still, 5 sit_to_stand, 6 stand_to_sit | 34/34 identical | **identical**; 2 sit-to-stand + 2 stand-to-sit events, mean 5.0 s |
| `P000_bed.csv` | 47 | 3 still, 4 lying, 7 bed_transfer | 47/47 identical | **identical**; 3 bed-transfer events |

Every LIVE v2 packet re-encodes its text line byte for byte (`parse_line(format_live(m)) == m`), and the SUMMARY
packet (41 bytes) decodes with `protocol.py` to the same fields as `metrics_ref`. The minutes are 0 in these three
short recordings (< 1 min); the event counts and the mean sit-to-stand time are non-zero as expected.

### 4.4 LIVE v1 back-compatibility — PASS

The v1 example packet of the old tests still decodes in C (`kneil_live_decode` with 20 bytes, version byte 1, raw
class 255, events 0) and in Python (`Live.version == 1`, the 10-value `L` line is written unchanged), and the bridge
accepts both lengths. The new host test prints both cases.

### 4.5 Only allowed files changed — PASS

`git diff --stat origin/main...agent/E2` in the firmware worktree lists 26 files, all in the allowed set:
`README.md`, `bridge/README.md`, `bridge/src/main.c`, `docs/BUILD.md`, `docs/kneil_tinyml.md`, `include/*`,
`pc_app/*` (5 modules + 2 tests), `protocol/*` (3 + README), `src/kneil_classifier.c`, `src/kneil_live.c`,
`src/kneil_metrics.c`, `tests/*`, `zephyr/Kconfig`. `src/main.c`, `bma580*`, `rtc.c`, `TEMP118.c`, `boards/` and
`prj.conf` are untouched; the workspace `kneil_tinyml/` was not modified (only read).

## 5. Problems and open questions

1. **`-DBOARD_ROOT=.` does not work** with the sysbuild default in NCS 3.1.0 (`Invalid BOARD`): the docs command had
   to use the absolute path, and `rom_report` needs `--domain kneil_firmware_agent` (the old `neilv2` domain name is
   the CMake project name, not the image name). Both are fixed in `docs/BUILD.md`.
2. **No `nrfutil`/`west` on the PATH.** I activated the toolchain by setting the variables from
   `C:\ncs\toolchains\0b393f9e1b\environment.json`; the exact block is in section 3. A one-line
   `nrfutil toolchain-manager launch --ncs-version v3.1.0 -- <command>` would be nicer in CI.
3. **pyserial is not installed** on this PC, so `pc_app` could not import `serial`; `transports.py` now imports it
   lazily and raises a clear `TransportError` only when a COM port is opened, so replay, demo and all unit tests run
   without it. A real BLE session needs `pip install pyserial`.
4. **The PC app keeps the 9-id space for totals and the confusion table**, mapping v2 `still` into sitting/standing by
   the posture state (unknown -> sitting). This is what makes "sitting vs standing" measurable on v2 (the task asked
   for it), but it means a v2 still window with an unknown posture counts as sitting in the accuracy table. The big
   label, the timeline and the legend use the 8-class v2 table with one colour for `still`, as asked.
5. **The demo mode still emits LIVE v1 lines** (back-compatibility path); a v2 demo would show the posture and the
   summary without hardware. Not done here.
6. **`tools/train_kneil_tinyml.py` in the firmware repo still trains the old 9-class/2 s models.** The V4 export lives
   in the training repo (`pipeline/export_v4.py`); porting the training tool to 8 classes/4 s is a later task (it is
   not used by this firmware build).
7. **No hardware test.** The suite stops at the host: nothing was flashed (owner does that), so the BLE SUMMARY
   characteristic, the 60 s timer and the MTU >= 44 check are checked by code review and unit tests only.
8. **The transition tie/run-gap semantics** of `transition_events.detect` (D3) differ slightly from the causal C rule
   (documented in E1, 4.5 and 5.4); the firmware follows the task's causal description, and the replay in 4.3 shows
   identical event counts on the three files.
