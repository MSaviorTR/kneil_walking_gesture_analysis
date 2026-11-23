"""
Load and align the owner's knee implant CAD (j_a_j_model.obj: Body31 femoral,
Body23 spacer, Body25 tibial) for the MuJoCo viewer and Blender renderer.
   implant_cad 1.0, 23 Nov 2026

Read-only on the owner's OBJ in sims_html; converted meshes are written ONLY
under cache/viewer/cad/ (git-ignored; never committed).

Usage:
    python viewer/implant_cad.py --prepare
    python viewer/implant_cad.py --check-clearance
"""
import argparse
import json
import os
import struct
import sys
import time

import numpy as np
import mujoco

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_DIR = os.path.join(REPO_ROOT, 'pipeline')
VIEWER_DIR = os.path.join(REPO_ROOT, 'viewer')
for d in (PIPELINE_DIR, VIEWER_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import config
import kneil_v1 as K

VERSION = 'implant_cad 1.1'
CAD_OBJ_PATH = r'C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\sims_html\j_a_j_model.obj'
CAD_CACHE_DIR = os.path.join(config.CACHE, 'viewer', 'cad')

# Implant parts always loaded; bone groups (Body46 / Body32) stay off until owner enables INCLUDE_BONES
INCLUDE_BONES = False
CAD_PARTS = {
    'femoral': 'Body31',
    'spacer': 'Body23',
    'tibial': 'Body25',
}
BONE_PARTS = {
    'femur_bone': 'Body46',
    'tibia_bone': 'Body32',
}


def active_parts(include_bones=INCLUDE_BONES):
    parts = dict(CAD_PARTS)
    if include_bones:
        parts.update(BONE_PARTS)
    return parts

# CAD (cm) -> MuJoCo body-local (m):
# From geometry:
#   - Anterior flange (Body31 Z > 4.5 cm) sits at Y_cad in [-1.97, -0.72] cm (Y_med = -1.15 cm),
#     and posterior intercondylar notch + tibial tray PCL notch sit at Y_cad > 0 -> Anterior = -Y_cad.
#   - Body23/Body25 are symmetric around X_cad = 0; lateral trochlear ridge is wider on +X_cad -> Right = +X_cad.
#   - Superior = +Z_cad.
# Pure right-handed rotation (det = +1):
#   X_m (anterior) = -Y_cad,  Y_m (superior) = +Z_cad,  Z_m (right) = +X_cad.
R_CAD_TO_MJ = np.array([
    [0.0, -1.0, 0.0],
    [0.0,  0.0, 1.0],
    [1.0,  0.0, 0.0],
], dtype=np.float64)

# Knee joint centre (OpenSim Gait2354 femoral epicondylar flexion axis) in CAD cm:
#   X = 0.00 cm (ML symmetry plane; tibial stem X_med = -0.07 cm)
#   Y = +1.40 cm (posterior-condylar flexion axis; matched to OpenSim knee_tx/knee_ty spline over 0..100 deg)
#   Z = +3.00 cm (2.76 cm above distal condyles Z_min=0.24 cm; puts the tibial insert Body23 right at
#                 Y_tibia = -3.47..-1.02 cm, containing the KNEIL implant point at Y_tibia = -2.5 cm!)
CAD_ORIGIN_CM = np.array([0.0, 1.40, 3.00], dtype=np.float64)


def cad_available():
    return os.path.exists(CAD_OBJ_PATH)


def parse_obj_groups(obj_path=CAD_OBJ_PATH, include_bones=INCLUDE_BONES):
    """Parse OBJ vertices and triangulated faces by group name."""
    verts = []
    groups = {}
    cur_g = 'default'
    with open(obj_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('v '):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith('g ') or line.startswith('o '):
                cur_g = line.split()[1].strip()
                groups.setdefault(cur_g, [])
            elif line.startswith('f '):
                toks = line.split()[1:]
                idx = [int(t.split('/')[0]) - 1 for t in toks]
                for k in range(1, len(idx) - 1):
                    groups.setdefault(cur_g, []).append((idx[0], idx[k], idx[k + 1]))
    V = np.asarray(verts, dtype=np.float64)
    out = {}
    for name, grp in active_parts(include_bones=include_bones).items():
        T = np.asarray(groups[grp], dtype=np.int32)
        uniq, inv = np.unique(T, return_inverse=True)
        out[name] = (V[uniq].copy(), inv.reshape(-1, 3).astype(np.int32))
    return out


def transform_cad_to_mj(V_cm, offset_m=(0.0, 0.0, 0.0)):
    """Convert CAD cm vertices to MuJoCo body-local metres around CAD_ORIGIN_CM + offset_m."""
    V_m = (V_cm - CAD_ORIGIN_CM[None, :]) * 0.01
    return V_m @ R_CAD_TO_MJ.T + np.asarray(offset_m, dtype=np.float64)[None, :]


def decimate_vertex_cluster(V, F, voxel_m=0.0022):
    """Simple, dependency-free grid vertex clustering decimation (preserves watertight shape)."""
    grid = np.floor(V / voxel_m).astype(np.int64)
    uniq, inv = np.unique(grid, axis=0, return_inverse=True)
    # Average vertex positions per cell
    n_u = len(uniq)
    V_new = np.zeros((n_u, 3), dtype=np.float64)
    counts = np.bincount(inv, minlength=n_u)
    for k in range(3):
        V_new[:, k] = np.bincount(inv, weights=V[:, k], minlength=n_u) / np.maximum(counts, 1)
    F_new = inv[F]
    # Drop degenerate triangles (two vertices in same cluster)
    keep = (F_new[:, 0] != F_new[:, 1]) & (F_new[:, 1] != F_new[:, 2]) & (F_new[:, 2] != F_new[:, 0])
    F_new = F_new[keep]
    # Deduplicate identical triangles
    F_sorted = np.sort(F_new, axis=1)
    _, keep_u = np.unique(F_sorted, axis=0, return_index=True)
    F_new = F_new[np.sort(keep_u)]
    return V_new, F_new.astype(np.int32)


def write_binary_stl(path, V, F):
    """Write binary STL (MuJoCo's native fast mesh format)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tris = V[F].astype(np.float32)  # (M, 3, 3)
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    n = np.cross(e1, e2)
    nl = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, np.maximum(nl, 1e-12))
    with open(path, 'wb') as f:
        f.write(b'KNEIL CAD converted mesh (cache only)'.ljust(80, b' '))
        f.write(struct.pack('<I', len(tris)))
        buf = np.zeros((len(tris), 12), dtype=np.float32)
        buf[:, 0:3] = n
        buf[:, 3:6] = tris[:, 0]
        buf[:, 6:9] = tris[:, 1]
        buf[:, 9:12] = tris[:, 2]
        # Pack with 2-byte attribute count = 0
        rec = np.zeros(len(tris), dtype=[('data', '<f4', 12), ('attr', '<u2')])
        rec['data'] = buf
        f.write(rec.tobytes())


def write_obj(path, V, F):
    """Write simple OBJ (for Blender import in body-local coordinates)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# {VERSION} cache-only mesh (do not commit)\n')
        for v in V:
            f.write(f'v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n')
        for tri in F:
            f.write(f'f {tri[0]+1} {tri[1]+1} {tri[2]+1}\n')


def knee_standing_offset(osim=None, femur=K.REF['femur']):
    """Exact (knee_tx_r(0), knee_ty_r(0), 0) of tibia_r relative to femur_r at knee_angle = 0."""
    if osim is None:
        osim = K.read_osim(K.fetch('osim', folder=config.OPENSIM_DIR))
    kf = float(femur) / K.REF['femur']
    tx0 = float(kf * osim['knee_1_r'](0.0))
    ty0 = float(kf * osim['knee_2_r'](0.0))
    return np.array([tx0, ty0, 0.0], dtype=np.float64)


def prepare_cad_meshes(force=False, decimate_voxel_m=0.0022, include_bones=INCLUDE_BONES):
    """Build cached full-res OBJ (for Blender) and decimated STL (for MuJoCo) under cache/viewer/cad/.
    Note: femoral mesh is centered at the knee joint centre (0, 0, 0); callers place it at
    pos="(knee_tx_0, knee_ty_0, 0)" on femur_r so it scales cleanly with any subject's femur length!"""
    os.makedirs(CAD_CACHE_DIR, exist_ok=True)
    meta_path = os.path.join(CAD_CACHE_DIR, 'cad_meta.json')
    if not force and os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        if (meta.get('version') == VERSION
                and bool(meta.get('include_bones', False)) == bool(include_bones)
                and all(os.path.exists(p) for p in meta['stl'].values())):
            return meta

    if not cad_available():
        raise FileNotFoundError(f'Owner CAD OBJ not found: {CAD_OBJ_PATH}')

    parts = parse_obj_groups(CAD_OBJ_PATH, include_bones=include_bones)
    meta = dict(
        version=VERSION,
        include_bones=bool(include_bones),
        source_obj=CAD_OBJ_PATH,
        cad_origin_cm=CAD_ORIGIN_CM.tolist(),
        R_cad_to_mj=R_CAD_TO_MJ.tolist(),
        stl={}, obj={}, full_faces={}, dec_faces={}, bounds_m={},
    )
    for name, (V_cm, F) in parts.items():
        V_m = transform_cad_to_mj(V_cm)
        obj_p = os.path.join(CAD_CACHE_DIR, f'{name}_full.obj')
        write_obj(obj_p, V_m, F)

        V_dec, F_dec = decimate_vertex_cluster(V_m, F, voxel_m=decimate_voxel_m)
        stl_p = os.path.join(CAD_CACHE_DIR, f'{name}_mj.stl')
        write_binary_stl(stl_p, V_dec, F_dec)

        meta['obj'][name] = obj_p
        meta['stl'][name] = stl_p
        meta['full_faces'][name] = int(len(F))
        meta['dec_faces'][name] = int(len(F_dec))
        meta['bounds_m'][name] = dict(
            min=[round(float(x), 4) for x in V_m.min(0)],
            max=[round(float(x), 4) for x in V_m.max(0)],
        )

    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    return meta


def check_femoral_spacer_clearance(motion_ids=('walk_healthy', 'sit_to_stand')):
    """Check 5: measure vertical interpenetration (negative) or gap (positive) in mm between
    the femoral component (on femur_r) and the spacer articular dish (on tibia_r) over
    each motion. Evaluates in tibia_r local frame so vertical = superior (+Y_tibia)."""
    import kneil_viewer as KV

    parts = parse_obj_groups(CAD_OBJ_PATH)
    V_fem_local = transform_cad_to_mj(parts['femoral'][0])   # relative to knee centre at 0 deg
    V_sp_local = transform_cad_to_mj(parts['spacer'][0])     # in tibia_r local frame

    # Build a 2D heightmap of the spacer top surface (Y_tibia vs X_tibia, Z_tibia) on a 2 mm grid
    res = 0.002
    x_min, z_min = V_sp_local[:, 0].min(), V_sp_local[:, 2].min()
    x_max, z_max = V_sp_local[:, 0].max(), V_sp_local[:, 2].max()
    nx = int(np.ceil((x_max - x_min) / res)) + 1
    nz = int(np.ceil((z_max - z_min) / res)) + 1
    sp_top = np.full((nx, nz), -np.inf)
    ix = np.clip(((V_sp_local[:, 0] - x_min) / res).astype(int), 0, nx - 1)
    iz = np.clip(((V_sp_local[:, 2] - z_min) / res).astype(int), 0, nz - 1)
    np.maximum.at(sp_top, (ix, iz), V_sp_local[:, 1])

    # Condylar contact region: |Z_tibia| in [0.010, 0.032] m (excludes the central PS post!)
    V_fem_cond = V_fem_local[(np.abs(V_fem_local[:, 2]) >= 0.010) & (np.abs(V_fem_local[:, 2]) <= 0.032)]
    # Subsample femoral condyle vertices for speed (~1200 pts)
    if len(V_fem_cond) > 1200:
        V_fem_cond = V_fem_cond[::max(1, len(V_fem_cond) // 1200)]

    cat = KV.build_catalog()
    osim = KV.get_osim()
    results = {}
    for mid in motion_ids:
        entry = KV.resolve_motion_id(mid, cat)
        data = KV.load_motion(entry)
        geom = data['meta']['geom']
        m, _ = K.build_model(osim, femur=float(geom['femur']), tibia=float(geom['tibia']),
                             pelvis=float(geom['pelvis']), imu_side=geom.get('imu_side', 'r'))
        d = mujoco.MjData(m)
        bid_f = m.body('femur_r').id
        bid_t = m.body('tibia_r').id
        k_off = knee_standing_offset(osim, femur=float(geom['femur']))
        idx = K.qidx(m)
        ka_i = idx['knee_angle_r']

        clearances_mm = []
        angles_deg = []
        # Check every 2nd frame (25 Hz)
        for q in data['Q'][::2]:
            d.qpos[:] = q
            mujoco.mj_kinematics(m, d)
            Rf = d.xmat[bid_f].reshape(3, 3)
            pf = d.xpos[bid_f]
            Rt = d.xmat[bid_t].reshape(3, 3)
            pt = d.xpos[bid_t]

            # Femoral condyle vertices -> world -> tibia_r local frame
            P_w = (V_fem_cond + k_off[None, :]) @ Rf.T + pf[None, :]
            P_t = (P_w - pt[None, :]) @ Rt  # Rt^T @ (P_w - pt)

            # Look up spacer top surface directly under each condyle vertex
            gx = np.floor((P_t[:, 0] - x_min) / res).astype(int)
            gz = np.floor((P_t[:, 2] - z_min) / res).astype(int)
            inb = (gx >= 0) & (gx < nx) & (gz >= 0) & (gz < nz)
            if not inb.any():
                continue
            sy = sp_top[gx[inb], gz[inb]]
            valid = np.isfinite(sy)
            if not valid.any():
                continue
            # Minimum vertical distance (femoral_y - spacer_top_y): negative = overlap, positive = gap
            diff_mm = float((P_t[inb, 1][valid] - sy[valid]).min()) * 1000.0
            clearances_mm.append(diff_mm)
            angles_deg.append(float(-np.degrees(q[ka_i])))

        c = np.array(clearances_mm)
        ang = np.array(angles_deg)
        res_m = dict(
            motion_id=entry['id'],
            n_frames=len(c),
            knee_flex_min_deg=round(float(ang.min()), 1),
            knee_flex_max_deg=round(float(ang.max()), 1),
            standing_clearance_mm=round(float(c[np.argmin(ang)]), 2),
            max_overlap_mm=round(float(max(0.0, -c.min())), 2),
            max_gap_mm=round(float(max(0.0, c.max())), 2),
            median_mm=round(float(np.median(c)), 2),
            p05_mm=round(float(np.percentile(c, 5)), 2),
            p95_mm=round(float(np.percentile(c, 95)), 2),
        )
        results[entry['id']] = res_m
        print(f'  {entry["id"]:26s} | flex {res_m["knee_flex_min_deg"]:4.1f}..{res_m["knee_flex_max_deg"]:4.1f} deg | '
              f'at min flex: {res_m["standing_clearance_mm"]:+5.2f} mm | '
              f'max overlap: {res_m["max_overlap_mm"]:4.2f} mm | max gap: {res_m["max_gap_mm"]:4.2f} mm | '
              f'med: {res_m["median_mm"]:+5.2f} mm')
    return results


def main():
    print(VERSION, flush=True)
    ap = argparse.ArgumentParser(description='Prepare KNEIL implant CAD meshes (cache only) and check clearance')
    ap.add_argument('--prepare', action='store_true', help='convert and decimate CAD meshes into cache/viewer/cad/')
    ap.add_argument('--force', action='store_true', help='rebuild cached meshes')
    ap.add_argument('--check-clearance', action='store_true', help='check femoral-spacer overlap/gap on walk & sit-to-stand')
    args = ap.parse_args()

    if args.prepare or not args.check_clearance:
        t0 = time.time()
        meta = prepare_cad_meshes(force=args.force)
        print(f'Prepared CAD meshes in {time.time() - t0:.2f} s -> {CAD_CACHE_DIR}')
        for name in ('femoral', 'spacer', 'tibial'):
            print(f'  {name:8s}: full={meta["full_faces"][name]:5d} tris -> MuJoCo={meta["dec_faces"][name]:4d} tris | '
                  f'bounds X=[{meta["bounds_m"][name]["min"][0]:+.3f},{meta["bounds_m"][name]["max"][0]:+.3f}] '
                  f'Y=[{meta["bounds_m"][name]["min"][1]:+.3f},{meta["bounds_m"][name]["max"][1]:+.3f}] '
                  f'Z=[{meta["bounds_m"][name]["min"][2]:+.3f},{meta["bounds_m"][name]["max"][2]:+.3f}] m')
    if args.check_clearance:
        print('\nFemoral-to-spacer vertical clearance (condylar contact patch, excluding central PS post):')
        check_femoral_spacer_clearance()
    return 0


if __name__ == '__main__':
    sys.exit(main())
