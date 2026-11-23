"""
Export a KNEIL MuJoCo motion (per-frame body poses, implant triad, scene objects,
and V4 forest decisions) to a JSON file for Blender rendering.
   export_motion 1.0, 23 Nov 2026

Usage:
    python viewer/export_motion.py walk_healthy --fps 25 --max-s 3.0
    python viewer/export_motion.py walk_fast --t0 8.0 --max-s 2.5 --out cache/viewer/blender_walk_fast.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import mujoco

VIEWER_DIR = os.path.dirname(os.path.abspath(__file__))
if VIEWER_DIR not in sys.path:
    sys.path.insert(0, VIEWER_DIR)

import kneil_viewer as KV

VERSION = 'export_motion 1.0'
BODY_NAMES = ('pelvis', 'femur_r', 'tibia_r', 'femur_l', 'tibia_l')


def _r3(arr):
    return [round(float(x), 5) for x in arr]


def export_motion_json(motion_name, out_path=None, fps=25.0, t0=0.0, max_s=None):
    catalog = KV.build_catalog()
    entry = KV.resolve_motion_id(motion_name, catalog)
    data = KV.load_motion(entry)
    meta = data['meta']
    t_arr = data['t']
    dur = float(t_arr[-1])
    t_start = float(np.clip(t0, 0.0, max(0.0, dur - 0.1)))
    t_end = dur if max_s is None else min(dur, t_start + float(max_s))

    m = KV.add_camera_to_model(meta)
    d = mujoco.MjData(m)
    body_ids = {b: m.body(b).id for b in BODY_NAMES}
    imu_sid = m.site('imu').id

    ts = np.arange(t_start, t_end + 1e-6, 1.0 / fps)
    frames = []
    for tt in ts:
        fi = int(np.clip(round(tt * KV.FS_OUT), 0, len(t_arr) - 1))
        d.qpos[:] = data['Q'][fi]
        mujoco.mj_forward(m, d)

        bodies = {}
        for b, bid in body_ids.items():
            bodies[b] = dict(
                pos=_r3(d.xpos[bid]),
                quat=_r3(d.xquat[bid]),  # MuJoCo [w, x, y, z]
            )
        imu_pos = _r3(d.site_xpos[imu_sid])
        imu_mat = d.site_xmat[imu_sid].reshape(3, 3)
        imu_quat = np.zeros(4)
        mujoco.mju_mat2Quat(imu_quat, imu_mat.ravel())

        dec = KV.decision_at(data, float(tt))
        if dec is not None:
            cls_id = dec['rule_cls']
            cls_label = KV.CLASS_LABELS_V2[cls_id]
            cls_col = KV.CLASS_COLOURS_V2[cls_id]
            raw_label = KV.CLASS_LABELS_V2[dec['raw_cls']]
            vote_pct = int(round(dec['vote'] * 100.0))
            posture = KV.POSTURE_NAMES[dec['posture']]
        else:
            cls_id = -1
            cls_label = 'buffering'
            cls_col = KV.NONE_COLOUR
            raw_label = '-'
            vote_pct = 0
            posture = 'unknown'

        frames.append(dict(
            t=round(float(tt), 4),
            bodies=bodies,
            imu=dict(pos=imu_pos, quat=_r3(imu_quat)),
            decision=dict(
                cls=cls_id, label=cls_label, colour=cls_col,
                raw=raw_label, vote_pct=vote_pct, posture=posture,
            ),
        ))

    if out_path is None:
        os.makedirs(KV.CACHE_DIR, exist_ok=True)
        out_path = os.path.join(KV.CACHE_DIR, f'blender_{entry["id"]}.json')

    payload = dict(
        version=VERSION,
        motion_id=entry['id'],
        name=meta['name'],
        source=meta['source'],
        fps=float(fps),
        t_start=t_start,
        t_end=t_end,
        n_frames=len(frames),
        geom=meta['geom'],
        env=meta.get('env', dict(type='floor', floor=0.0)),
        frames=frames,
    )
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f)
    KV.log_msg(f'Exported {entry["id"]} ({len(frames)} frames @ {fps} fps) -> {out_path}')
    return out_path, len(frames)


def main():
    print(VERSION, flush=True)
    ap = argparse.ArgumentParser(description='Export KNEIL MuJoCo motion poses to JSON for Blender')
    ap.add_argument('motion', help='motion id or alias')
    ap.add_argument('--fps', type=float, default=25.0, help='export frame rate (default 25)')
    ap.add_argument('--t0', type=float, default=0.0, help='start time in seconds')
    ap.add_argument('--max-s', type=float, default=None, help='max duration in seconds')
    ap.add_argument('--out', help='output JSON path (default cache/viewer/blender_<id>.json)')
    args = ap.parse_args()
    t0 = time.time()
    outp, nf = export_motion_json(args.motion, out_path=args.out, fps=args.fps, t0=args.t0, max_s=args.max_s)
    print(f'Exported {nf} frames to {outp} in {time.time() - t0:.2f} s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
