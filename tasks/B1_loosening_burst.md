# Task B1 (worker gemini, after R1): high-rate burst for spacer loosening (design study, no firmware yet)

Branch `gemini/B1`, new from `main`. Report `tasks/B1_report.md` and the design note `docs/BURST_LOOSENING.md`,
committed last. Code only for models and analysis (`pipeline/burst_model.py`); outputs under `cache\b1\`.
**No firmware change**: the owner approves the design first (chip rule in CLAUDE.md).

## Owner's idea (24 Nov 2026)
Raise the accelerometer rate for a few seconds to check whether the spacer has loosened. The implant accelerometer is
a **Bosch BMA580**: ODR 1.56 Hz - **6.4 kHz** (datasheet BST-BMA580-DS000 and Bosch flyer; the owner thought 100 kHz:
confirm from the datasheet and say so). Nyquist 3.2 kHz; the vibration studies used 30 Hz - 3 kHz (Arami 2017, doi
10.1007/s10439-017-1941-2) up to 5.5 kHz.

## The key problem
A loose interface changes how the structure **responds to an excitation**. A patient who is still gives almost none:
a burst during quiet standing records mostly sensor noise. Study the excitation options:
1. **Heel strike** (free, every step): burst triggered at initial contact during walking; average the spectra of N
   strikes; the input force is unknown, so use ratios between bands or axes, or the decay time.
2. **Watch-driven exciter**: the watch already has an NS4150B class-D amplifier. A small surface exciter (bone-conduction
   transducer instead of the speaker), held on the tibial tubercle or patella, plays a chirp 30 Hz - 3 kHz; the implant
   records at 6.4 kHz; the frequency response is computed from the known input. Say what exciter (size, force) and
   what coupling would be needed.
3. The watch vibration motor (one fixed frequency, ~150-250 Hz with harmonics): what it can and cannot show.

## Do
- **Datasheet facts** (cite pages): ODR and bandwidth per mode, noise density at high ODR, FIFO size, current at
  6.4 kHz vs 50 Hz, range, how to switch ODR at run time, any data-ready / FIFO interrupt limits.
- **Model**: a simple lumped (2-3 mass) model of tibia - cement spacer - femur with an interface stiffness and damping;
  how the resonance and the response change as the interface stiffness falls (loosening), using published stiffness
  values (cite). Is the shift inside 0-3.2 kHz and larger than the sensor noise for options 1-3?
- **Data path on the nRF54L15**: raw 2 s at 6.4 kHz x 3 axes x 2 B = 77 KB vs an on-chip Welch spectrum (e.g. 128
  bins); RAM, CPU, BLE time and energy per check for both; how often (daily, weekly?).
- **Bench test plan** for the owner: sawbones tibia + the spacer, fixed vs deliberately loosened (shims, partial
  cement), each excitation option, what a pass looks like.

## Report
Datasheet table, model plots, the data-path budget, the recommended option with its open risks, the bench plan.
Mark every number measured / from a citation / assumed. Check every DOI resolves to the paper you cite.
