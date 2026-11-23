# Task V3d (worker gemini): see-through right leg around the implant CAD

Branch `gemini/V3d`, new from `main` (V3c is merged). Report `tasks/V3d_report.md`, committed last. Same rules as V3c:
**never commit the OBJ or any mesh made from it**; read it from `sims_html` at run time.

## Owner's decision (24 Nov 2026)
Keep the implant CAD (femoral component, spacer, tibial component). Fix the "broken leg" look of the full-body view:
in `blender_cad_walk_full/frame_0000.png` the right thigh and shank shapes stop short and the parts float in a gap.

## Do
1. **Closed leg**: the right thigh and shank shapes continue through the knee (no gap), as on the left leg.
2. **See-through skin** on the right leg (thigh + shank, or at least the knee region with a soft fade): semi-transparent
   (about 25-40 % opacity, a light skin or blue tint, subtle rim/fresnel so the outline stays readable), so the chrome
   and white parts and the implant chip with its axes are clearly visible inside. The rest of the figure stays opaque.
   Eevee settings that make transparency render correctly (blend mode, shadow mode, sorting) as needed.
3. **MuJoCo viewer**: the same idea with geom alpha (right thigh/shank about 0.3), the CAD meshes opaque.
4. Do not add the bones yet (the owner decides later); leave the code ready for it (one switch).

## Renders (paths in the report; the manager looks at them)
Full-body walking (same frame as V3c), the 60 deg sit-to-stand close-up, a stairs-up frame, and the MuJoCo
`--render` of walking and sit-to-stand. Report render time per frame.
