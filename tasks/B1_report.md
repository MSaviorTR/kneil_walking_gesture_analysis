# Task B1 Report (worker gemini): High-Rate BMA580 Burst for Spacer Loosening (Design Study)

## 1. Status
done

## 2. Files
- `pipeline/burst_model.py` (added, `burst_model 1.0`): 3-DOF lumped mass-spring-damper model of tibia – cement interface – spacer – femur, 6.4 kHz BMA580 burst simulation (120 µg/√Hz noise, 16-bit ±8 g quantisation) for Options 1–3 (heel strike, watch-driven bone-conduction exciter chirp, watch vibration motor), and nRF54L15 RAM / CPU / BLE / energy data-path budget.
- `docs/BURST_LOOSENING.md` (added): standalone engineering design note for the owner (BMA580 datasheet table, lumped model, excitation comparison, data-path budget, recommended staged approach, open risks, and Sawbones bench test plan).
- `tasks/B1_report.md` (added): this report.

Outputs (not committed, under `cache\b1\`):
- `cache\b1\plot1_lumped_model_frf.png`, `cache\b1\plot2_excitation_comparison.png`, `cache\b1\b1_summary.json`, `cache\b1\burst_model_log.txt`

No firmware, chip, library, or protocol change.

## 3. Commands
```powershell
git switch -c gemini/B1 main
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe pipeline\burst_model.py
```

## 4. Acceptance checks

### Check 1 — BMA580 datasheet facts & 100 kHz correction: **PASS**
Verified from Bosch Sensortec `BST-BMA580-DS000`:
- **Max ODR = `6.4 kHz`** (`1.5625 Hz – 6.4 kHz`, Nyquist = `3.2 kHz`) — **not 100 kHz**.
- Noise density = **`120 µg/√Hz`** typ (HPM) -> **`6.79 mg RMS`** over 3.2 kHz; ranges `±2/4/8/16 g` (16-bit); FIFO = **`1 KB` (1,024 B)** -> fills in **`26.7 ms`** at `6.4 kHz × 3 ax × 2 B = 38.4 KB/s` (**requires SPI**, not 400 kHz I2C!); current = **`125 µA`** (HPM), **`18 µA`** (LPM @ 100 Hz), **`4.75 µA`** (Suspend).
- Watch amplifier (`NS4150B` datasheet): `3.0–5.0 V`, `4–8 Ω`, `~2.8–3.0 W` @ 5 V (`~0.8 W` @ 3.7 V into `8 Ω` — ample for a miniature `15–22 mm`, `8 Ω`, `1 W` bone-conduction exciter).

### Check 2 — 3-DOF lumped model & excitation comparison: **PASS**
Plots saved and visually inspected: `cache\b1\plot1_lumped_model_frf.png` and `cache\b1\plot2_excitation_comparison.png`.
- **Modal shifts (`k_if` 100% -> 10% -> 3%)**: nominal `f2` shifts **`631 Hz -> 418 Hz -> 266 Hz`** and `f3` shifts **`3,405 Hz -> 1,644 Hz -> 1,448 Hz`** (squarely inside 0–3.2 kHz Nyquist); even in the stiff bound (`k_if0 = 2e8 N/m`), `f3` enters the 3.2 kHz band below `~20%` stiffness (`2,565 Hz` at 10%).
- **Option 1 (20 averaged heel strikes)**: peak SNR `41–50 dB`, `500–2500 / 50–400 Hz` power ratio drops `9×` (`0.009 -> 0.001`), zero hardware, but confounded by shoes/floor/speed.
- **Option 2 (watch-driven 30 Hz – 3 kHz exciter chirp on tibial tubercle)**: peak SNR **`17–40 dB`** with known input waveform; resolves resonance frequency shifts cleanly without shoe/floor confounding (**recommended primary method**).
- **Option 3 (watch 200 Hz vibration motor)**: `24–29 dB` at 200 Hz only, pure noise above 650 Hz — cannot track resonance frequency shifts.

### Check 3 — nRF54L15 data-path budget: **PASS**
- **Raw 2 s @ 6.4 kHz (3 axes)**: `76.8 KB`, `~78 KB` RAM, `~0.96 s` BLE 2M PHY, `~18.5 mJ` (`1.71 µAh`) per check.
- **On-chip 128-bin Welch PSD (3 axes)**: **`768 B`**, `~4.0 KB` RAM, `~35 ms` CPU @ 128 MHz, `~10 ms` BLE, **`~0.55 mJ` (`0.051 µAh`)** per check (`2.65 µAh/year` weekly).

### Check 4 — Design note & Sawbones bench plan: **PASS**
- Complete design note, datasheet table, data-path budget, recommended staged approach, open risks, and 4-state Sawbones bench test plan with quantitative pass criteria are in `docs/BURST_LOOSENING.md`.
- **Verified DOIs cited**:
  - `10.1007/s10439-017-1941-2` — Arami et al., *Ann. Biomed. Eng.* (2018), knee implant vibration loosening (`30 Hz – 3 kHz`).
  - `10.1016/0021-9290(89)90017-1` — Williams & Johnson, *J. Biomech.* (1989), PMMA / cancellous bone-cement elastic moduli.
  - `10.3390/s24144594` — *Sensors* (2024), structure-borne sound implant loosening.

## 5. Problems and open questions
- **Confirm BMA580 bus wiring on the nRF54L15 board**: SPI (`>= 4 MHz` + EasyDMA) is mandatory to drain the 1 KB FIFO every `~20 ms` at 6.4 kHz; 400 kHz I2C cannot sustain 38.4 KB/s.
- **In-vivo soft-tissue attenuation**: the model assumes a 1.2 kHz 1st-order soft-tissue roll-off over the tibial tubercle; actual coupling attenuation and re-placement repeatability must be measured in the Sawbones + gel-pad bench test before any firmware work.
- **No firmware or chip files were modified** (design study only).
