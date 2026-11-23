# Task V3b (worker gemini): viewer fixes after review

Branch `gemini/V3b`, new from `main` (V3 is merged). Report `tasks/V3b_report.md`, committed last. Same rules as V3.

## Review of V3 (manager)
Very good work: 50 motions, the chip library decision with C = Python on 3 motions, a careful audit of the old viewer
(38 motions, 100 Hz acc, preds never filled, Caicedo implant 3 cm / 0 mm), and useful findings (walker personas called
`still`, ramps called stairs). Problems seen in your renders:

1. **Body and scene do not match**: in `render_ramp_up.png` the ramp is not visible (flat floor; the body climbs in
   the air); in `render_stairs_up.png` and `blender_stairs_up/frame_0025.png` the feet are not on the steps (one foot
   below the step surface, the other floating). Place each prop from the motion itself: the floor, step positions and
   riser/tread, and the ramp start/angle must follow the foot trajectories (e.g. fit them to the stance-phase foot
   heights). Add a numeric check per motion: during stance, the lowest foot point minus the prop surface below it;
   report the median and 95th percentile of |error| per motion (target < 2 cm) for the floor, stairs and ramp motions.
2. **Blender figure**: add arms (decorative, swinging opposite to the legs, as the old viewer did; say they are not
   measured), human-like proportions (thinner limbs, a pelvis and shoulders), and make the knee spacer and the implant
   visible on the right tibia. Keep the studio look. Same check as 1 for the feet.
3. **In-sample label**: the forest was trained on the v1.6 synthetic set, the Camargo replay and Caicedo. Mark in
   `--list`, in the summary table and in the on-screen text every motion whose data (same person or same generated
   trial set) was in the training data, as "training data (in-sample)". Find out for each source whether it was in
   training (`stepD\windows_v11` source/person ids, `pipeline/export_v4.py`); the spacer-persona and walker motions in
   particular. The class shares are only an indication for in-sample motions.
4. Write `viewer/README.md` "How to start" for the owner: the exact command for the interactive viewer, which window
   shows what, and the keys. (You could not open the GUI; the owner will test it.)

## Checks
The foot-to-prop table (before / after), new `--render` PNGs and 2 Blender frames for stairs up, ramp up and
sit-to-stand (paths in the report), the in-sample table per source with its evidence.
