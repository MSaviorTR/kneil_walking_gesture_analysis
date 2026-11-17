/* Written by pipeline/export_v4.py (KNEIL V4). Owner decision 17 Nov 2026 (docs/STEP_D_SUMMARY.md). */
#ifndef KNEIL_MODEL_INFO_H
#define KNEIL_MODEL_INFO_H
#define KNEIL_MODEL_FS_HZ 50                 /* trained on 50 Hz data */
#define KNEIL_MODEL_N_FEATURES 20
#define KNEIL_MODEL_LOWPASS_HZ 6             /* input low-pass used in training, applied on the device */
#define KNEIL_MODEL_WIN_S 4                   /* window length in seconds */
#define KNEIL_MODEL_HOP_S 1                   /* classify every HOP_S seconds */
#define KNEIL_MODEL_N_CLASSES 8
#define KNEIL_MODEL_STAIRS_MIN_VOTE 0.60f /* stairs kept only with this vote share */
#define KNEIL_MODEL_NAME "V4half 4s"
#define KNEIL_MODEL_DATASET "kneil_dataset_v1_6; kneil_camargo_v1_3; caicedo_2020; real implant-site (CeTI, KneE-PAD, MHEALTH, Marpino, PAMAP2, WearGait-PD, Luo, Lencioni); V4half"
#endif
