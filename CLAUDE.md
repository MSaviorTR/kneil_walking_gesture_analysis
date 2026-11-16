# KNEIL activity model — project context for Claude Code

## Who and how
I am Mehdi, an engineering PhD student (circuit boards, mechanical design, chemistry): do not explain basics.
English is not my first language: write short, plain sentences. Windows 11, VS Code, PowerShell.
Python 3.12 venv (numpy, scipy, pandas 3, scikit-learn, matplotlib, openpyxl, emlearn 0.23.2 with setuptools,
mujoco 3.17 for the Camargo replay); gcc from MSYS2 UCRT64 on the PATH.

**Working rules**
- Before any long run, test the code on a small subset or a mock with the real file format. Show me the result.
- Print a version line at the start of every script; write logs to files; save results as you go and resume.
- Separate measured results from assumptions; say when a number rests on few people.
- Never overwrite earlier results (V3 stays as it is); new work goes into new folders (V4).
- Ask me before changing anything the chip or the PC app depends on (class list, window length, BLE protocol).
- When something fails, first add a diagnostic that shows the cause; do not guess.

## The project
KNEIL: implantable BLE sensor in the tibial insert of an articulating knee spacer (two-stage revision for periprosthetic
joint infection): pH, K+ and a 3-axis accelerometer (nRF54L15, Zephyr). Accelerometer at **50 Hz, ±8 g**. Device frame:
**x anterior, y = subject's left, z superior**; standing reads (0, 0, +1 g). The implant point is **2.5 cm below the knee
joint centre, 5 mm anterior**, on the tibia.

**On-device classifier** (`kneil_tinyml`, library v1.1): causal 6 Hz input low-pass, 2 s windows every 1 s,
20 accelerometer features computed by C code (the same C code is used in training through ctypes), random forest
20 trees x depth 10 (scikit-learn -> emlearn, **float** thresholds) plus a single-tree option; majority-of-3 smoothing in
the daily metrics; self-test with 27 test vectors; host test `kneil_tinyml/tests/run_host_test.py`.
Current classes (9): 0 walking, 1 stairs_up, 2 stairs_down, 3 sitting, 4 standing, 5 lying, 6 sit_to_stand,
7 stand_to_sit, 8 bed_transfer.

## How the training data were made (pipeline/)
- `vimp.py` (virtual implant): a shank IMU with gyroscope -> the implant point by the rigid-body transfer
  f_P = f_S + alpha x r + omega x (omega x r); r = a fixed lever arm along the tibia axis. The tibia frame is set **once
  per person** (vimp.person_frame): z = gravity while standing still, y = main rotation axis while walking (signed by the
  forward swing), x = y x z. Validated on Camargo (22 people, 245 trials): |a| r 0.93, x r 0.97, z r 0.98, 0.27 g RMS
  (without the transfer: |a| r 0.27). The Seel knee-centre fit gave wrong lever arms and is not used.
- `stage01.py`: readers (WearGait-PD, KneE-PAD), robust file access, plausibility rule (mean forward lean while walking
  must be -5..+35 deg), the Camargo validation. `stage2.py`: implant-site data from WearGait-PD, KneE-PAD, Marpino, PAMAP2,
  MHEALTH and CeTI (from suit positions), the HAR70+/HARTH thigh+back activity labeller (leave-people-out macro-F1 0.79),
  one npz per person + index CSV. `stage3.py`: chip features for all windows, 5-fold cross-validation **by person**,
  report, export. `ext_datasets.py`: marker-based tibia signals (Caicedo; use for marker datasets).
  `camargo_replay.py` + `kneil_v1.py`: replay of measured joint angles in the KNEIL MuJoCo model (simulated implant).
- These modules were written for Google Colab (paths under /content, Drive remount). They must run **locally** now:
  make paths configurable, drop the remount, keep the logic.

## Results so far (cross-validated by person)
| Walking recognised | V2 | **V3 (deployed candidate)** |
|---|---|---|
| WearGait-PD controls / Parkinson (median per person) | 48 / 55 % | 89 / 87 % |
| CeTI / MHEALTH / PAMAP2 | 67 / 40 / 52 % | 98 / 100 / 83 % |
| Marpino / KneE-PAD (knee patients) | 32 / 36 % | 74 / 74 % |
| Caicedo older adults | 84 % | 84 % |
V3 keeps sit-to-stand 82 %, stand-to-sit 84 %, bed transfer 98.5 % (simulated). **Sitting vs standing cannot be separated
at the tibia** (still vertical shank in both); together ("upright and still") 92-100 % on every dataset. Seated knee
extensions look like lying. Real stairs were weak (up 40 %, down 53 %; only PAMAP2, 8 people).

**My own test with the real device** (implant hardware on the head of my tibia, no gyroscope): sitting and standing are
confused; **slow walking is recognised perfectly, but faster walking is called stairs up or stairs down**.

## Pitfalls already found (do not rediscover)
pandas 3 text columns (use pd.api.types, not np.issubdtype); WearGait-PD time column is text ('0 sec'), ids like HC100,
WHC001 (use the stage 2 index 'group' column for control/Parkinson); CeTI positions in cm, a mirrored axis layout, a header
row in motion.tsv (forward = walking direction); MHEALTH: 6 of 10 gyroscopes have the opposite sign (fixed by the
backward-lean retry); PAMAP2/MHEALTH arrays are stored under the key 'all' while their index rows say 'protocol';
Camargo AB06 treadmill/stair recordings have a mirrored gyroscope (flagged); Marpino does not say who is who (group = person
for the folds); do not count stage2_index_all.csv twice; the training scripts must call sys.executable, never 'python3'.
