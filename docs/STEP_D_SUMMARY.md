# Step D summary: which V4 model? (16 Nov 2026)

Sources: worker tasks D0-D3 (`tasks/D*_report.md`), results in `KNEIL_results\v4\stepD\`. All numbers are 5-fold
cross-validation **by person**, mean over **3 seeds** (seed noise: 0-3 points on big datasets, 5-8 on PAMAP2, ~7 % on
node counts; differences below ~2 points are not meaningful). 8 classes (sitting + standing = still).

Variants: **V3recipe** = V3 training data; **V4data** = + Luo + Lencioni walking; **V4half** = + Luo + Lencioni at half
weight. Stairs rule v2 = causal post-processing tuned for F0.5 (precision counts double).

## The owner's problem: fast walking called stairs (% of true walking windows)

| | today (V3recipe 2 s, no rule) | V4half 4 s, no rule | V4half 4 s + rule | V4data 4 s + rule | V4data 5 s + rule |
|---|---|---|---|---|---|
| Lencioni fast walkers | 12.8 | 4.9 | 1.1 | 0.5 | 0.5 |
| Luo flat walking (FE) | 17.5 | 11.0 | 2.8 | 1.9 | 0.6 |
| WearGait-PD HurriedPace | 7.9 | 6.2 | (see D3) | (see D3) | (see D3) |

## Main trade-offs by window length (v2 rule, from D3 4.4)

| W | variant | Luo stairs F0.5 | STS event recall (sim.) | false events/h | WearGait walking | KneE-PAD walking | nodes |
|---|---|---|---|---|---|---|---|
| 2 s | V3recipe | 66.9 | **86.8** | 2.3 | 87.7 | 67.7 | 17.7 k |
| 2 s | V4half | 76.0 | 83.3 | 2.4 | 84.5 | 61.6 | 18.7 k |
| 4 s | V4half | 82.4 | 78.1 | 0.9 | 86.1 | 70.4 | 16.1 k |
| 4 s | V4data | 83.8 | 77.6 | 0.9 | 85.7 | 68.7 | 16.4 k |
| 5 s | V4data | **87.8** | 64.4 | 0.1 | 84.4 | 76.7 | 15.0 k |

Stairs recall / precision on Luo at 4 s (V4half): stairs_up 71.5 / 58.0 without rule -> 49.2 / 75.7 with rule;
stairs_down 95.5 / 38.1 -> 90.6 / 61.4. Today (V3recipe 2 s, no rule): up 50.4 / 41.3, down 83.4 / 28.7.
PAMAP2 (7 people) stays weak in every setting (stairs up recall 30-54 %, precision 25-28 %).

The tuned rule at 4-5 s is simply **"stairs only if the forest vote share >= 0.5-0.6"** (no k-of-n needed: a 4 s window
already holds several strides); at 2 s it is "vote share >= 0.3 and 2 of the last 3 windows".

## Recommendation (manager; the owner decides — this changes the chip)
- **8 classes** (still = sitting + standing): no cost measured; sitting/standing split later by posture tracking.
- **Window 4 s, hop 1 s.** Best balance: stairs and fast-walking errors fall strongly (Luo FE 17.5 -> 2.8 %), walking
  recall on the old data is kept or better (KneE-PAD 64 -> 70, WearGait ~86), false transition events < 1/h.
  Cost: sit-to-stand events 87 -> 78 % recall (simulation only, 240 events). 5 s is better for stairs but loses
  transitions (64 %); 2 s keeps transitions but keeps the stairs problem.
- **V4half** (new data at half weight): within noise of V4data on stairs (82.4 vs 83.8) and slightly better on the old
  datasets; the safer choice.
- **Stairs rule: vote share >= 0.6.** Trades stairs-up recall (72 -> 49 %) for precision (58 -> 76 %) and removes most
  walking-called-stairs. If stairs counts matter more than false stairs, use 0.5 or no rule.

## What is not proven yet
- Transition events are validated on **simulated** data only (CeTI s01 postures last 0.1-0.3 s, TUG truth is
  approximate: both unusable). The first real test is the device recordings with the live-viewer ground-truth keys.
- No real spacer-period gait (walker, crutches) in any dataset.
- The Luo lever arm (0.26 m) is a data-driven choice (docs/STEP_C_NOTES.md); Luo dominates the stairs numbers.
- Step E (chip) must also re-check: RAM for a 200-sample window (3 x 200 floats = 2.4 kB), latency of 4 s, the daily
  metrics (transition runs, posture tracking) and the summary format version.
