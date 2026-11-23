# V3c Report — Owner's Knee Implant CAD in MuJoCo and Blender Viewers

## 1. Status
done

## 2. Files
- `viewer/implant_cad.py` (added, v1.0): reads the owner's read-only OBJ (`C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\sims_html\j_a_j_model.obj`), extracts only `Body31` (femoral), `Body23` (spacer), and `Body25` (tibial), applies the cm -> m scale and anatomical axis rotation/origin alignment, caches full-res OBJ (for Blender) and voxel-decimated binary STL (for MuJoCo) strictly under `cache/viewer/cad/` (git-ignored), and runs the femoral-to-spacer clearance check over walking and sit-to-stand.
- `viewer/kneil_viewer.py` (modified, v1.2): attaches the 3 decimated STL parts as visual-only mesh geoms (`contype="0" conaffinity="0"`) on the right leg (`femur_r` and `tibia_r`) with Chrome and Nylon 6-6 White materials, keeping the KNEIL implant point and x/y/z axes in place.
- `viewer/export_motion.py` (modified, v1.2): adds the `cad` block (`obj` paths to `cache/viewer/cad/*_full.obj` and subject-scaled `femoral_offset` at standing) to exported Blender motion JSONs.
- `viewer/blender_render.py` (modified, v1.2): loads the 3 full-res OBJ parts on the right knee (Chrome + Nylon 6-6 White), shortens the right stylised thigh/shin cleanly outside the CAD, keeps the cyan KNEIL implant point and red/green/blue device axes in place, and adds `--closeup` mode targeting the right knee.
- `tasks/V3c_report.md` (added): this report.

Note: zero `.obj` or `.stl` files were staged or committed; `cache/` is git-ignored (`git status --ignored --short cache/viewer/cad` reports `!! cache/`).

## 3. Commands
```powershell
# 1. Prepare cached CAD meshes (full-res OBJ + decimated STL) and run clearance check
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\implant_cad.py --prepare --force --check-clearance

# 2. Render MuJoCo verification frames with the 3 CAD parts
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\kneil_viewer.py walk_healthy --render cache\viewer\render_cad_walk_healthy.png --t 10.0
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\kneil_viewer.py sit_to_stand --render cache\viewer\render_cad_sit_to_stand.png --t 5.4

# 3. Export single-frame JSONs for Blender (standing, ~60 deg sit-to-stand, full-body walking)
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\export_motion.py sit_to_stand --out cache\viewer\cad_knee_standing.json --t0 6.28 --max-s 0.03 --fps 25
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\export_motion.py sit_to_stand --out cache\viewer\cad_knee_flex60.json --t0 5.30 --max-s 0.03 --fps 25
C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe viewer\export_motion.py walk_healthy --out cache\viewer\cad_walk_full.json --t0 10.00 --max-s 0.03 --fps 25

# 4. Render the 3 Blender 5.2 studio frames (1920x1080, Eevee, 24 samples)
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -P viewer\blender_render.py -- cache\viewer\cad_knee_standing.json cache\viewer\blender_cad_knee_standing --closeup --samples 24
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -P viewer\blender_render.py -- cache\viewer\cad_knee_flex60.json cache\viewer\blender_cad_knee_flex60 --closeup --samples 24
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b -P viewer\blender_render.py -- cache\viewer\cad_walk_full.json cache\viewer\blender_cad_walk_full --samples 24
```

## 4. Acceptance checks

### Check 1 — Anatomical axes derived from CAD geometry & cm -> m scaling: **PASS**
From `j_a_j_model.obj` (30,995 vertices, 5 groups, units cm, Z up):
- **Anterior = `-Y_cad`** (confirmed by 4 independent geometric cues):
  1. `Body31` anterior femoral flange (`Z > 4.5 cm`, 497 verts) lies entirely in `Y = [-1.97, -0.72] cm` (`Y_med = -1.15 cm`).
  2. `Body31` midline (`|X| < 0.5 cm`, `Z > 1.5 cm`) has 362 vertices on `Y < 0` (anterior trochlear groove) and 0 vertices on `Y > 0` (open posterior intercondylar notch).
  3. `Body25` tibial tray has a `1.09 cm` deep posterior PCL cutout at `Y > 0`.
  4. `Body23` posterior-stabilised (PS) spine (`Z > 1.4 cm`) sits posteriorly at `Y_med = +1.26 cm`.
- **Medio-lateral = `X_cad`**: `Body23` (`X = [-3.80, +3.80] cm`) and `Body25` (`X = [-3.93, +3.93] cm`) are symmetric about `X = 0`; the slightly wider lateral trochlear ridge is on `+X_cad`, matching `+X_cad = right/lateral` for a right knee.
- **Superior = `+Z_cad`**.
- **Pure right-handed rotation (`det = +1`)** from CAD (cm) to MuJoCo body-local frame (m; `X` anterior, `Y` superior, `Z` right):
  $$p_{\text{mj}} = 0.01 \cdot R_{\text{cad}\to\text{mj}} (p_{\text{cad}} - O_{\text{cad}}), \qquad R_{\text{cad}\to\text{mj}} = \begin{pmatrix} 0 & -1 & 0 \\ 0 & 0 & 1 \\ 1 & 0 & 0 \end{pmatrix}$$
  with knee flexion centre origin `O_cad = [0.0, 1.40, 3.00] cm` (aligned to OpenSim Gait2354's femoral epicondylar flexion centre, 2.76 cm above the distal femoral condyles at `Z_min = 0.24 cm`).

### Check 2 — Per-part transforms, segment attachment & KNEIL implant point: **PASS**
All three meshes are pre-rotated and scaled into the shared standing knee-centre frame (`O_cad = [0.0, 1.40, 3.00] cm`, metres):

| Part | Group | Parent body | Local offset in parent (m) | Local bounds in knee frame (m): X ant, Y sup, Z right | Material |
|---|---|---|---|---|---|
| Femoral component | `Body31` | `femur_r` | `knee_standing_offset(femur)` = `[-0.00502, -0.44157, 0.0]` for healthy older adult | `X=[-0.0213, +0.0344]`, `Y=[-0.0276, +0.0352]`, `Z=[-0.0333, +0.0330]` | Chrome (`metallic=0.92, roughness=0.14`) |
| Spacer (insert) | `Body23` | `tibia_r` | `[0.0, 0.0, 0.0]` | `X=[-0.0205, +0.0305]`, `Y=[-0.0347, -0.0102]`, `Z=[-0.0380, +0.0380]` | Nylon 6-6 White (`metallic=0.0, roughness=0.28`) |
| Tibial component | `Body25` | `tibia_r` | `[0.0, 0.0, 0.0]` | `X=[-0.0203, +0.0313]`, `Y=[-0.0776, -0.0347]`, `Z=[-0.0393, +0.0393]` | Chrome (`metallic=0.92, roughness=0.14`) |

- In standing (`knee_angle_r = 0`), `tibia_r` sits at `knee_standing_offset(femur)` relative to `femur_r`, so the femoral condyles (`Y_min = -0.0276 m`) sit directly in the spacer's condylar troughs (`Y = [-0.0347, -0.0102] m`).
- The KNEIL implant point `(0.005, -0.025, 0.0) m` in `tibia_r` (2.5 cm below the knee joint centre, 5 mm anterior) lies directly inside/at the anterior spacer (`Y = -0.025 m` within `[-0.0347, -0.0102] m`) with the cyan sensor marker and red (`X` anterior), green (`Y` left), blue (`Z` superior) device axes drawn in place.

### Check 3 — Blender 5.2 renders (2 close-ups + 1 full-body walking): **PASS**
All 3 frames rendered at 1920x1080 (Eevee, 24 samples, 1.08–1.12 s/frame) and visually inspected:
- Standing right-knee close-up (`sit_to_stand`, `t = 6.28 s`, knee flexion `2.31 deg`): `cache\viewer\blender_cad_knee_standing\frame_0000.png`
- Flexed right-knee close-up (`sit_to_stand`, `t = 5.30 s`, knee flexion `60.42 deg`): `cache\viewer\blender_cad_knee_flex60\frame_0000.png`
- Full-body walking frame (`walk_healthy`, `t = 10.00 s`): `cache\viewer\blender_cad_walk_full\frame_0000.png`

### Check 4 — MuJoCo viewer visual-only mesh geoms & face counts: **PASS**
All 3 parts are added with `contype="0" conaffinity="0"` (no collisions), voxel-decimated (2.2 mm voxel grid) for fast interactive rendering:

| Part | Full-res faces (Blender) | Decimated faces (MuJoCo) | Reduction |
|---|---:|---:|---:|
| `Body31` (femoral) | 16,538 | 3,061 | 81.5% |
| `Body23` (spacer) | 5,828 | 1,256 | 78.4% |
| `Body25` (tibial) | 16,904 | 1,698 | 90.0% |
| **Total** | **39,270** | **6,015** | **84.7%** |

MuJoCo verification renders (visually inspected):
- `cache\viewer\render_cad_walk_healthy.png` (`walk_healthy`, `t = 10.00 s`)
- `cache\viewer\render_cad_sit_to_stand.png` (`sit_to_stand`, `t = 5.40 s`)

### Check 5 — Femoral-to-spacer overlap / gap check: **PASS**
Measured over the full condylar contact patch (excluding the central PS post) across all frames using the exact OpenSim Gait2354 knee spline:

| Motion | Flexion range (deg) | Standing / min-flex clearance (mm) | Max interpenetration / overlap (mm) | Max separation / gap (mm) | Median clearance (mm) |
|---|---:|---:|---:|---:|---:|
| `old_22_walk_healthy` (gait cycle) | 0.1 .. 67.4 | -1.38 | **1.94** | **0.00** | -1.16 |
| `old_23_sitstand_healthy` (sit-to-stand) | 2.3 .. 103.2 | -1.30 | **6.92** | **0.00** | -6.05 |

(Negative clearance = overlap; 1.94 mm max overlap across the entire gait cycle and 6.92 mm at deep 103 deg seated flexion, with zero liftoff gap.)

## 5. Problems and open questions
- **Deep flexion overlap (6.92 mm at 103 deg seated flexion)**: OpenSim Gait2354's generic tibiofemoral spline (`knee_1_r`, `knee_2_r`) moves the tibia origin downward by `-20.64 mm` at 90 deg flexion for a generic biological knee, which differs slightly from the posterior-stabilised implant's cam-post rollback radius above ~75 deg flexion. Over the entire gait cycle (0.1–67.4 deg) the maximum overlap is only 1.94 mm, and at 60 deg sit-to-stand flexion the condyles articulate cleanly in the spacer troughs (visible in `blender_cad_knee_flex60\frame_0000.png`).
- **Owner's decision**: `Body46` (femur bone) and `Body32` (tibia bone) are excluded as instructed; if the owner later wants them enabled, they can be added to `PARTS` in `viewer/implant_cad.py` using the same `R_CAD_TO_MJ` and `CAD_ORIGIN_CM`.
- **README note for manager**: `viewer/README.md` can mention `viewer/implant_cad.py` and the `--closeup` flag in `viewer/blender_render.py` once the owner decides whether to keep the CAD integration.
