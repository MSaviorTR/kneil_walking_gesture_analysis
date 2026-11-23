# Task V3c (worker gemini): the owner's knee implant CAD in the viewer

Branch `gemini/V3c`, new from `main`. Report `tasks/V3c_report.md`, committed last. Same rules as V3/V3b.

## The CAD model (owner's file, read only)
`C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\sims_html\j_a_j_model.obj` (+ `.mtl`), 5 groups, units **cm**, z up.
The manager identified the parts from their material and position (and a quick render):

| group | part | material | z range (cm) |
|---|---|---|---|
| Body31 | femoral component | Chrome | 0.2 .. 6.5 |
| Body23 | spacer (insert) | Nylon_6-6_(White) | -0.5 .. 2.0 |
| Body25 | tibial component (tray + stem) | Chrome | -4.8 .. -0.5 |
| Body46 | femur | Bone | 0.8 .. 15.0 (**not used now**) |
| Body32 | tibia | Bone | -12.5 .. -0.9 (**not used now**) |

**Use only the femoral component, the spacer and the tibial component for now** (the owner will decide about the bones
later). **Do not commit the OBJ or any mesh made from it** (the repo is public; this is the owner's CAD): read it from
`sims_html`, write converted meshes only under `cache\viewer\` (git-ignored). The code may contain the path.

## Do
1. Find the model's anterior direction and medio-lateral axis from the geometry (e.g. the femoral component's anterior
   flange and trochlear groove, the tray's shape) and state how you found it. Scale cm -> m.
2. Attach the femoral component to the femur segment and the spacer + tibial component to the tibia segment of the
   viewer's model, so the joint line of the CAD (spacer top / femoral condyles) sits at the model's knee joint centre
   in standing (knee straight). The KNEIL implant point (2.5 cm below the joint centre, 5 mm anterior, on the tibia)
   and its x/y/z axes must be drawn at their place relative to these parts.
3. **Blender**: replace the current stylised spacer on the right knee with the three parts (chrome and white
   materials); keep the rest of the figure. Render 2 close-up frames of the right knee (standing, and about 60 deg
   knee flexion during sit-to-stand) and 1 full-body walking frame.
4. **MuJoCo viewer**: add the three parts as visual-only mesh geoms (no collisions) on the right leg; decimate if the
   viewer gets slow (say the face count used).
5. Check: how much the femoral component and the spacer overlap or separate over a gait cycle and a sit-to-stand
   (they move with different segments); report the maximum interpenetration / gap in mm. A large value means the
   attachment points are wrong, not that the CAD is wrong.

## Report
How the axes were found, the transform (rotation + offset) per part, the overlap/gap numbers, the face counts and the
render paths (the manager looks at them). The owner will decide whether the CAD stays.
