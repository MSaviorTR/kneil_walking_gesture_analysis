# Model V3: what it is and how well it works (16 Nov 2026)

**Training data:** simulated implant-site data (60 v1.6 synthetic patients, 22 Camargo subjects replayed in the KNEIL
model), Caicedo older adults (virtual implant from markers), and **real implant-site data of 265 people** computed from
their shank IMUs or motion suits (stage 2: WearGait-PD, CeTI, PAMAP2, MHEALTH, KneE-PAD, Marpino; about 64 h).

**Validation:** 5-fold cross-validation **by person**: every person is tested by a model that never saw them.

| Walking recognised | V2 | V3 |
|---|---|---|
| WearGait-PD controls (median per person) | 48 % | 89 % |
| WearGait-PD Parkinson's (median per person) | 55 % | 87 % |
| CeTI / MHEALTH / PAMAP2 | 67 / 40 / 52 % | 98 / 100 / 83 % |
| Marpino / KneE-PAD (knee patients) | 32 / 36 % | 74 / 74 % |
| Caicedo older adults | 84 % | 84 % |

Classes only the simulation contains are kept: sit-to-stand 80 -> 82 %, stand-to-sit 78 -> 84 %, bed transfer 99 %.

**Limits (important for the daily metrics):**
- **Sitting vs standing** cannot be separated reliably at the tibia (a still, vertical shank looks the same). Together,
  as **"upright and still"**, they are recognised 92-100 % on every dataset. Report that; treat the split as an estimate.
- **Seated knee extensions** look like lying (shank horizontal): rehabilitation exercises can inflate lying time.
- **Stairs** on real people are still weak (up 40 %, down 53 %; only 8 people with real stairs).
- Real spacer-period walking (walker, crutches, partial weight-bearing) is not in the data; the first device recordings
  with the ground-truth keys of the live viewer will measure it.
