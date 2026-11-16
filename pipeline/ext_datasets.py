"""
External datasets for KNEIL (Nov 2026):
  HAR70+ (Ustad et al. 2023) and HARTH (Logacjov et al. 2021): thigh + lower-back AX3, 50 Hz, video labels.
      -> activity bouts, pauses inside walking, cadence (calibration of the walker personas).
  Marpino walking dataset: shank / thigh / foot IMUs on both legs, 100 Hz, 20 elderly + 20 young, 5 m walks.
      -> real shank IMU of older adults: does the 4-class shank model recognise their walking?
  Caicedo, Rengifo, Rodriguez et al. 2020 (Data in Brief 33:106550): 44 older adults, Vicon CGM2.3 markers, 100 Hz.
      -> virtual shank IMU and virtual KNEIL implant from the real tibia motion; test of the on-device model.
Features are computed exactly as in the Camargo experiment (tstr_camargo: 200 Hz -> causal 6 Hz low-pass ->
channels |a|, axial a, |w| -> 50 Hz -> 2 s windows, 1 s hop).
"""
import ctypes, glob, json, os, re
import numpy as np
import pandas as pd
from scipy.signal import resample_poly, welch, butter, sosfiltfilt

CODE_VERSION = '2026-11-09f (viewer export)'

HAR_LABELS = {1: 'walking', 2: 'running', 3: 'shuffling', 4: 'stairs_up', 5: 'stairs_down', 6: 'standing', 7: 'sitting',
              8: 'lying', 13: 'cycling_sit', 14: 'cycling_stand', 130: 'cycling_sit_inactive', 140: 'cycling_stand_inactive'}
MARPINO_SENSORS = {1: 'right_foot', 2: 'right_shank', 3: 'right_thigh', 4: 'left_thigh', 5: 'left_shank', 6: 'left_foot', 7: 'back'}
SHANK_CLASSES = ('standing', 'walking', 'stairs_up', 'stairs_down')
DEVICE_CLASSES = ('walking', 'stairs_up', 'stairs_down', 'sitting', 'standing', 'lying', 'sit_to_stand', 'stand_to_sit', 'bed_transfer')


# ------------------------------------------------------------------ locating the data
def find_folder(root, *patterns, depth=3):
    """First folder under root whose name contains one of the patterns (case-insensitive), breadth first."""
    level = [root]
    for _ in range(depth):
        nxt = []
        for d in level:
            try:
                subs = sorted(e for e in os.listdir(d) if os.path.isdir(os.path.join(d, e)))
            except OSError:
                continue
            for e in subs:
                if any(p.lower() in e.lower() for p in patterns):
                    return os.path.join(d, e)
                nxt.append(os.path.join(d, e))
        level = nxt
    return None


def files(folder, *exts):
    """Data files under folder, without Office lock files (~$name.xlsx, present while a file is open) or hidden files."""
    out = []
    for e in exts:
        out += glob.glob(os.path.join(folder, '**', f'*.{e}'), recursive=True)
    return sorted(p for p in set(out) if not os.path.basename(p).startswith(('~$', '.')))


def locate(root):
    return dict(har70=find_folder(root, 'har70'), harth=find_folder(root, 'harth'),
                marpino=find_folder(root, 'marpino'), caicedo=find_folder(root, 'rodr', 'caicedo'))


# ------------------------------------------------------------------ HAR70+ / HARTH
def read_har(path):
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    t = pd.to_datetime(df['timestamp'])
    dt = np.median(np.diff(t.values).astype('timedelta64[ns]').astype(float)) / 1e9
    return df, float(1.0 / dt)


def label_runs(lab):
    out, s = [], 0
    for i in range(1, len(lab) + 1):
        if i == len(lab) or lab[i] != lab[s]:
            out.append((int(lab[s]), s, i)); s = i
    return out


def har_subject(path, gap_max=5.0):
    """Time per activity, bout lengths, pauses inside walking (standing/shuffling gaps <= gap_max s between two
    walking runs) and cadence from the thigh inclination (dominant stride frequency of walking runs >= 5 s)."""
    df, fs = read_har(path)
    lab = df['label'].to_numpy(int)
    R = label_runs(lab)
    time_s, bouts = {}, {}
    for l, a, b in R:
        nm = HAR_LABELS.get(l, str(l))
        time_s[nm] = time_s.get(nm, 0.0) + (b - a) / fs
        bouts.setdefault(nm, []).append((b - a) / fs)
    gaps, wruns = [], []
    for i, (l, a, b) in enumerate(R):
        if l == 1:
            wruns.append((b - a) / fs)
        elif l in (3, 6) and 0 < i < len(R) - 1 and R[i - 1][0] == 1 and R[i + 1][0] == 1 and (b - a) / fs <= gap_max:
            gaps.append((b - a) / fs)
    th = np.degrees(np.arctan2(df['thigh_z'].to_numpy(float), df['thigh_x'].to_numpy(float)))
    cad = []
    for l, a, b in R:
        if l == 1 and b - a >= 5 * fs:
            x = th[a:b] - th[a:b].mean()
            f, P = welch(x, fs=fs, nperseg=min(len(x), int(8 * fs)), nfft=8192)        # zero-padded: fine peak
            m = (f >= 0.3) & (f <= 1.5)
            if m.any():
                cad.append(120.0 * f[m][np.argmax(P[m])])
    return dict(subject=os.path.splitext(os.path.basename(path))[0], fs=round(fs, 2), minutes=round(len(lab) / fs / 60, 1),
                time_s={k: round(v, 1) for k, v in time_s.items()}, bouts={k: [round(x, 2) for x in v] for k, v in bouts.items()},
                walk_runs=[round(x, 2) for x in wruns], gaps=[round(x, 2) for x in gaps],
                cadence=float(np.median(cad)) if cad else float('nan'), n_cadence_runs=len(cad))


def har_summary(subjects, n_slow=5):
    """Slowest walkers (lowest cadence) vs the rest: pauses inside walking and walking-run lengths."""
    ok = [s for s in subjects if np.isfinite(s['cadence'])]
    order = sorted(ok, key=lambda s: s['cadence'])
    slow = {s['subject'] for s in order[:n_slow]}
    def pool(sel, key):
        v = np.array([x for s in subjects if (s['subject'] in slow) == sel for x in s[key]])
        return dict(n=int(len(v)), median=float(np.median(v)) if len(v) else None, q25=float(np.percentile(v, 25)) if len(v) else None,
                    q75=float(np.percentile(v, 75)) if len(v) else None)
    return dict(slowest=sorted(slow), cadence={s['subject']: round(s['cadence'], 1) for s in order},
                pauses_slow=pool(True, 'gaps'), pauses_other=pool(False, 'gaps'),
                walk_runs_slow=pool(True, 'walk_runs'), walk_runs_other=pool(False, 'walk_runs'),
                pauses_per_min_walking_slow=_rate(subjects, slow, True), pauses_per_min_walking_other=_rate(subjects, slow, False))


def _rate(subjects, slow, sel):
    n = sum(len(s['gaps']) for s in subjects if (s['subject'] in slow) == sel)
    t = sum(s['time_s'].get('walking', 0) for s in subjects if (s['subject'] in slow) == sel)
    return round(60 * n / t, 2) if t else None


# ------------------------------------------------------------------ shared feature pipeline (as tstr_camargo)
def movement_labels(gyr, fs, thr=0.6):
    """1 (walking) where the slow angular speed is high, 0 (standing) where the leg is still; smoothed over 1 s."""
    import camargo_replay as C
    w = np.linalg.norm(C.lowpass(gyr, 3.0, fs), axis=1)
    k = max(1, int(fs))
    w = np.convolve(w, np.ones(k) / k, mode='same')
    return (w > thr).astype(int)


def shank_features(acc_g, gyr_rad, fs, lab=None):
    """Low-pass (6 Hz, causal) features of the Camargo experiment from any shank IMU recording."""
    import camargo_replay as C, tstr_camargo as T
    from fractions import Fraction
    fr = Fraction(200, int(round(fs))).limit_denominator(10)
    a = resample_poly(acc_g, fr.numerator, fr.denominator, axis=0)
    g = resample_poly(gyr_rad, fr.numerator, fr.denominator, axis=0)
    lf = lambda x: C.lowpass_causal(x, 6.0, 200.0)
    X50 = resample_poly(T.channels(lf(a), lf(g)), 1, 4, axis=0)
    if lab is None:
        lab = movement_labels(gyr_rad, fs)
    lab50 = np.round(np.interp(np.arange(len(X50)) / 50.0, np.arange(len(lab)) / fs, lab)).astype(int)
    starts = T.window_starts(lab50)
    F, y = T.windows(X50, lab50, starts)
    return np.array(F, float).reshape(-1, 31), np.array(y, int)


# ------------------------------------------------------------------ Marpino
def marpino_read(path):
    """{sensor index: dict(acc [g], gyr [rad/s], sheet)} from one workbook; units as in the dataset README."""
    xl = pd.ExcelFile(path)
    out, notes = {}, []
    for k, sh in enumerate(xl.sheet_names):
        df = xl.parse(sh)
        cols = {re.sub(r'\s', '', str(c)).lower(): c for c in df.columns}
        def pick(prefix):
            got = {}
            for key, c in cols.items():
                m = re.match(prefix + r'_?read_?([xyz])(?:[_\-]?(\d+))?$', key)
                if m:
                    got.setdefault(int(m.group(2)) if m.group(2) else None, {})[m.group(1)] = c
            return got
        acc, gyr = pick('acc'), pick('gyro')
        for sid, ax in acc.items():
            if set(ax) != set('xyz') or sid not in gyr or set(gyr[sid]) != set('xyz'):
                continue
            idx = sid
            if idx is None:
                d = re.findall(r'(\d+)', str(sh))
                idx = int(d[-1]) if d and 1 <= int(d[-1]) <= 7 else k + 1
                if not (d and 1 <= int(d[-1]) <= 7):
                    notes.append(f'sheet "{sh}": sensor number taken from the sheet order ({idx})')
            a = df[[ax[c] for c in 'xyz']].apply(pd.to_numeric, errors='coerce').to_numpy(float) / 10000.0
            g = np.radians(df[[gyr[sid][c] for c in 'xyz']].apply(pd.to_numeric, errors='coerce').to_numpy(float) / 100.0)
            ok = np.isfinite(a).all(1) & np.isfinite(g).all(1)
            out[idx] = dict(acc=a[ok], gyr=g[ok], sheet=str(sh), n=int(ok.sum()))
    return out, notes


def marpino_group(path, root):
    rel = re.sub(r'[\s_\-]', '', os.path.relpath(path, root).replace('\\', '/').lower())
    for g, key in (('elderly', 'elderly'), ('young', 'young'), ('disability', 'disability'), ('long distance', 'longdistance'), ('marzia', 'marzia')):
        if key in rel:
            return g
    return 'other'


# ------------------------------------------------------------------ Caicedo et al. 2020 (Vicon Nexus CSV export)
def nexus_sections(path):
    """Sections of a Nexus CSV export: tables (Gait Cycle Parameters, Events) and time series
    (Joints, Model Outputs, Trajectories, ...) as {name: dict(rate, columns {group:component -> array}, units)}."""
    txt = open(path, encoding='utf-8-sig', errors='replace').read().splitlines()
    head = [l for l in txt[:12] if l.strip()]
    probe = head[2] if len(head) > 2 else (head[0] if head else '')
    sep = max([',', '\t', ';'], key=probe.count)                    # comma, tab or semicolon, whatever the export used
    if sep != ',':
        txt = [l.replace(',', ' ').replace(sep, ',') for l in txt]  # work in commas from here on
    txt = [l.replace('"', '') for l in txt]
    blocks, cur = [], []
    for ln in txt:
        if ln.strip().strip(',') == '':
            if cur:
                blocks.append(cur); cur = []
        else:
            cur.append(ln)
    if cur:
        blocks.append(cur)
    out = {}
    for b in blocks:
        name = b[0].split(',')[0].strip()
        try:
            rate = float(b[1].split(',')[0])
        except (IndexError, ValueError):
            rate = None
        if len(b) < 3:
            continue
        hdr = [h.strip() for h in b[2].split(',')]
        if hdr[:2] == ['Subject', 'Context'] or name in ('Gait Cycle Parameters', 'Events'):
            rows = [r.split(',') for r in b[3:]]
            width = len(hdr)
            rows = [(r + [''] * width)[:width] for r in rows]
            out[name] = dict(rate=rate, table=pd.DataFrame(rows, columns=hdr))
            continue
        # header rows run until the first row that starts with a frame number (layouts differ between exports)
        first = next((i for i in range(2, len(b)) if re.match(r'^\s*\d+\s*$', b[i].split(',')[0])), None)
        if first is None or first < 3:
            continue
        hdr_rows = [r.split(',') for r in b[2:first]]
        groups = hdr_rows[0]; comps = hdr_rows[1] if len(hdr_rows) > 1 else hdr_rows[0]
        units = hdr_rows[2] if len(hdr_rows) > 2 else []
        width = max(len(groups), len(comps))
        data = []
        for r in b[first:]:
            v = (r.split(',') + [''] * width)[:width]
            data.append([_num(x) for x in v])
        data = np.array(data, float)
        cols, g_cur = {}, ''
        for i in range(2, width):
            if i < len(groups) and groups[i].strip():
                g_cur = groups[i].strip().split(':')[-1]
            comp = comps[i].strip() if i < len(comps) else str(i)
            cols[f'{g_cur}:{comp}'] = data[:, i]
        out[name] = dict(rate=rate, frames=data[:, 0], columns=cols, units=[u.strip() for u in units])
    return out


def _num(x):
    try:
        return float(x)
    except ValueError:
        return np.nan


def nexus_markers(sec):
    tr = sec.get('Trajectories')
    if tr is None:
        return {}, None
    names = sorted({k.split(':')[0] for k in tr['columns']})
    M = {}
    for n in names:
        try:
            M[n] = np.c_[tr['columns'][f'{n}:X'], tr['columns'][f'{n}:Y'], tr['columns'][f'{n}:Z']] / 1000.0
        except KeyError:
            pass
    return M, tr['rate']


def _fill(x):
    df = pd.DataFrame(x).interpolate(limit_direction='both')
    return df.to_numpy(float)


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def valid_markers(M, min_share=0.8):
    """Markers that actually carry data (a marker can be listed in the header but be empty in walking trials:
    CGM medial markers are often used only in the static calibration)."""
    return {n: v for n, v in M.items() if np.isfinite(v).all(1).mean() >= min_share}


def tibia_signals(M, fs, side, implant_below=0.03, shank_frac=0.35, widths=None):
    """Tibia frame from the CGM2.3 markers (x anterior, y subject's left, z superior); virtual implant 3 cm below
    the knee centre and virtual shank IMU at 35 % of the shank length above the ankle centre:
    specific force [g] in the tibia frame and angular velocity [rad/s]. Lab vertical axis detected (z or y up).
    widths: (knee width, ankle width) in mm for this side, used when the medial markers are empty (CGM-style:
    joint centre = lateral marker moved inwards by half the width + the 7 mm marker radius)."""
    s = side
    V = valid_markers(M)
    empty = sorted(n for n in M if n.startswith(s) and n not in V)
    need = [s + 'KNE', s + 'ANK']
    if any(n not in V for n in need):
        return None, f'{side}: markers {[n for n in need if n not in V]} missing or empty (empty: {empty})'
    KNE, ANK = _fill(V[s + 'KNE']), _fill(V[s + 'ANK'])
    if s + 'KNM' in V and s + 'MED' in V:
        KNM, MED = _fill(V[s + 'KNM']), _fill(V[s + 'MED'])
        K, A = (KNE + KNM) / 2, (ANK + MED) / 2
        lat = KNE - KNM
        how = 'knee and ankle centres from lateral + medial markers'
    elif s + 'TIAP' in V or s + 'TIAD' in V:
        T = _fill(V[s + 'TIAP'] if s + 'TIAP' in V else V[s + 'TIAD'])
        kw, aw = widths if widths and all(np.isfinite(widths)) else (100.0, 70.0)
        K, A = KNE, ANK
        for _ in range(4):        # the anterior direction is measured from the joint centres, which need the lateral one
            zz = unit(K - A)
            ant = T - (K + A) / 2
            ant = unit(ant - np.sum(ant * zz, 1, keepdims=True) * zz)
            lat = unit(np.cross(ant, zz) * (1 if s == 'R' else -1))   # points laterally on both sides
            K = KNE - (kw / 2000.0 + 0.007) * lat
            A = ANK - (aw / 2000.0 + 0.007) * lat
        how = f'lateral markers + anterior tibia marker, centres from knee/ankle widths {kw:.0f}/{aw:.0f} mm (medial markers empty)'
    else:
        return None, f'{side}: medial markers and anterior tibia markers missing or empty (empty: {empty})'
    if np.isnan(K).any() or np.isnan(A).any():
        return None, f'{side}: gaps could not be filled'
    sos = butter(4, 10.0, fs=fs, output='sos')
    K, A, lat = sosfiltfilt(sos, K, axis=0), sosfiltfilt(sos, A, axis=0), sosfiltfilt(sos, lat, axis=0)
    z = unit(K - A)
    up_axis = int(np.argmax(np.abs(z.mean(0))))
    gvec = np.zeros(3); gvec[up_axis] = -9.81 * np.sign(z.mean(0)[up_axis])
    l = unit(lat - np.sum(lat * z, 1, keepdims=True) * z)
    y = l if s == 'L' else -l
    x = np.cross(y, z)
    R = np.stack([x, y, z], axis=2)                               # columns: tibia axes in the lab
    dt = 1.0 / fs
    def sf(p):
        acc = np.gradient(np.gradient(p, dt, axis=0), dt, axis=0)
        return np.einsum('nji,nj->ni', R, acc - gvec) / 9.81
    p_imp = K - implant_below * z
    p_sh = A + shank_frac * (K - A)
    Rd = np.gradient(R, dt, axis=0)
    W = np.einsum('nji,njk->nik', R, Rd)
    w = np.c_[W[:, 2, 1], W[:, 0, 2], W[:, 1, 0]]
    return dict(implant=sf(p_imp), shank=sf(p_sh), gyr=w, shank_len=float(np.median(np.linalg.norm(K - A, axis=1))),
                up_axis='xyz'[up_axis], how=how, K=K, A=A, R=R, p_imp=p_imp), None


def marker_speed(M, fs):
    """Walking speed [m/s] from the pelvis markers (or all markers): median horizontal speed of their centre."""
    names = [n for n in ('LASI', 'RASI', 'LPSI', 'RPSI') if n in M] or list(M)
    if not names or not fs:
        return float('nan')
    c = np.nanmean(np.stack([_fill(M[n]) for n in names]), axis=0)
    vert = int(np.argmin(np.nanstd(c, axis=0)))                       # the vertical axis moves least
    h = [i for i in range(3) if i != vert]
    v = np.linalg.norm(np.diff(c[:, h], axis=0), axis=1) * fs
    return float(np.nanmedian(v))


def caicedo_params(sec):
    tab = sec.get('Gait Cycle Parameters', {}).get('table')
    if tab is None or not {'Name', 'Value'} <= set(tab.columns):
        return {}
    out = {}
    for name in ('Walking Speed', 'Cadence', 'Stride Time', 'Double Support'):
        v = pd.to_numeric(tab.loc[tab['Name'] == name, 'Value'], errors='coerce').dropna()
        if len(v):
            out[name.lower().replace(' ', '_')] = float(v.mean())
    return out


# ------------------------------------------------------------------ models trained on all Camargo subjects
def train_shank_models(feat_dir, n_classes=4, cap=400, trees=150, seed=0):
    from sklearn.ensemble import RandomForestClassifier
    rng = np.random.default_rng(seed)
    feats = {os.path.splitext(os.path.basename(p))[0]: dict(np.load(p)) for p in sorted(glob.glob(os.path.join(feat_dir, '*.npz')))}
    def take(s, kind):
        F, y = feats[s][f'F_{kind}'], feats[s][f'y_{kind}']
        keep = y < n_classes
        F, y = F[keep], y[keep]
        idx = np.concatenate([rng.permutation(np.flatnonzero(y == c))[:cap] for c in range(n_classes)])
        return F[idx], y[idx]
    models = {}
    for name, parts in (('A_lf', ['real_lf']), ('B_lf', ['simhf_lf']), ('C_lf', ['real_lf', 'simhf_lf'])):
        pieces = [take(s, p) for s in feats for p in parts if f'F_{p}' in feats[s]]
        if not pieces:
            continue
        X = np.vstack([q[0] for q in pieces]); y = np.concatenate([q[1] for q in pieces])
        models[name] = RandomForestClassifier(trees, min_samples_leaf=2, class_weight='balanced_subsample',
                                              random_state=0, n_jobs=-1).fit(X, y)
    return models, sorted(feats)


# ------------------------------------------------------------------ on-device classifier (kneil_tinyml, C) via ctypes
def build_device_lib(tinyml_dir, out=None):
    """Compile the on-device classifier as a shared library (.so on Linux, .dll on Windows with MinGW-w64 gcc)."""
    import subprocess, tempfile, time
    out = out or os.path.join(tempfile.gettempdir(), f'libkneil_device_{int(time.time() * 1000)}' + ('.dll' if os.name == 'nt' else '.so'))
    flags = ['-static-libgcc'] if os.name == 'nt' else ['-fPIC']
    src = [os.path.join(tinyml_dir, 'src', f) for f in ('kneil_features.c', 'kneil_classifier.c', 'kneil_metrics.c')]
    r = subprocess.run(['gcc', '-O2', '-std=c99', '-shared', *flags, '-I' + os.path.join(tinyml_dir, 'include')] + src + ['-o', out, '-lm'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    lib = ctypes.CDLL(out)
    lib.kneil_classifier_init.argtypes = [ctypes.c_void_p]
    lib.kneil_classifier_push.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float]
    lib.kneil_classifier_push.restype = ctypes.c_int
    return lib


def device_classes(lib, stream_g):
    """Classes of every window the on-device classifier produces for a 50 Hz device-frame stream [g]."""
    buf = ctypes.create_string_buffer(1 << 17)
    lib.kneil_classifier_init(buf)
    out = []
    for x, y, z in np.clip(stream_g, -8.0, 8.0):
        c = lib.kneil_classifier_push(buf, float(x), float(y), float(z))
        if c >= 0:
            out.append(c)
    return out
