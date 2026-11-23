# V3d Report — Closed See-Through Right Leg Around Implant CAD

## 1. Status
done

## 2. Files
- `viewer/implant_cad.py` (modified, v1.1): added `INCLUDE_BONES = False` and `BONE_PARTS = {'femur_bone': 'Body46', 'tibia_bone': 'Body32'}` plus `active_parts(include_bones=...)` so bone meshes remain excluded by default and can be toggled on later with a single switch.
- `viewer/kneil_viewer.py` (modified, v1.3): made right thigh (`femur_g_r`, radius `0.050 m`) and right shank (`tibia_g_r`, radius `0.045 m`) continuous full-length capsules (no gap at the knee) with semi-transparent blue tint (`rgba="0.24 0.56 0.80 0.28"`), enclosing the 100% opaque CAD meshes (`cad_femoral`, `cad_spacer`, `cad_tibial`) and ready to display `femur_bone` / `tibia_bone` if `INCLUDE_BONES` is enabled.
- `viewer/blender_render.py` (modified, v1.3): added `add_tapered_capsule()` (single watertight revolved capsule-frustum mesh with zero internal sphere-cap seams) and `make_glass_skin_mat()` (Fresnel-rimmed semi-transparent blue skin: `Layer Weight` Facing -> `Alpha` `0.22..0.62`, `surface_render_method='BLENDED'`, `use_backface_culling=True`, `use_transparency_overlap=False`, `visible_shadow=False`). Right thigh (`r=0.056..0.046 m`) and shank (`r=0.046..0.030 m`) run continuously through the knee around the opaque Chrome/Nylon CAD and cyan KNEIL chip + RGB axes; rest of the figure stays opaque. Ready to load `femur_bone` / `tibia_bone` when `INCLUDE_BONES` is enabled.
- `tasks/V3d_report.md` (added): this report.

Note: zero `.obj` or `.stl` files were staged or committed; `cache/` remains git-ignored.

## 3. Commands
```powershell
# 1. MuJoCo renders (walking and sit-to-stand)
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\kneil_viewer.py walk_healthy --render cache\viewer\v3d_mj_walk_healthy.png --t 10.0
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\kneil_viewer.py sit_to_stand --render cache\viewer\v3d_mj_sit_to_stand.png --t 5.4

# 2. Export 3 single-frame motion JSONs for Blender
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\export_motion.py walk_healthy --out cache\viewer\v3d_walk_full.json --t0 10.00 --max-s 0.03 --fps 25
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\export_motion.py sit_to_stand --out cache\viewer\v3d_knee_flex60.json --t0 5.30 --max-s 0.03 --fps 25
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\export_motion.py stairs_up --out cache\viewer\v3d_stairs_up.json --t0 6.00 --max-s 0.03 --fps 25

# 3. Render 3 Blender 5.2 studio frames (1920x1080, BLENDER_EEVEE, 24 samples)
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -P viewer\blender_render.py -- cache\viewer\v3d_walk_full.json cache\viewer\v3d_blender_walk_full --samples 24
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -P viewer\blender_render.py -- cache\viewer\v3d_knee_flex60.json cache\viewer\v3d_blender_knee_flex60 --closeup --samples 24
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -P viewer\blender_render.py -- cache\viewer\v3d_stairs_up.json cache\viewer\v3d_blender_stairs_up --samples 24
```

## 4. Acceptance checks

### Check 1 — Closed continuous right leg (no gap): **PASS**
- Both `viewer/blender_render.py` and `viewer/kneil_viewer.py` now render full-length right thigh (`0` to `-femur`) and right shank (`0` to `-tibia`) shapes matching the left leg, eliminating the "broken leg" gap seen in V3c.

### Check 2 — See-through Fresnel-rimmed skin on right leg (Blender 5.2 Eevee): **PASS**
- Right thigh and shank use `DeviceLegGlass` (`Alpha = 0.22` center to `0.62` grazing rim via `Layer Weight` Facing, `surface_render_method='BLENDED'`, `use_backface_culling=True`, `use_transparency_overlap=False`, `visible_shadow=False`) on single watertight tapered-capsule meshes (`add_tapered_capsule`, zero internal sphere-cap seams).
- Opaque Chrome femoral/tibial components, white Nylon 6-6 spacer, cyan KNEIL implant chip, and red/green/blue device axes remain crisp and clearly visible inside the right leg; torso, head, arms, left leg, and feet remain opaque.

### Check 3 — Translucent right leg in MuJoCo viewer: **PASS**
- Right thigh (`femur_g_r`, `r=0.050 m`) and right shank (`tibia_g_r`, `r=0.045 m`) render at `alpha = 0.28` (`rgba="0.24 0.56 0.80 0.28"`) around the 100% opaque CAD meshes (`cad_femoral`, `cad_spacer`, `cad_tibial`).

### Check 4 — Bones excluded by default, one-switch ready: **PASS**
- `viewer/implant_cad.py` defines `INCLUDE_BONES = False` and `BONE_PARTS = {'femur_bone': 'Body46', 'tibia_bone': 'Body32'}`; both `kneil_viewer.py` and `blender_render.py` automatically attach `femur_bone` (to `femur_r` at `femoral_offset`) and `tibia_bone` (to `tibia_r` at `(0, 0, 0)`) if `INCLUDE_BONES` is flipped to `True`.

### Check 5 — Required renders & measured render times: **PASS**
All 5 outputs were generated and visually inspected:

| Render | Engine / Mode | Path | Render time |
|---|---|---|---|
| Full-body walking (`walk_healthy`, `t = 10.00 s`) | Blender 5.2 `BLENDER_EEVEE` (1920x1080, 24 spp) | `cache\viewer\v3d_blender_walk_full\frame_0000.png` | **1.14 s/frame** |
| 60 deg sit-to-stand close-up (`sit_to_stand`, `t = 5.30 s`) | Blender 5.2 `BLENDER_EEVEE` `--closeup` (1920x1080, 24 spp) | `cache\viewer\v3d_blender_knee_flex60\frame_0000.png` | **1.26 s/frame** |
| Stairs-up full-body (`stairs_up`, `t = 6.00 s`) | Blender 5.2 `BLENDER_EEVEE` (1920x1080, 24 spp) | `cache\viewer\v3d_blender_stairs_up\frame_0000.png` | **1.19 s/frame** |
| MuJoCo walking (`walk_healthy`, `t = 10.00 s`) | MuJoCo offscreen + Matplotlib panel | `cache\viewer\v3d_mj_walk_healthy.png` | ~2.5 s (single composite) |
| MuJoCo sit-to-stand (`sit_to_stand`, `t = 5.40 s`) | MuJoCo offscreen + Matplotlib panel | `cache\viewer\v3d_mj_sit_to_stand.png` | ~2.5 s (single composite) |

(Warm Blender Eevee render speed is 1.14–1.26 s/frame at 1920x1080, 24 samples; first cold run after shader compilation took 4.42 s.)

## 5. Problems and open questions
- **Close-up thigh/shin overlap seam**: because the thigh and shank are two separate rigid bodies meeting at the knee, their spherical end-caps slightly intersect inside the joint in extreme flexion (faint curved boundary visible inside the glass skin in `v3d_blender_knee_flex60\frame_0000.png`). `use_backface_culling=True` and `use_transparency_overlap=False` keep this subtle and artifact-free; a skinned/armature-deformed single-mesh leg could eliminate it completely if ever desired, at higher rigging complexity.
- **README note for manager**: once approved, `viewer/README.md` can note that the right leg renders as a closed see-through shell around the 3-part implant CAD and that bones (`Body46`/`Body32`) are controlled by `INCLUDE_BONES` in `viewer/implant_cad.py`.
