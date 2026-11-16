"""
Virtual KNEIL implant from a thigh IMU and a shank IMU (both with gyroscope).  v1.0, Nov 2026

The implant sits in the tibial insert, i.e. on the tibia, about 2.5 cm below the knee joint centre. A shank IMU is on
the same rigid segment, so the specific force at the implant point P follows from the shank sensor S:
    f_P = f_S + alpha x r + omega x (omega x r)          (sensor frame; r = vector S -> P; gravity cancels)
Steps:
  1. knee hinge axis j1 (thigh frame), j2 (shank frame): minimise sum(|w1 x j1| - |w2 x j2|)^2       (Seel et al.)
  2. knee centre o1, o2 (vectors from each sensor to the joint centre): minimise
     sum(|f1 - G1 o1| - |f2 - G2 o2|)^2 with G(w, a) o = w x (w x o) + a x o, then shift both along the axis to
     the points closest to the sensors                                                            (Seel et al.)
  3. tibia frame in the shank-sensor frame: z = gravity direction while standing still, y = knee axis (sign so that the
     forward leg swing is a rotation about -y, i.e. y points to the subject's left), x = y x z
  4. implant point r = o2 + (medial shift along the axis) - below * z + anterior * x; transfer; rotate to the device
     frame (x anterior, y left, z superior).
Units: acceleration in g, angular velocity in rad/s.
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.signal import butter, sosfiltfilt

G0 = 9.81
VERSION = 'vimp 1.2'


def lowpass(x, fc, fs, order=4):
    return sosfiltfilt(butter(order, fc, fs=fs, output='sos'), x, axis=0)


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def sph(t, p):
    return np.array([np.cos(t) * np.cos(p), np.cos(t) * np.sin(p), np.sin(t)])


def gamma(w, a, o):
    """w x (w x o) + a x o for every sample (o fixed, 3,)."""
    return np.cross(w, np.cross(w, o)) + np.cross(a, o)


def moving_mask(w1, w2, fs, thr=1.0):
    """Samples with clear rotation (fitting needs excitation)."""
    m = (np.linalg.norm(w1, axis=1) > thr) | (np.linalg.norm(w2, axis=1) > thr)
    return m


def joint_axis(w1, w2, n_max=3000, seed=0):
    rng = np.random.default_rng(seed)
    idx = np.arange(len(w1))
    if len(idx) > n_max:
        idx = np.sort(rng.choice(idx, n_max, replace=False))
    W1, W2 = w1[idx], w2[idx]
    def res(x):
        return np.linalg.norm(np.cross(W1, sph(x[0], x[1])), axis=1) - np.linalg.norm(np.cross(W2, sph(x[2], x[3])), axis=1)
    best = None
    for start in rng.uniform(-np.pi, np.pi, (8, 4)):
        r = least_squares(res, start)
        if best is None or r.cost < best.cost:
            best = r
    j1, j2 = sph(best.x[0], best.x[1]), sph(best.x[2], best.x[3])
    if np.corrcoef(W1 @ j1, W2 @ j2)[0, 1] < 0:                  # same rotation direction for both segments
        j1 = -j1
    return j1, j2, float(np.sqrt(best.cost * 2 / len(idx)))


def joint_centre(f1, w1, a1, f2, w2, a2, j1, j2, n_max=3000, seed=0):
    rng = np.random.default_rng(seed)
    idx = np.arange(len(f1))
    if len(idx) > n_max:
        idx = np.sort(rng.choice(idx, n_max, replace=False))
    F1, W1, A1, F2, W2, A2 = (v[idx] for v in (f1 * G0, w1, a1, f2 * G0, w2, a2))
    def res(x):
        return (np.linalg.norm(F1 - gamma(W1, A1, x[:3]), axis=1) - np.linalg.norm(F2 - gamma(W2, A2, x[3:]), axis=1))
    best = None
    for start in [np.r_[0, 0, 0.2, 0, 0, 0.2], np.r_[0, 0, -0.2, 0, 0, -0.2], np.zeros(6) + 0.05, rng.normal(0, 0.15, 6)]:
        r = least_squares(res, start)
        if best is None or r.cost < best.cost:
            best = r
    o1, o2 = best.x[:3], best.x[3:]
    s = (o1 @ j1 + o2 @ j2) / 2.0                                 # closest to the sensors along the axis
    o1, o2 = o1 - s * j1, o2 - s * j2
    return o1, o2, float(np.sqrt(best.cost * 2 / len(idx)) / G0)


def still_mask(f, w, fs, win=1.0):
    k = max(1, int(win * fs))
    wn = np.convolve(np.linalg.norm(w, axis=1), np.ones(k) / k, mode='same')
    fn = np.convolve(np.abs(np.linalg.norm(f, axis=1) - 1.0), np.ones(k) / k, mode='same')
    return (wn < 0.15) & (fn < 0.05)


def tibia_frame(f2, w2, j2, fs):
    """Rows = tibia x (anterior), y (left), z (superior) in shank-sensor coordinates."""
    st = still_mask(f2, w2, fs)
    g = f2[st].mean(0) if st.sum() > fs else lowpass(f2, 0.3, fs).mean(0)
    z = unit(g)
    y = unit(j2 - (j2 @ z) * z)
    wy = w2 @ y                                                   # forward swing = big rotation about -y
    peak = np.argmax(np.abs(wy))
    hi = np.abs(wy) > 0.6 * np.abs(wy[peak])
    if np.mean(wy[hi]) > 0:
        y = -y
    x = np.cross(y, z)
    return np.stack([x, y, z]), int(st.sum())


def transfer(f, w, a, r):
    """Specific force [g] at the point r (sensor frame, m) of the same rigid segment."""
    return f + gamma(w, a, r) / G0


def calibrate_up(f, w, fs):
    """Gravity direction (sensor coordinates) during quiet standing, or None if there is no still period of 1 s.
    Use one calibration per person and sensor for all their trials (the sensor stays on the leg)."""
    st = still_mask(lowpass(f, 15, fs), lowpass(w, 15, fs), fs)
    if st.sum() < fs:
        return None
    return unit(lowpass(f, 15, fs)[st].mean(0))


def tibia_frame_pca(w, fs, z_up, fc=15.0):
    """Rows x (anterior), y (left), z (superior) in sensor coordinates. y = main rotation axis of the shank while
    moving (sagittal rotation dominates), sign so that the big forward-swing peaks rotate about -y."""
    wf = lowpass(w, fc, fs)
    mv = np.linalg.norm(wf, axis=1) > 1.0
    if mv.sum() < fs:
        mv = np.linalg.norm(wf, axis=1) > 0.3
    pc = np.linalg.eigh(np.cov(wf[mv].T))[1][:, -1]
    z = unit(z_up)
    y = unit(pc - (pc @ z) * z)
    wy = wf @ y
    hi = np.abs(wy) > 0.6 * np.abs(wy).max()
    if wy[hi].mean() > 0:
        y = -y
    return np.stack([np.cross(y, z), y, z])


def virtual_implant(f, w, fs, z_up=None, distance=0.22, anterior=-0.02, medial=0.0, side='R', fc=15.0, T=None):
    """Implant specific force [g] in the device frame (x anterior, y left, z superior) from ONE shank IMU.
    z_up: standing gravity direction of this sensor (calibrate_up); if None, quiet periods of this recording are used,
    and the trial-mean direction as the last resort (biased by the forward lean of the shank while walking).
    distance: sensor-to-implant distance along the tibia axis (implant above the sensor); anterior/medial offsets of
    the implant relative to the sensor (m). Validated on Camargo (real shank IMU vs implant from the replay):
    the knee-centre fit of Seel et al. gave a wrong lever arm on these data, so it is not used."""
    how = 'calibrated'
    if z_up is None:
        z_up = calibrate_up(f, w, fs); how = 'still periods of this recording'
    if z_up is None:
        z_up = unit(lowpass(f, 0.3, fs).mean(0)); how = 'trial mean (biased by the walking lean)'
    if T is None:
        T = tibia_frame_pca(w, fs, z_up, fc)
    x, y, z = T
    med = medial if side.upper().startswith('R') else -medial          # medial = +y on the right leg, -y on the left
    r = distance * z + anterior * x + med * y
    wf = lowpass(w, fc, fs)
    fP = transfer(f, wf, np.gradient(wf, 1 / fs, axis=0), r)
    return fP @ T.T, dict(T=T, r=r, up_source=how)


def person_frame(standing, walking, fs):
    """One tibia frame per person and sensor (the sensor does not move between their tasks).
    standing: list of (f, w) recordings that contain quiet standing; walking: list of (f, w) walking recordings.
    z = standing gravity direction; y = main rotation axis while walking, signed by the forward swing; x = y x z.
    Returns (T or None, note). Squats, sit-to-stand or seated tasks then use this frame: their own motion does not
    say which way is forward (stage 1b found x flipped in squats with a per-recording frame)."""
    z = None
    for f, w in standing + walking:
        z = calibrate_up(f, w, fs)
        if z is not None:
            break
    if z is None:
        return None, 'no quiet standing found'
    if not walking:
        return None, 'no walking recording to set the forward direction'
    W = np.vstack([w for f, w in walking])
    return tibia_frame_pca(W, fs, z), f'standing from {len(standing)} rec., forward from {len(walking)} walking rec.'
