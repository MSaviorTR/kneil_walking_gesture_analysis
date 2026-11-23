# Task A1: aid-gait training data and the cross-validation experiment (steps 2-3 of the walker plan)

Branch `agent/A1`, new from `main`. Report `tasks/A1_report.md`, committed last. Read `docs/PLAN_walker_gait.md` and
`tasks/G2_report.md` (Gemini's diagnosis) first. Outputs only under `KNEIL_results\v4\stepF\` (new allowed folder,
see AGENTS.md). No chip, library or protocol change; no export.

## Problem
Slow walking with a walking aid (walker 0.2-0.35 m/s with pauses) is classified `still` 96-100 %: the training data
has no walking slower than ~0.5 m/s, so the forest's still/walking cut-offs sit in that gap (G2). The owner chose the
label rule **C**: a 4 s window with an aid is `walking` if it holds **>= 2 steps of either leg and >= 50 % of the window
is moving**; otherwise `still` (upright, no transition).

## Part A: aid-gait personas (`pipeline/aid_gait.py`, version 1.0)
1. Generate walker, crutch and step-to personas from **measured joint angles of many people** (the Camargo replay,
   `pipeline/camargo_replay.py`, 22 people) through the same virtual-implant path as the training data. **Do not use
   AB07**: the 8 spacer personas of the viewer are built from AB07 and stay an independent test set.
2. Vary, per persona: speed 0.15-0.55 m/s (by stretching strides and inserting pauses; the replay computes the
   accelerations from the stretched kinematics), pause share 0-45 % with **irregular** pause lengths, step-to vs
   step-through, weight-bearing (full / partial / toe-touch; non-weight-bearing only as a small set labelled by rule C),
   aid (pick-up walker, rollator, crutches), some standing rests and turns. Use published ranges (G2 report section 3)
   and say which you used.
3. Label every window by rule C from the foot contacts of the generated motion (not from the old 60 % `min_share`).
4. Test on 2 personas first (plot signal + labels), then generate at least 20 personas per source person (440+),
   each persona = one CV group tied to its source person.

## Part B: the experiment (`pipeline/cv_aid.py`, version 1.0)
5-fold CV **by source person** (aid personas fold with their source person), 3 seeds, W = 4 s, hop 1 s, 8 classes,
stairs rule 0.6. Variants: V4half (today), and V4half + aid gait at weight 0.25 / 0.5 / 1.0.
Metrics, mean (sd) over seeds:
- aid-gait walking recall (CV, held-out persons) by aid and speed band; steps-per-window bins;
- **external test**: the 8 viewer personas (`old_14`..`old_21`, from the viewer's motion cache or rebuilt) labelled
  by rule C: walking recall per persona;
- **cost**: real `still` windows called walking (%), per dataset; `still` precision;
- no regression: walking recall per dataset, walking called stairs (Lencioni fast, Luo FE, WearGait hurried), Luo /
  PAMAP2 stairs recall and precision, simulated sit-to-stand event recall, false events per hour (reuse D2/D3 code);
- model size (nodes).

## Acceptance checks
1. The 2-persona test plots (paths) and the label counts.
2. Persona table: count by aid, speed band, weight-bearing; windows walking/still by rule C.
3. The experiment table above for all variants; a one-screen summary for the owner (numbers only, no
   recommendation).
4. Repeat G2's check on the best variant: do the walker windows now pass the still/walking cut-offs, and does real still
   stay below them?
