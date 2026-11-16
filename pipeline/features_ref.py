"""
Reference implementation of the 20 KNEIL chip features in pure numpy (float64).   features_ref 1.0, 16 Nov 2026

A line-by-line port of kneil_features() in kneil_tinyml/src/kneil_features.c. The feature order is the order of the
KF_* enum in kneil_tinyml/include/kneil_tinyml.h (= the model input order). It is an independent check of the C code
(pipeline/test_features_window.py); nothing in the training path uses it.

features_ref(x, y, z, fs) -> np.ndarray (20,), order = NAMES
"""
import numpy as np

VERSION = 'features_ref 1.0'
RAD2DEG = 57.29577951            # RAD2DEG in kneil_features.c
EPS = 1e-9                       # eps in kneil_features.c

NAMES = ['mean_x', 'mean_y', 'mean_z', 'std_x', 'std_y', 'std_z', 'std_m', 'mean_m', 'ptp_m', 'max_m',
         'jerk_m', 'tilt_sag_deg', 'tilt_cor_deg', 'ac_m_05s', 'ac_m_10s', 'zcr_z_hz', 'trend_x', 'trend_z',
         'corr_xz', 'hf_ratio']
assert len(NAMES) == 20

I_ZCR = NAMES.index('zcr_z_hz')


def features_ref(x, y, z, fs):
    """The 20 features of one window, float64. Same arithmetic as the C function, vectorised."""
    x = np.asarray(x, np.float64).ravel()
    y = np.asarray(y, np.float64).ravel()
    z = np.asarray(z, np.float64).ravel()
    n = len(x)
    assert len(y) == n and len(z) == n and n >= 2, f'window lengths {len(x)}, {len(y)}, {len(z)}'
    mag = np.sqrt(x * x + y * y + z * z)                  # mag3()
    inv_n = 1.0 / n
    mx, my, mz, mm = x.mean(), y.mean(), z.mean(), mag.mean()
    mmin, mmax = mag.min(), mag.max()
    l1 = int(0.5 * fs + 0.5)                              # autocorrelation lags, as in C
    l2 = int(1.0 * fs + 0.5)
    q = n // 4
    dx, dy, dz = x - mx, y - my, z - mz
    dm = mag - mm
    vx = float(np.dot(dx, dx)); vy = float(np.dot(dy, dy)); vz = float(np.dot(dz, dz))
    vm = float(np.dot(dm, dm)); cxz = float(np.dot(dx, dz))
    dd = np.diff(mag)                                     # i > 0: dd = m[i] - m[i - 1]
    jerk = float(np.abs(dd).sum()); d2 = float(np.dot(dd, dd))
    zc = int(np.count_nonzero((dz[1:] > 0.0) != (dz[:-1] > 0.0)))     # sign change of z - mean(z)
    ac1 = float(np.dot(dm[l1:], mag[:-l1] - mm)) if n > l1 else 0.0
    ac2 = float(np.dot(dm[l2:], mag[:-l2] - mm)) if n > l2 else 0.0
    tx0 = float(x[:q].sum()); tz0 = float(z[:q].sum())    # first quarter
    tx1 = float(x[n - q:].sum()); tz1 = float(z[n - q:].sum())        # last quarter
    f = np.zeros(20, np.float64)
    f[0], f[1], f[2] = mx, my, mz
    f[3], f[4], f[5] = np.sqrt(vx * inv_n), np.sqrt(vy * inv_n), np.sqrt(vz * inv_n)
    f[6], f[7], f[8], f[9] = np.sqrt(vm * inv_n), mm, mmax - mmin, mmax
    f[10] = jerk / (n - 1) * fs
    f[11] = np.arctan2(-mx, mz) * RAD2DEG
    f[12] = np.arctan2(my, mz) * RAD2DEG
    f[13] = ac1 / (vm + EPS)
    f[14] = ac2 / (vm + EPS)
    f[15] = zc * fs / n
    f[16] = (tx1 - tx0) / q if q > 0 else np.nan
    f[17] = (tz1 - tz0) / q if q > 0 else np.nan
    f[18] = cxz / np.sqrt(vx * vz + EPS)
    f[19] = d2 / (vm + EPS)
    return f
