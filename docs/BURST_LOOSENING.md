# KNEIL Design Note: High-Rate BMA580 Burst for Spacer Loosening

**Status**: Design study only — **no firmware or chip changes made**. Owner approval required before any firmware implementation.  
**Model script & plots**: `pipeline/burst_model.py` (`burst_model 1.0`), plots under `cache\b1\`.

---

## 1. Bosch BMA580 Datasheet Facts (`BST-BMA580-DS000`)

> **Correction on max ODR**: The BMA580 maximum output data rate is **6.4 kHz** (Nyquist **3.2 kHz**), **not** 100 kHz. That 0–3.2 kHz band covers the 30 Hz – 3 kHz vibration-loosening sweep used by Arami et al. (2018, DOI: `10.1007/s10439-017-1941-2`), though it does not reach 5.5 kHz.

| Parameter | BMA580 Specification | Source | Impact on 6.4 kHz Burst |
|---|---|---|---|
| **ODR range** | **1.5625 Hz – 6.4 kHz** | Cited (`BST-BMA580-DS000`) | Nyquist = **3.2 kHz** |
| **Measurement ranges** | `±2 g`, `±4 g`, `±8 g`, `±16 g` (16-bit) | Cited (`BST-BMA580-DS000`) | `0.244 mg/LSB` at `±8 g` |
| **Noise density (HPM)** | **120 µg/√Hz** typ | Cited (`BST-BMA580-DS000`) | **6.79 mg RMS** broadband over 3.2 kHz (computed) |
| **On-chip FIFO** | **1 KB (1,024 bytes)**, watermark & full INT | Cited (`BST-BMA580-DS000`) | At `6.4 kHz × 3 ax × 2 B = 38.4 KB/s`, FIFO fills in **26.7 ms** (computed) |
| **Current (HPM, 6.4 kHz)** | **125 µA** typ | Cited (`BST-BMA580-DS000`) | 2 s burst adds **0.06 µAh** sensor charge (negligible) |
| **Current (LPM @ 100 Hz)** | **18 µA** typ (`~12–15 µA` @ 50 Hz est.) | Cited / Assumed | Normal continuous gait monitoring mode |
| **Current (Suspend)** | **4.75 µA** typ | Cited (`BST-BMA580-DS000`) | Data-retention sleep |
| **Runtime ODR switch** | Write `ACC_CONF` (HPM, 6.4 kHz), flush FIFO, wait ~1–2 ms, drain on watermark INT, restore 50 Hz LPM & re-prime 6 Hz LP | Cited / Design | **Bus constraint**: 38.4 KB/s requires **SPI** (`>= 4–8 MHz` + EasyDMA, watermark every ~20 ms); 400 kHz I2C would overflow! |

---

## 2. Lumped-Mass Vibration Model (`pipeline/burst_model.py`)

3-DOF model of **Tibia (`0.60 kg`) – Cement/Interface (`k_if, c_if`) – Tibial Spacer (`0.12 kg`) – Articulating Contact (`k_art = 8e6 N/m`) – Femur (`1.20 kg`)** (*assumed* lumped parameters grounded in published PMMA modulus `2.4–2.7 GPa` and cancellous bone `0.1–1.0 GPa`, Williams & Johnson 1989, DOI: `10.1016/0021-9290(89)90017-1`):

| Remaining `k_if` | Nominal `f2` (femur-spacer) | Nominal `f3` (spacer-tibia, `k_if0=4e7 N/m`) | Stiff bound `f3` (`k_if0=2e8 N/m`) | Inside 3.2 kHz Nyquist? |
|---|---:|---:|---:|---|
| **100% (Fixed)** | `631 Hz` | `3,405 Hz` | `7,217 Hz` | `f2` yes; `f3` near/above Nyquist |
| **50%** | `593 Hz` | `2,565 Hz` | `5,173 Hz` | Nominal `f2, f3` both inside |
| **30%** | `551 Hz` | `2,145 Hz` | `4,080 Hz` | Nominal `f2, f3` both inside |
| **10% (Loose)** | `418 Hz` | `1,644 Hz` | `2,565 Hz` | **Both nominal & stiff inside** |
| **3% (Very loose)** | `266 Hz` | `1,448 Hz` | `1,778 Hz` | **Both inside** |

Plots: `cache\b1\plot1_lumped_model_frf.png` and `cache\b1\plot2_excitation_comparison.png`.

---

## 3. Excitation Options Comparison (6.4 kHz BMA580, 120 µg/√Hz noise)

| Option | Excitation | Simulated SNR & Loosening Signature | Pros | Cons / Risks |
|---|---|---|---|---|
| **1. Heel strike** | Free, every walking step (`N = 20` averaged 0.25 s bursts triggered at initial contact) | Peak SNR **41–50 dB**; `500–2500 / 50–400 Hz` band ratio drops **9×** (`0.009 -> 0.001`) from fixed to 10% loose | Zero extra hardware; automatic passive daily check | Unknown input force; strongly confounded by **shoes, floor surface, and walking speed** |
| **2. Watch-driven bone-conduction exciter** | Watch's **NS4150B** Class-D amp (`3.0–5.0 V`, `~0.8 W` into `8 Ω` @ 3.7 V, cited) driving a small **15–22 mm, 8 Ω, 1 W** surface exciter (e.g. Dayton `BCT-1` / `DAEX13CT-8`, ~0.5 N) held on the **tibial tubercle** (minimal soft tissue) playing a 2 s `30 Hz – 3 kHz` log-chirp | Peak SNR **17–40 dB** across `625–3000 Hz`; cleanly tracks downward resonance shift (`f2` & `f3`) via transfer function `H(f)` | **Known input waveform**; immune to shoes/floor/speed; matches Arami et al. (2018) | Requires holding exciter on tibial tubercle with consistent ~5–10 N hand pressure + BLE start sync; soft tissue attenuates `> 1.5 kHz` |
| **3. Watch vibration motor** | Built-in ERM/LRA at fixed `~200 Hz` (+ weak 400/600 Hz harmonics) | `24–29 dB` at 200 Hz only; **`0 dB` (pure noise)** above 650 Hz | Already in watch | **Cannot track resonance frequency shift**; single-frequency amplitude is confounded by hand pressure |

---

## 4. nRF54L15 Data-Path & Energy Budget (per 2 s @ 6.4 kHz Check)

| Path | Payload / Check | RAM Needed | MCU CPU @ 128 MHz | BLE 2M PHY Time | Total Energy / Check | Recommended Cadence |
|---|---:|---:|---:|---:|---:|---|
| **Raw 3-axis stream** (`12,800 × 3 × 2 B`) | **76.8 KB** | ~78 KB | ~5 ms (DMA only) | **~0.96 s** | **~18.5 mJ (`1.71 µAh`)** | Research / bench / weekly clinic check |
| **On-chip Welch PSD (3 axes, 128 bins)** | **768 B** | **~4.0 KB** | ~35 ms (99×256-pt FFT) | **~10 ms** | **~0.55 mJ (`0.051 µAh`)** | **Weekly** (or daily: `< 0.02 mAh/yr`!) |
| **On-chip Welch PSD (1 axial axis, 128 bins)** | **256 B** | **~3.0 KB** | ~12 ms | **~5 ms** | **~0.25 mJ (`0.023 µAh`)** | Weekly / daily |

- **Battery impact**: Even a **weekly** 3-axis Welch check uses `52 × 0.051 µAh = 2.65 µAh/year` (essentially zero); even a weekly **raw 76.8 KB** dump uses `~89 µAh/year`.

---

## 5. Recommendation & Open Risks
1. **Recommended architecture**: **Staged hybrid** — use **Option 2 (watch-driven 30 Hz – 3 kHz bone-conduction exciter on the tibial tubercle)** as the primary weekly loosening check (known input, high SNR, immune to shoes/floor), paired with **on-chip 128-bin Welch PSD** (768 B) for routine use and **raw 76.8 KB dump** during bench/clinic validation. Optionally log **Option 1 (heel-strike high/low band ratio)** passively during walking only if bench tests show acceptable repeatability. **Do not use Option 3** (vibration motor) for loosening detection.
2. **Open hardware/clinical risks**:
   - **Bus wiring**: Verify whether BMA580 is connected to the nRF54L15 over **SPI** (required for 38.4 KB/s FIFO draining) or I2C (would overflow at 6.4 kHz).
   - **Soft-tissue damping in vivo**: Subcutaneous tissue over the tibial tubercle varies across patients; high-frequency energy (`> 2 kHz`) may attenuate more than the assumed 1.2 kHz roll-off.
   - **Baseline stiffness**: If a well-fixed spacer's `f3` sits above 3.2 kHz (stiff cortical contact), early loosening may only appear in `f2` (`~400–650 Hz`) or once `k_if` drops below `~25%`.

---

## 6. Bench Test Plan (Sawbones Tibia + Spacer)
1. **Setup**: Mount the instrumented spacer (BMA580 @ 6.4 kHz, `±8 g`, raw 2 s logging) into a **Sawbones composite proximal tibia** clamped at the distal shaft, with a **5 mm silicone gel pad** over the tibial tubercle to mimic skin/subcutaneous tissue.
2. **Conditions (4 fixation states)**:
   - `Fixed`: full PMMA cement mantle (baseline; repeat 5× with exciter lifted/re-placed between runs to measure coupling repeatability).
   - `Partial-50%`: half-mantle cement (posterior debond simulated with thin PTFE sheet).
   - `Shim-loose`: 0.3–0.5 mm elastomer/paper shim under tibial tray (micromotion).
   - `Unbonded`: dry press-fit spacer (gross loosening).
3. **Test all 3 excitations on every state**:
   - **Opt 1**: 20 repeatable rubber-mallet taps on the distal tibia (simulating heel strike, varying tap force ±30%).
   - **Opt 2**: Watch NS4150B + 15–22 mm `8 Ω` bone-conduction exciter held on the gel-padded tibial tubercle with ~5 N and ~10 N force, playing a 2 s `30 Hz – 3 kHz` log-chirp (5 repeats each).
   - **Opt 3**: Watch vibration motor held on the same spot for 2 s (5 repeats).
4. **Pass criteria**:
   - Peak resonance frequency (`f2` or `f3`) shifts downward by **`>= 15%`** (and `> 3×` the re-placement repeatability SD) between `Fixed` and `Shim-loose` / `Partial-50%`.
   - SNR at the tracked resonance peak stays **`>= 15 dB`** above the BMA580 `120 µg/√Hz` noise floor across both 5 N and 10 N coupling forces.
   - Zero FIFO overflows over 10 consecutive 2 s bursts at 6.4 kHz on the nRF54L15.

## Manager's check (24 Nov 2026)
- DOIs checked on Crossref: all three match (Arami 2017, Williams 1989, Schumacher 2024). The BMA580 FIFO, noise and
  current values were not re-checked against the datasheet: confirm them before any firmware.
- **The bus question is answered from the firmware**: the BMA580 is on **I2C** (`i2c21` in
  `kneil_firmware/boards/KAGAFEI/es4l15ba1/es4l15ba1_nrf54l15_cpuapp.dts`), and the app overlay runs it at **100 kHz**
  (`boards/es4l15ba1_nrf54l15_cpuapp.overlay`, set to rule out bus faults). 100 kHz carries about 10 KB/s, far below
  the 38.4 KB/s of a 3-axis 6.4 kHz burst. Options without a board change: (a) 3.2 kHz, 3 axes = 19.2 KB/s with the bus
  at 400 kHz (Nyquist 1.6 kHz: the f2 shift 631 -> 418 -> 266 Hz stays visible, f3 is lost); (b) one axis at 6.4 kHz =
  12.8 KB/s at 400 kHz, if the BMA580 FIFO can hold single-axis data (datasheet check); (c) 6.4 kHz, 3 axes needs the
  bus at 1 MHz (Fm+), if both the nRF54L15 TWIM and the BMA580 support it on this board (datasheet + bench check).
  Any of these is a firmware change: the owner decides.
