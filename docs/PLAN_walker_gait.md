# Plan: walker and crutch gait called "still" (23 Nov 2026)

## Problem (measured, out-of-sample)
In the viewer, the 8 spacer-period personas (walker, crutches, static spacer; AB07 strides recomposed with pauses and
weight-bearing limits; **not** in the training data) are classified `still` in 96-100 % of the 4 s windows when the
gait is ultra-slow (about 0.3 m/s with 33-39 % pauses). During the spacer period the device would then miss most
walking time and steps. Cause (assumed, to be checked): no training set has walker or crutch gait, and a 4 s window
holds only one or two slow, soft steps.

## Steps
| step | who | what | chip change? |
|---|---|---|---|
| 1. Diagnose | Gemini (G2) | Why `still`: steps per window, feature values of walker windows vs real still and slow walking, which features decide (tree votes); is the persona motion itself plausible (speed, cadence, pauses vs published walker/crutch gait)? Proposed label rule for "walking" with an aid. Public datasets with walker / crutch / rollator gait (list, licence, sensors, whether a shank signal exists). | no |
| 2. Data | DeepSeek | Generate many walker / crutch / step-to personas with the generator (vary speed, pause share, weight-bearing, step-to vs step-through), labelled by the step-1 rule; add any usable public data through the virtual implant. | no |
| 3. Experiment | DeepSeek | CV by person (3 seeds): V4half + aid gait at several weights; metrics: aid-gait walking recall, `still` precision on real still data, all D-step metrics (no regression, fast walking called stairs stays low). | no |
| 4. Decision | owner | Choose the variant. Same 8 classes and 4 s window, so only the model changes (export V4.1); protocol and app stay. | model only |
| 5. Export + firmware | DeepSeek | Export V4.1, host test, firmware build; Gemini reviews. | model only |
| 6. Real check | owner | Record with the device and the truth keys: walking with a walker and with crutches, slow, with pauses (the PC app or the watch). This is the only real validation. | no |

Step 6 can happen any time; the earlier the better (it may change step 1's label rule).

## Open questions for the owner (later, not blocking step 1)
- Is very slow walking with long pauses "walking" for the clinical question (activity minutes, steps), or should
  pauses count as still? Step 1 proposes a rule; the owner decides before step 2.
- Ramps are called stairs (no ramp data in training). Same approach later if ramps matter.
