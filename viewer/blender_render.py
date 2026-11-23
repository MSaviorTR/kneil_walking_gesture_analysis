"""
Headless Blender studio renderer for KNEIL MuJoCo motion JSONs (Eevee, 1920x1080).
   blender_render 1.1, 23 Nov 2026

Uses only Blender's built-in Python (bpy, mathutils); no add-ons or external assets.
Note: arms are decorative (driven opposite to measured hip flexion) and not measured.

Usage:
    blender.exe -b -P viewer/blender_render.py -- <motion.json> <out_dir> [--step 1] [--samples 16]
"""
import json
import math
import os
import sys
import time

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

VERSION = 'blender_render 1.1'

# Coordinate transform: MuJoCo Y-up (X ant, Y up, Z right) -> Blender Z-up (X ant, Y left, Z up)
R_M2B = Matrix(((1.0, 0.0, 0.0),
                (0.0, 0.0, -1.0),
                (0.0, 1.0, 0.0)))
Q_M2B = R_M2B.to_quaternion()


def m2b_pos(p):
    return Vector((float(p[0]), -float(p[2]), float(p[1])))


def m2b_quat(q_wxyz):
    qm = Quaternion((float(q_wxyz[0]), float(q_wxyz[1]), float(q_wxyz[2]), float(q_wxyz[3])))
    return Q_M2B @ qm


def hex_to_rgba(h, alpha=1.0):
    h = h.lstrip('#')
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    return (r ** 2.2, g ** 2.2, b ** 2.2, alpha)


def make_mat(name, rgba, roughness=0.45, metallic=0.0, emission=0.0):
    mat = bpy.data.materials.new(name=name)
    bsdf = mat.node_tree.nodes.get('Principled BSDF') if mat.node_tree else None
    if bsdf:
        bsdf.inputs['Base Color'].default_value = rgba
        bsdf.inputs['Roughness'].default_value = roughness
        bsdf.inputs['Metallic'].default_value = metallic
        if emission > 0.0 and 'Emission Strength' in bsdf.inputs:
            bsdf.inputs['Emission Color'].default_value = rgba
            bsdf.inputs['Emission Strength'].default_value = emission
    return mat


def set_smooth(obj):
    if obj.type == 'MESH' and obj.data:
        for p in obj.data.polygons:
            p.use_smooth = True


def add_tapered_limb(name, p0, p1, r0, r1, mat, parent=None):
    """Add a smooth tapered limb (cone frustum + two sphere end-caps) from p0 to p1."""
    v0, v1 = Vector(p0), Vector(p1)
    dv = v1 - v0
    length = dv.length
    mid = 0.5 * (v0 + v1)
    rot = Vector((0, 0, 1)).rotation_difference(dv.normalized()) if length > 1e-6 else Quaternion()

    bpy.ops.mesh.primitive_cone_add(vertices=28, radius1=r0, radius2=r1, depth=max(length, 1e-4), location=mid)
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = rot
    obj.data.materials.append(mat)
    set_smooth(obj)
    if parent is not None:
        obj.parent = parent

    for k, (pt, rad) in enumerate(((v0, r0), (v1, r1))):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=rad, location=pt)
        sp = bpy.context.active_object
        sp.name = f'{name}_cap{k}'
        sp.data.materials.append(mat)
        set_smooth(sp)
        if parent is not None:
            sp.parent = parent
    return obj


def add_capsule(name, p0, p1, radius, mat, parent=None):
    return add_tapered_limb(name, p0, p1, radius, radius, mat, parent=parent)


def add_box(name, center, half_extents, mat, euler=(0, 0, 0), parent=None):
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=center)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = half_extents
    obj.rotation_euler = euler
    obj.data.materials.append(mat)
    if parent is not None:
        obj.parent = parent
    return obj


def build_env_scene(env):
    etype = env.get('type', 'floor')
    fy = float(env.get('floor', 0.0))

    mat_floor = make_mat('Floor', (0.78, 0.80, 0.83, 1.0), roughness=0.65)
    mat_wood = make_mat('Wood', (0.34, 0.21, 0.12, 1.0), roughness=0.50)
    mat_stair = make_mat('Stairs', (0.50, 0.53, 0.58, 1.0), roughness=0.55)
    mat_metal = make_mat('Metal', (0.28, 0.30, 0.34, 1.0), roughness=0.30, metallic=0.6)
    mat_ramp = make_mat('Ramp', (0.36, 0.48, 0.46, 1.0), roughness=0.52)
    mat_bed = make_mat('Mattress', (0.82, 0.85, 0.90, 1.0), roughness=0.75)

    bpy.ops.mesh.primitive_plane_add(size=50.0, location=(0.0, 0.0, fy))
    fl = bpy.context.active_object
    fl.name = 'StudioFloor'
    fl.data.materials.append(mat_floor)

    if etype == 'chair':
        seat = float(env.get('seat', 0.45))
        front = float(env.get('front', 0.0))
        d, w, th = 0.44, 0.46, 0.04
        cx = front - d / 2.0
        add_box('ChairSeat', m2b_pos((cx, seat - th / 2, 0)), (d / 2, w / 2, th / 2), mat_wood)
        add_box('ChairBack', m2b_pos((front - d + 0.02, seat + 0.24, 0)), (0.02, w / 2, 0.24), mat_wood)
        for sx in (front - 0.03, front - d + 0.03):
            for sz in (-w / 2 + 0.03, w / 2 - 0.03):
                add_capsule('ChairLeg', m2b_pos((sx, fy, sz)), m2b_pos((sx, seat - th, sz)), 0.018, mat_wood)
    elif etype == 'stairs':
        treads = env.get('treads')
        w = 0.55
        if treads:
            for i, (xa, xb, y) in enumerate(treads):
                cx = 0.5 * (xa + xb)
                hx = max(abs(xb - xa) * 0.5, 0.05)
                h = max(y - fy, 0.04)
                add_box(f'Step_{i}', m2b_pos((cx, fy + h / 2, 0)), (hx, w, h / 2), mat_stair)
            if len(treads) >= 2:
                xa0, _, y0 = treads[0]
                _, xb1, y1 = treads[-1]
                add_capsule('Handrail', m2b_pos((xa0, y0 + 0.9, -w)), m2b_pos((xb1, y1 + 0.9, -w)), 0.02, mat_metal)
    elif etype == 'ramp':
        x_lo, x_hi = float(env.get('x_lo', -1.5)), float(env.get('x_hi', 2.5))
        y_lo, y_hi = float(env.get('y_lo', fy)), float(env.get('y_hi', fy + 0.5))
        x_max = float(env.get('x_max', max(x_lo, x_hi) + 1.5))
        dx, dy = x_hi - x_lo, y_hi - y_lo
        length = math.hypot(dx, dy)
        ang = math.atan2(dy, dx)
        th = 0.04
        nx, ny = -math.sin(ang), math.cos(ang)
        cx = 0.5 * (x_lo + x_hi) - (th * 0.5) * nx
        cy = 0.5 * (y_lo + y_hi) - (th * 0.5) * ny
        add_box('RampDeck', m2b_pos((cx, cy, 0)), (length / 2, 0.65, th / 2), mat_ramp, euler=(0.0, -ang, 0.0))
        lx0, lx1 = (x_hi, max(x_max, x_hi + 1.2)) if x_hi > x_lo else (min(float(env.get('x_min', x_hi - 1.2)), x_hi - 1.2), x_hi)
        lh = max(y_hi - fy, 0.04)
        add_box('RampTop', m2b_pos((0.5 * (lx0 + lx1), fy + lh / 2, 0)), (0.5 * abs(lx1 - lx0), 0.65, lh / 2), mat_stair)
    elif etype == 'treadmill':
        add_box('TreadmillDeck', m2b_pos((0, fy - 0.04, 0)), (1.05, 0.36, 0.04), mat_metal)
        for sz in (-0.38, 0.38):
            add_capsule('TmRail', m2b_pos((-0.7, fy + 0.92, sz)), m2b_pos((0.8, fy + 0.92, sz)), 0.018, mat_metal)
    elif etype == 'bed':
        by = float(env.get('bed', 0.48))
        x0, x1, w = float(env.get('x0', -1.0)), float(env.get('x1', 1.2)), float(env.get('w', 0.50))
        cx, hx = 0.5 * (x0 + x1), 0.5 * abs(x1 - x0)
        add_box('BedMattress', m2b_pos((cx, by - 0.10, 0)), (hx, w, 0.10), mat_bed)
        add_box('BedFrame', m2b_pos((cx, fy + (by - 0.20) / 2, 0)), (hx + 0.03, w + 0.03, max(by - 0.20, 0.04) / 2), mat_wood)


def setup_studio_lighting():
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new('StudioWorld')
        bpy.context.scene.world = world
    bg = world.node_tree.nodes.get('Background') if world.node_tree else None
    if bg:
        bg.inputs[0].default_value = (0.88, 0.91, 0.95, 1.0)
        bg.inputs[1].default_value = 0.28

    bpy.ops.object.light_add(type='SUN', location=(3.0, -3.5, 5.0))
    sun = bpy.context.active_object
    sun.name = 'KeySun'
    sun.data.energy = 3.2
    sun.data.angle = math.radians(12.0)
    sun.rotation_euler = (math.radians(48), math.radians(10), math.radians(32))

    bpy.ops.object.light_add(type='AREA', location=(-2.8, 2.5, 2.6))
    fill = bpy.context.active_object
    fill.name = 'FillLight'
    fill.data.energy = 140.0
    fill.data.size = 3.5
    fill.rotation_euler = (math.radians(60), 0.0, math.radians(-140))

    bpy.ops.object.light_add(type='AREA', location=(-1.8, -2.5, 3.2))
    rim = bpy.context.active_object
    rim.name = 'RimLight'
    rim.data.energy = 160.0
    rim.data.size = 2.0
    rim.rotation_euler = (math.radians(52), 0.0, math.radians(-30))


def build_human_rig(geom):
    """Build human-proportioned smooth figure (pelvis, torso, shoulders, neck, head, decorative arms,
    slim tapered legs, visible articulating knee spacer + cyan implant chip on device tibia)."""
    femur = float(geom['femur'])
    tibia = float(geom['tibia'])
    pelvis = float(geom['pelvis'])
    imu_side = geom.get('imu_side', 'r')

    mat_body = make_mat('BodySlate', (0.22, 0.27, 0.35, 1.0), roughness=0.40)
    mat_arm = make_mat('ArmSlate', (0.30, 0.35, 0.43, 1.0), roughness=0.45)
    mat_dev_leg = make_mat('DeviceLeg', (0.09, 0.32, 0.50, 1.0), roughness=0.35)
    mat_joint = make_mat('JointSilver', (0.70, 0.74, 0.80, 1.0), roughness=0.25, metallic=0.35)
    mat_spacer = make_mat('KneeSpacer', (0.93, 0.95, 0.98, 1.0), roughness=0.14, metallic=0.25)
    mat_fem_cap = make_mat('FemoralCap', (0.76, 0.80, 0.86, 1.0), roughness=0.15, metallic=0.80)
    mat_chip = make_mat('ImplantChip', (0.0, 0.82, 0.85, 1.0), roughness=0.18, emission=1.8)
    mat_foot = make_mat('FootDark', (0.14, 0.15, 0.18, 1.0), roughness=0.55)
    mat_ax_x = make_mat('AxisX', (0.90, 0.10, 0.10, 1.0), roughness=0.3, emission=0.7)
    mat_ax_y = make_mat('AxisY', (0.10, 0.74, 0.22, 1.0), roughness=0.3, emission=0.7)
    mat_ax_z = make_mat('AxisZ', (0.12, 0.36, 0.92, 1.0), roughness=0.3, emission=0.7)

    empties = {}
    for bname in ('pelvis', 'femur_r', 'tibia_r', 'femur_l', 'tibia_l', 'imu'):
        e = bpy.data.objects.new(bname, None)
        e.rotation_mode = 'QUATERNION'
        bpy.context.collection.objects.link(e)
        empties[bname] = e

    # Pelvis, waist-to-chest torso, shoulders, neck, head (MuJoCo body-local: X ant, Y up, Z right)
    add_capsule('PelvisBridge', (0, -0.02, -0.10 * pelvis), (0, -0.02, 0.10 * pelvis), 0.056, mat_body, parent=empties['pelvis'])
    # Tapered torso (waist -> chest)
    add_tapered_limb('Torso', (0, 0.04, 0), (0, 0.44 * pelvis, 0), 0.072, 0.095, mat_body, parent=empties['pelvis'])
    # Shoulder bar
    sh_y = 0.44 * pelvis
    sh_z = 0.185 * pelvis
    add_capsule('Shoulders', (0, sh_y, -sh_z), (0, sh_y, sh_z), 0.044, mat_body, parent=empties['pelvis'])
    # Neck + Head
    add_capsule('Neck', (0, sh_y + 0.02, 0), (0, sh_y + 0.11 * pelvis, 0), 0.036, mat_joint, parent=empties['pelvis'])
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=0.088, location=(0, sh_y + 0.20 * pelvis, 0))
    head = bpy.context.active_object
    head.name = 'Head'
    head.data.materials.append(mat_joint)
    set_smooth(head)
    head.parent = empties['pelvis']

    # Decorative swinging arms (parented to pelvis at left/right shoulders; driven opposite to hip flexion)
    arm_u = 0.27 * pelvis
    arm_f = 0.24 * pelvis
    for s, sgn in (('r', +1.0), ('l', -1.0)):
        sh = bpy.data.objects.new(f'shoulder_{s}', None)
        sh.location = (0.0, sh_y, sgn * sh_z)
        sh.rotation_mode = 'XYZ'
        sh.parent = empties['pelvis']
        bpy.context.collection.objects.link(sh)
        empties[f'shoulder_{s}'] = sh
        add_tapered_limb(f'UpperArm_{s}', (0, 0, 0), (0, -arm_u, 0), 0.032, 0.026, mat_arm, parent=sh)
        # Natural 20-deg forward elbow bend
        ex = arm_f * math.sin(math.radians(20.0))
        ey = -arm_u - arm_f * math.cos(math.radians(20.0))
        add_tapered_limb(f'Forearm_{s}', (0, -arm_u, 0), (ex, ey, 0), 0.025, 0.020, mat_arm, parent=sh)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=0.026, location=(ex, ey, 0))
        hand = bpy.context.active_object
        hand.name = f'Hand_{s}'
        hand.data.materials.append(mat_joint)
        set_smooth(hand)
        hand.parent = sh

    # Slim human-proportioned legs + exact foot bottom (ankle_y - 0.030 - 0.026 = ankle_y - 0.056)
    for s in ('r', 'l'):
        is_dev = (s == imu_side)
        fmat = mat_dev_leg if is_dev else mat_body
        tmat = mat_dev_leg if is_dev else mat_body
        if is_dev:
            # Leave a visible gap right at the knee joint so the articulating spacer + metallic femoral cap stand out
            add_tapered_limb(f'Femur_{s}', (0, 0, 0), (0, -(femur - 0.028), 0), 0.044, 0.035, fmat, parent=empties[f'femur_{s}'])
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=0.040, location=(0, -(femur - 0.008), 0))
            fcap = bpy.context.active_object
            fcap.name = 'FemoralSpacerCap'
            fcap.scale = (1.10, 0.85, 1.05)
            fcap.data.materials.append(mat_fem_cap)
            set_smooth(fcap)
            fcap.parent = empties[f'femur_{s}']

            add_tapered_limb(f'Tibia_{s}', (0, -0.042, 0), (0, -tibia, 0), 0.033, 0.025, tmat, parent=empties[f'tibia_{s}'])
            # Articulating tibial insert spacer (bright white-silver puck at knee plateau)
            bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.044, depth=0.032, location=(0, -0.022, 0))
            sp = bpy.context.active_object
            sp.name = 'KneeSpacerInsert'
            sp.rotation_euler = (math.radians(90), 0, 0)
            sp.data.materials.append(mat_spacer)
            set_smooth(sp)
            sp.parent = empties[f'tibia_{s}']
        else:
            add_tapered_limb(f'Femur_{s}', (0, 0, 0), (0, -femur, 0), 0.044, 0.035, fmat, parent=empties[f'femur_{s}'])
            add_tapered_limb(f'Tibia_{s}', (0, 0, 0), (0, -tibia, 0), 0.033, 0.025, tmat, parent=empties[f'tibia_{s}'])
        add_capsule(f'Foot_{s}', (-0.03, -tibia - 0.030, 0), (0.15, -tibia - 0.030, 0), 0.026, mat_foot, parent=empties[f'tibia_{s}'])

    # Glowing cyan implant sensor chip + 3 device-axis arrows on 'imu' empty
    add_box('ImplantSensor', (0.008, 0, 0), (0.014, 0.015, 0.010), mat_chip, parent=empties['imu'])
    vo = (0.045, -0.042 if imu_side == 'r' else 0.042, 0.0)
    add_capsule('ImplantAxisX', vo, (vo[0] + 0.16, vo[1], vo[2]), 0.0055, mat_ax_x, parent=empties['imu'])
    add_capsule('ImplantAxisY', vo, (vo[0], vo[1] + 0.16, vo[2]), 0.0055, mat_ax_y, parent=empties['imu'])
    add_capsule('ImplantAxisZ', vo, (vo[0], vo[1], vo[2] + 0.16), 0.0055, mat_ax_z, parent=empties['imu'])

    return empties


def setup_camera_and_hud(env):
    bpy.ops.object.camera_add(location=(1.1, -3.7, 1.5))
    cam = bpy.context.active_object
    cam.name = 'MainCamera'
    cam.data.lens = 38.0
    bpy.context.scene.camera = cam

    hud_mat = make_mat('HudBg', (0.18, 0.62, 0.27, 1.0), roughness=0.9, emission=0.8)
    txt_mat = make_mat('HudTxt', (1.0, 1.0, 1.0, 1.0), roughness=0.9, emission=1.8)
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(-0.275, 0.195, -1.0))
    badge = bpy.context.active_object
    badge.name = 'HudBadge'
    badge.scale = (0.35, 0.095, 1.0)
    badge.data.materials.append(hud_mat)
    badge.parent = cam

    bpy.ops.object.text_add(location=(-0.435, 0.195, -0.992))
    txt_obj = bpy.context.active_object
    txt_obj.name = 'HudText'
    txt_obj.data.body = 'KNEIL V4'
    txt_obj.data.size = 0.020
    txt_obj.data.align_y = 'CENTER'
    txt_obj.data.materials.append(txt_mat)
    txt_obj.parent = cam

    return cam, hud_mat, txt_obj


def render_motion(json_path, out_dir, frame_step=1, samples=16):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    if 'BLENDER_EEVEE_NEXT' in engines:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    elif 'BLENDER_EEVEE' in engines:
        scene.render.engine = 'BLENDER_EEVEE'
    else:
        scene.render.engine = engines[0]

    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'taa_render_samples'):
        scene.eevee.taa_render_samples = samples
    scene.render.fps = int(round(data.get('fps', 25.0)))

    setup_studio_lighting()
    build_env_scene(data.get('env', {}))
    empties = build_human_rig(data['geom'])
    cam, hud_mat, txt_obj = setup_camera_and_hud(data.get('env', {}))

    out_dir = os.path.abspath(out_dir)
    frames = data['frames']
    env = data.get('env', {})
    etype = env.get('type', 'floor')
    cam_off = Vector((1.1, -3.7, 0.65)) if etype != 'bed' else Vector((1.1, -3.2, 2.0))
    ins_short = 'in-sample' if data.get('in_sample', True) else 'out-of-sample'

    for idx, fr in enumerate(frames):
        fnum = idx + 1
        for bname, bdata in fr['bodies'].items():
            e = empties[bname]
            e.location = m2b_pos(bdata['pos'])
            e.rotation_quaternion = m2b_quat(bdata['quat'])
            e.keyframe_insert('location', frame=fnum)
            e.keyframe_insert('rotation_quaternion', frame=fnum)
        imu = fr['imu']
        empties['imu'].location = m2b_pos(imu['pos'])
        empties['imu'].rotation_quaternion = m2b_quat(imu['quat'])
        empties['imu'].keyframe_insert('location', frame=fnum)
        empties['imu'].keyframe_insert('rotation_quaternion', frame=fnum)

        # Decorative arms swing opposite to asymmetric leg swing (0 when sitting/standing symmetrically)
        hf_r, hf_l = fr.get('hip_flex', [0.0, 0.0])
        diff = 0.5 * (float(hf_r) - float(hf_l))
        for s, ang in (('r', -0.65 * diff), ('l', +0.65 * diff)):
            sh = empties[f'shoulder_{s}']
            sh.rotation_euler = Euler((0.0, 0.0, ang), 'XYZ')
            sh.keyframe_insert('rotation_euler', frame=fnum)

        pel_b = m2b_pos(fr['bodies']['pelvis']['pos'])
        target = pel_b + Vector((0.0, 0.0, -0.05))
        cam.location = target + cam_off
        direction = (target - cam.location).normalized()
        cam.rotation_mode = 'QUATERNION'
        cam.rotation_quaternion = direction.to_track_quat('-Z', 'Y')
        cam.keyframe_insert('location', frame=fnum)
        cam.keyframe_insert('rotation_quaternion', frame=fnum)

    os.makedirs(out_dir, exist_ok=True)
    rendered = 0
    t_r0 = time.time()
    bsdf = hud_mat.node_tree.nodes.get('Principled BSDF')

    for idx in range(0, len(frames), max(1, frame_step)):
        fnum = idx + 1
        fr = frames[idx]
        scene.frame_set(fnum)
        dec = fr['decision']
        txt_obj.data.body = f'V4: {dec["label"]} ({dec["vote_pct"]}%)\nt = {fr["t"]:.2f} s  ({ins_short})'
        if bsdf:
            col = hex_to_rgba(dec['colour'])
            bsdf.inputs['Base Color'].default_value = col
            if 'Emission Color' in bsdf.inputs:
                bsdf.inputs['Emission Color'].default_value = col
        scene.render.filepath = os.path.join(out_dir, f'frame_{idx:04d}.png')
        bpy.ops.render.render(write_still=True)
        rendered += 1

    dt = time.time() - t_r0
    per_f = dt / max(rendered, 1)
    print(f'{VERSION} | engine={scene.render.engine} | rendered {rendered} frames (1920x1080) '
          f'in {dt:.2f}s ({per_f:.2f} s/frame) -> {out_dir}', flush=True)


def main():
    print(VERSION, flush=True)
    argv = sys.argv
    if '--' in argv:
        argv = argv[argv.index('--') + 1:]
    else:
        argv = []
    if len(argv) < 2:
        print('Usage: blender -b -P viewer/blender_render.py -- <motion.json> <out_dir> [--step N] [--samples S]')
        sys.exit(1)
    json_path, out_dir = argv[0], argv[1]
    step = 1
    samples = 16
    if '--step' in argv:
        step = int(argv[argv.index('--step') + 1])
    if '--samples' in argv:
        samples = int(argv[argv.index('--samples') + 1])
    render_motion(json_path, out_dir, frame_step=step, samples=samples)


if __name__ == '__main__':
    main()
