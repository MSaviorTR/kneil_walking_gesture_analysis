# Flashing the V3 activity model on the nRF54L15 DK

**Model:** `KNEIL_results\tinyml_final_v3_lp6` (Google Drive), exported 16 Nov 2026, host self-test PASS.
Forest of 20 trees (18,900 nodes) plus a single small tree (1,117 nodes); 20 accelerometer features, 9 classes;
50 Hz input, 6 Hz input low-pass applied on the chip.

**Expected size:** forest about 160 KB of flash (about 8.5 bytes per node, measured on the v1 build), small tree about
10 KB, about 2.3 KB of RAM. If flash is tight: `CONFIG_KNEIL_TINYML_MODEL_SMALL=y`.

## On the PC (2 minutes)
1. Download the folder `KNEIL_results/tinyml_final_v3_lp6` from Google Drive (4 files).
2. In this folder: `python add_v3_model.py "<path to that folder>"`. It copies the files, checks the model information
   (50 Hz, 6 Hz, dataset ending with V3) and runs the host test. It must end with `READY`.

## On the board
Give `PROMPT_firmware_KNEIL_live.md` to the AI assistant in your firmware project. It goes step by step: module and
self-test, timing, accelerometer axes, USB text stream, Bluetooth LE. The PC side is `PROMPT_gui_KNEIL_live.md`
(PC app and the XIAO nRF52840 bridge). Both use the same protocol section.

## What good looks like
- Self-test: 0 feature failures, 0 class mismatches (as on the PC).
- Timing: well under 1 ms per window at 128 MHz (one window per second).
- Axes: device z up -> (0, 0, +1 g); x up -> (+1, 0, 0); y up -> (0, +1, 0). A wrong axis or sign makes walking look
  like stairs.
- Live: walking is recognised when you walk; sitting and standing may swap (see below), lying is reliable.
