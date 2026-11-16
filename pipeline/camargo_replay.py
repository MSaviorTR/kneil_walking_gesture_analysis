"""
Camargo et al. (2021) open dataset -> KNEIL MuJoCo replay.

Drives the KNEIL MuJoCo model (kneil_v1.build_model, gait2354 coordinate set, scaled to the subject's
height) with the dataset's OpenSim inverse kinematics, and returns specific force and angular velocity at
  - 'shin_r': a virtual sensor where Camargo's shank IMU sat (3/4 down the right shank, anterior surface)
  - 'imu'   : the KNEIL implant site in the right tibial insert (device frame: x anterior, y left, z superior)
Also: frame alignment of a real IMU to the simulated segment frame (Kabsch on the gyroscope), lever-arm
estimation, kinematic activity labels and foot-contact events.

Data layout accepted: <root>/<subject>/<mode>/{ik,imu}/<trial>.mat   (e.g. ab06/stair/ik/stair_1_l_01_01.mat)
                  or: <root>/<SUBJECT>/<date>/<mode>/{ik,imu}/<trial>.mat   (original dataset layout)
MATLAB tables are read with mat-io (pip install mat-io).
"""
import glob, os
import numpy as np
import mujoco
from scipy.interpolate import CubicSpline
from scipy.signal import butter, sosfiltfilt
import kneil_v1 as K

KDIR = os.path.dirname(os.path.abspath(__file__))
# Camargo et al. 2021, Table 1 (height in m)
HEIGHT = dict(ab06=1.80, ab07=1.65, ab08=1.74, ab09=1.63, ab10=1.75, ab11=1.75, ab12=1.74, ab13=1.73, ab14=1.52,
              ab15=1.78, ab16=1.65, ab17=1.68, ab18=1.80, ab19=1.70, ab20=1.71, ab21=1.57, ab23=1.80, ab24=1.73,
              ab25=1.63, ab27=1.70, ab28=1.69, ab30=1.77)
FS_DATA = 200.0
TRANSLATIONS = ('pelvis_tx', 'pelvis_ty', 'pelvis_tz')
_OSIM = None


def load_table(path):
    import matio
    return matio.load_from_mat(path)['data']


def find_trials(root, subj, mode):
    """Trial names that have both ik and imu tables, in either directory layout."""
    hits = sorted(glob.glob(os.path.join(root, subj, mode, 'ik', '*.mat')) +
                  glob.glob(os.path.join(root, subj.upper(), '*', mode, 'ik', '*.mat')))
    out = []
    for p in hits:
        q = p.replace(os.sep + 'ik' + os.sep, os.sep + 'imu' + os.sep)
        if os.path.exists(q):
            out.append((os.path.splitext(os.path.basename(p))[0], p, q))
    return out


def model_for(subj, side='r', shank_frac=0.75, implant_pos=(0.005, -0.025, 0.0), mount=(0.0, 0.0, 0.0)):
    global _OSIM
    if _OSIM is None:
        import config
        _OSIM = K.read_osim(K.fetch('osim', folder=config.OPENSIM_DIR))
    k = HEIGHT[subj.lower()] / K.H_REF
    return K.build_model(_OSIM, femur=K.REF['femur'] * k, tibia=K.REF['tibia'] * k, pelvis=k, imu_side=side,
                         imu_pos=implant_pos, mount=mount, shin_frac=shank_frac)


def ik_to_Q(m, info, ik, fs_out=FS_DATA, f_lp=12.0):
    """IK table -> generalized coordinates (radians, metres), low-passed and resampled to fs_out."""
    idx = K.qidx(m)
    t = ik['Header'].values.astype(float)
    t = t - t[0]
    t_out = np.arange(0.0, t[-1] + 1e-9, 1.0 / fs_out)
    sos = butter(4, f_lp, fs=FS_DATA, output='sos')
    Q = np.zeros((len(t_out), m.nq))
    for name, a in idx.items():
        if name.startswith('knee_t') or name not in ik.columns:
            continue
        y = ik[name].values.astype(float)
        if name not in TRANSLATIONS:
            y = np.unwrap(np.radians(y))            # turns can wrap pelvis_rotation at +-180 deg
        y = sosfiltfilt(sos, y)
        Q[:, a] = y if len(t_out) == len(t) else CubicSpline(t, y)(t_out)
    return t_out, K.set_knee_translations(Q, idx, info)


def replay(m, Q, fs, sensors=('acc_imu', 'gyr_imu', 'acc_shin_r', 'gyr_shin_r')):
    """Kinematic replay with mj_inverse. Returns accelerometers in g, gyros in rad/s (site frames),
    'grav_<acc sensor>' = the static (gravity) part of that accelerometer in its frame (g; |grav| = 1),
    the right ankle position (world) and the right-tibia tilt (deg, + = top of tibia forward)."""
    QD = np.gradient(Q, 1.0 / fs, axis=0)
    QDD = np.gradient(QD, 1.0 / fs, axis=0)
    d = mujoco.MjData(m)
    adr = {n: m.sensor(n).adr[0] for n in sensors}
    site = {n: int(m.sensor_objid[m.sensor(n).id]) for n in sensors if n.startswith('acc')}
    out = {n: np.zeros((len(Q), 3)) for n in sensors}
    grav = {n: np.zeros((len(Q), 3)) for n in site}
    ank, tib, pel = m.site('ankle_r').id, m.body('tibia_r').id, m.body('pelvis').id
    ankle, tilt = np.zeros((len(Q), 3)), np.zeros(len(Q))
    for i in range(len(Q)):
        d.qpos[:], d.qvel[:], d.qacc[:] = Q[i], QD[i], QDD[i]
        mujoco.mj_inverse(m, d)
        for n in sensors:
            out[n][i] = d.sensordata[adr[n]:adr[n] + 3]
        for n, sid in site.items():
            grav[n][i] = d.site_xmat[sid].reshape(3, 3)[1, :]          # R^T (0, 1, 0): world 'up' in the site frame
        ankle[i] = d.site_xpos[ank]
        ax = d.xmat[tib].reshape(3, 3)[:, 1]                     # tibia long axis (superior), world
        fw = d.xmat[pel].reshape(3, 3)[:, 0]                     # pelvis anterior axis = heading
        fw = np.array([fw[0], 0.0, fw[2]]) / (np.hypot(fw[0], fw[2]) + 1e-12)
        tilt[i] = np.degrees(np.arctan2(ax @ fw, ax[1]))         # sagittal tilt in the heading frame
    for n in sensors:
        if n.startswith('acc'):
            out[n] /= K.G
    out.update({f'grav_{n}': g for n, g in grav.items()})
    out.update(ankle=ankle, tilt=tilt, QD=QD)
    return out


def scale_dynamic(acc, grav, k):
    """Scale only the movement part of a specific-force signal: k * (acc - grav) + grav (all in g)."""
    return grav + k * (acc - grav)


def draw_person(rng, calib=None):
    """Per-person randomisation from the 22-subject Camargo comparison (Nov 2026):
    impact speed exponent ~ N(1.35, 0.45) clipped to [0.5, 2.1] (panel c: median 1.34, range 0.60-1.95);
    movement-amplitude factor ~ U(0.82, 1.10) (panel b: sim/real amplitude 0.94-1.24);
    stair impact gains relative to walking at 1.3 m/s: log-normal from the real-IMU calibration (calib), else the
    earlier assumptions 0.5 (ascent) and 1.3 (descent)."""
    p = dict(impact_exponent=float(np.clip(rng.normal(1.35, 0.45), 0.5, 2.1)), amplitude=float(rng.uniform(0.82, 1.10)))
    if calib and calib.get('up') and calib.get('down'):
        for k, key in (('up', 'stair_up_gain'), ('down', 'stair_down_gain')):
            p[key] = float(np.exp(rng.normal(calib[k]['mu'], calib[k]['sd'])))
    else:
        p.update(stair_up_gain=0.5, stair_down_gain=1.3)
    return p


def lowpass_causal(x, fc, fs, order=2):
    """Causal Butterworth low-pass (what a device filter would do), along axis 0."""
    from scipy.signal import sosfilt
    return sosfilt(butter(order, fc, fs=fs, output='sos'), x, axis=0)


def missing_hf(acc, grav, gyr, rng, fs=200.0):
    """Fast (6-25 Hz) content that the replay cannot contain (the markers were low-passed at 6 Hz): soft-tissue
    and strap vibration of a skin-mounted IMU. Band-limited noise scaled by the slow movement; strength drawn per
    trial between pre-filtered (AB06-like) and loose (AB07-like) recordings:
    gyro 6-25 Hz RMS gain 0.02-0.22 x |w|_slow (rad/s), accelerometer 0.04-0.35 x |a|_slow,dyn (g) (AB07: 0.19, 0.32)."""
    from scipy.signal import sosfilt
    n = len(acc)
    bp = butter(4, [6.0, 25.0], btype='band', fs=fs, output='sos')

    def band_noise():
        x = sosfilt(bp, rng.standard_normal((n + 400, 3)), axis=0)[400:]
        return x / (np.sqrt((x ** 2).sum(1).mean()) + 1e-12)          # unit RMS of the vector magnitude
    u = rng.uniform(0.0, 1.0)                                         # one 'attachment looseness' for both sensors
    b_g = 0.02 * (0.22 / 0.02) ** float(np.clip(u + rng.normal(0, 0.1), 0, 1))
    b_a = 0.04 * (0.35 / 0.04) ** float(np.clip(u + rng.normal(0, 0.1), 0, 1))
    w_slow = np.linalg.norm(lowpass(gyr, 6.0, fs), axis=1)
    a_slow = np.linalg.norm(lowpass(acc, 6.0, fs) - grav, axis=1)
    g_hf = band_noise() * (rng.uniform(0.005, 0.03) + b_g * w_slow)[:, None]
    a_hf = band_noise() * (rng.uniform(0.003, 0.012) + b_a * a_slow)[:, None]
    return a_hf, g_hf, dict(looseness=float(u), gyro_gain=float(b_g), acc_gain=float(b_a))


def calibrate_stair_impacts(validation, min_walk_peak=0.05):
    """Stair impact gains relative to walking at 1.1-1.5 m/s, per subject, from the real shank IMU (validation
    results: impact_peak_real_g, contact_speed, contact_label). Subjects whose recordings carry no impacts
    (median walking peak < min_walk_peak g, i.e. pre-filtered) are excluded. Returns per-subject ratios and a
    log-normal fit (mu, sd of log ratio) for ascent and descent."""
    by = {}
    for key, r in validation.items():
        if not r.get('sync_ok'):
            continue
        s = key.split('/')[0]
        d = by.setdefault(s, {1: [], 2: [], 3: []})
        for pk, sp, lab in zip(r.get('impact_peak_real_g', []), r.get('contact_speed', []), r.get('contact_label', [])):
            if lab == 1 and np.isfinite(sp) and 1.1 <= sp <= 1.5:
                d[1].append(pk)
            elif lab in (2, 3):
                d[lab].append(pk)
    per, excluded = {}, []
    for s, d in sorted(by.items()):
        if len(d[1]) < 20 or np.median(d[1]) < min_walk_peak:
            excluded.append(s); continue
        w = float(np.median(d[1]))
        per[s] = dict(walk_peak_g=w, n_walk=len(d[1]),
                      up_ratio=float(np.median(d[2]) / w) if len(d[2]) >= 5 else None, n_up=len(d[2]),
                      down_ratio=float(np.median(d[3]) / w) if len(d[3]) >= 5 else None, n_down=len(d[3]))
    out = dict(subjects=per, excluded=excluded)
    for k in ('up', 'down'):
        v = np.array([p[f'{k}_ratio'] for p in per.values() if p[f'{k}_ratio']])
        if len(v) >= 3:
            out[k] = dict(median=float(np.median(v)), mu=float(np.log(v).mean()), sd=float(max(np.log(v).std(ddof=1), 0.1)),
                          q25=float(np.percentile(v, 25)), q75=float(np.percentile(v, 75)), n=int(len(v)))
    return out


def kabsch(A, B):
    """Rotation R minimising sum ||B_i - R A_i||^2 (rows are vectors)."""
    U, _, Vt = np.linalg.svd(A.T @ B)
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(Vt.T @ U.T))])
    return Vt.T @ D @ U.T


def lowpass(x, fc, fs=FS_DATA, order=4):
    return sosfiltfilt(butter(order, fc, fs=fs, output='sos'), x, axis=0)


def kinematic_labels(Q, idx, ankle, fs=FS_DATA, mode=None):
    """0 standing, 1 walking, 2 stairs up, 3 stairs down, from kinematics only (the uploaded data have no
    'conditions' labels). Locomotion = knee or ankle-height activity in a 2 s window; stairs = sustained
    vertical pelvis velocity."""
    knee = -np.degrees(Q[:, idx['knee_angle_r']])
    w = int(2 * fs)
    pad = lambda x: np.pad(x, (w // 2, w - w // 2 - 1), mode='edge')
    from numpy.lib.stride_tricks import sliding_window_view as swv
    krng = np.ptp(swv(pad(knee), w), axis=1)
    loco = krng > 25.0
    vy = np.gradient(lowpass(Q[:, idx['pelvis_ty']], 0.7, fs), 1.0 / fs)
    lab = np.where(loco, 1, 0)
    lab[loco & (vy > 0.12)] = 2
    lab[loco & (vy < -0.12)] = 3
    if mode == 'ramp':                      # ramps also raise the pelvis: own classes 4 (up) / 5 (down)
        lab[lab == 2] = 4; lab[lab == 3] = 5
    elif mode is not None and mode != 'stair':
        lab[lab >= 2] = 1                   # treadmill / level ground: vertical drift is not stairs
    return lab


def foot_contacts(ankle, fs=FS_DATA, v_swing=-0.25, v_contact=-0.05):
    """Right-foot contacts: the ankle falls faster than v_swing (m/s) in late swing, then stops (> v_contact)."""
    vy = np.gradient(lowpass(ankle[:, 1], 8.0, fs), 1.0 / fs)
    ev, armed = [], False
    for i in range(1, len(vy)):
        if vy[i] < v_swing:
            armed = True
        elif armed and vy[i] > v_contact:
            ev.append(i)
            armed = False
    return np.array(ev, int)


def walking_speed_at(Q, idx, ankle, ev, fs=FS_DATA):
    """Speed of the body over the stance foot (works on treadmill and overground): |v_pelvis - v_ankle|
    horizontally, averaged over 50-250 ms after each contact."""
    p = np.c_[Q[:, idx['pelvis_tx']], Q[:, idx['pelvis_tz']]]
    a = np.c_[ankle[:, 0], ankle[:, 2]]
    rel = np.gradient(lowpass(p - a, 5.0, fs), 1.0 / fs, axis=0)
    sp = np.linalg.norm(rel, axis=1)
    return np.array([np.median(sp[i + int(0.05 * fs):i + int(0.25 * fs)]) if i + int(0.25 * fs) < len(sp) else np.nan
                     for i in ev])


def align(gyr_sim, acc_sim, gyr_real, acc_real, fc=6.0, w_acc=3.0):
    """Sensor-from-site rotation from gyroscope AND accelerometer (gravity fixes the rotation about the
    dominant sagittal gyro axis, which a gyro-only fit leaves ambiguous). Fit on calibration data only."""
    A = np.r_[lowpass(gyr_sim, fc), w_acc * lowpass(acc_sim, fc)]
    B = np.r_[lowpass(gyr_real, fc), w_acc * lowpass(acc_real, fc)]
    return kabsch(A, B)


def compare(sim, real, fc=6.0):
    """Per-axis Pearson r and amplitude ratio (std sim / std real) after the same zero-phase low-pass."""
    s, r = lowpass(sim, fc), lowpass(real, fc)
    rr = np.array([np.corrcoef(s[:, k], r[:, k])[0, 1] for k in range(3)])
    return rr, s.std(0) / (r.std(0) + 1e-12)


# ----------------------------------------------------------------------------------------------------------------
# dataset labels from the 'conditions' tables (1000 Hz), mapped to KNEIL classes; kinematic labels as fallback
# ----------------------------------------------------------------------------------------------------------------
LABELS = ('standing', 'walking', 'stairs_up', 'stairs_down', 'ramp_up', 'ramp_down')


def map_condition_label(s):
    """Camargo locomotion-mode strings (e.g. 'stand', 'walk', 'turn1', 'stand-walk', 'stairascent',
    'walk-stairdescent', 'rampascent') -> 0..5, or -1 if unknown. Transitions into or out of stairs/ramps count
    as stairs/ramps; turns and stand-walk transitions count as walking."""
    s = str(s).lower()
    if 'stair' in s and 'ascent' in s:
        return 2
    if 'stair' in s and 'descent' in s:
        return 3
    if 'ramp' in s and 'ascent' in s:
        return 4
    if 'ramp' in s and 'descent' in s:
        return 5
    if 'walk' in s or 'turn' in s:
        return 1
    if 'stand' in s or 'idle' in s:
        return 0
    return -1


def conditions_path(ik_path):
    p = ik_path.replace(os.sep + 'ik' + os.sep, os.sep + 'conditions' + os.sep)
    return p if os.path.exists(p) else None


def _flat(x):
    """Unwrap MATLAB cell/char contents (e.g. array(['walk']), [[0.005]], b'walk') to a Python scalar or str."""
    for _ in range(6):
        if isinstance(x, (list, tuple)):
            x = np.asarray(x, dtype=object)
        if not isinstance(x, np.ndarray):
            break
        if x.size == 0:
            return ''
        if x.dtype.kind in 'US' and x.size > 1:          # char array stored letter by letter
            return ''.join(str(c) for c in x.ravel())
        x = x.ravel()[0]
    if isinstance(x, bytes):
        x = x.decode(errors='ignore')
    return x.item() if isinstance(x, np.generic) else x


def conditions_labels(path, header):
    """Labels (0..5, -1 = unknown string) on the time stamps `header` from a conditions .mat file.
    Returns (labels, vocabulary) or (None, reason). Never raises: any problem is returned as the reason."""
    import pandas as pd
    import matio
    try:
        d = matio.load_from_mat(path)
    except Exception as e:
        return None, f'unreadable ({type(e).__name__})'
    reason = 'no label table'
    for name, v in sorted(d.items(), key=lambda kv: (kv[0].lower() != 'labels', kv[0])):   # 'labels' first
        try:
            if not isinstance(v, pd.DataFrame) or len(v) < 2:
                continue
            cols = {c: ([_flat(x) for x in v[c].values] if v[c].dtype == object else list(v[c].values)) for c in v.columns}
            num, txt = [], []
            for c, vals in cols.items():
                (num if pd.to_numeric(pd.Series(vals), errors='coerce').notna().mean() > 0.95 else txt).append(c)
            tcol = 'Header' if 'Header' in num else (num[0] if num else None)
            if tcol is None or not txt:
                continue
            known = {c: np.mean([map_condition_label(x) >= 0 for x in cols[c]]) for c in txt}
            best = max(known, key=known.get)
            if known[best] < 0.5:                         # not a locomotion-label column
                continue
            tt = pd.to_numeric(pd.Series(cols[tcol]), errors='coerce').to_numpy(float)
            ll = np.array([str(x) for x in cols[best]])
            codes = np.array([map_condition_label(x) for x in ll])
            ok = np.isfinite(tt)
            order = np.argsort(tt[ok], kind='stable')
            tt, codes = tt[ok][order], codes[ok][order]
            j = np.clip(np.searchsorted(tt, header, side='right') - 1, 0, len(tt) - 1)
            return codes[j], sorted(set(ll.tolist()))[:40]
        except Exception as e:                            # keep looking; report the last problem
            reason = f'{name}: {type(e).__name__}: {e}'[:120]
    return None, reason


def trial_labels(Q, idx, ankle, ik, ik_path, mode, t_rel):
    """Dataset labels where available (unknown strings filled from kinematics), else kinematic labels.
    Returns (labels, source, agreement_with_kinematics, vocabulary)."""
    kin = kinematic_labels(Q, idx, ankle, fs=1.0 / (t_rel[1] - t_rel[0]), mode=mode)
    cp = conditions_path(ik_path)
    if cp is None:
        return kin, 'kinematics', None, None
    try:
        lab, vocab = conditions_labels(cp, float(ik['Header'].values[0]) + t_rel)
    except Exception as e:                                # labels must never stop a trial
        lab, vocab = None, f'{type(e).__name__}: {e}'[:120]
    if lab is None:
        return kin, f'kinematics ({vocab})', None, None
    ok = lab >= 0
    agree = float(np.mean(lab[ok] == kin[ok])) if ok.any() else None
    return np.where(ok, lab, kin), 'conditions', agree, vocab
