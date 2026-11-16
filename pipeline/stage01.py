"""
KNEIL virtual implant, stages 0 and 1 (Colab).  v1.0, Nov 2026
Stage 0: inventory of every dataset folder (found? format as expected? sensors, rates, units).
Stage 1: validation of the virtual implant (vimp.py):
   1a  Camargo: virtual implant from the REAL shank IMU vs the implant signal of the replay of the measured joint
       angles (same point, same frame). Variants: calibrated (per person), no calibration, no transfer.
   1b  Two sensors on the same tibia must give the same implant signal:
       KneE-PAD (tibialis anterior vs gastrocnemius sensor) and WearGait-PD (lateral shank vs ankle sensor).
All results go to <DATA_ROOT>/KNEIL_results/virtual_implant/.
"""
import glob, io, json, os, re, shutil, sys, time, traceback, zipfile
import numpy as np
import pandas as pd

import vimp as V

VERSION = 'stage01 1.4'
WG_NAME = re.compile(r'([A-Z]*(?:HC|PD)\d+)_(.+)\.csv$', re.I)   # full person id (e.g. HC100, WHC001, PD012) and task
wg_is_control = lambda pid: 'HC' in pid.upper()
TILT_OK = (-5.0, 35.0)                     # plausible mean forward lean of the tibia while moving (deg)
LP = 6.0                                   # the device's input low-pass (Hz); all comparisons after it


LOCAL_CACHE = '/content/kneil_cache'


def remount():
    """Re-mount Google Drive after 'Transport endpoint is not connected' (Colab only)."""
    try:
        from google.colab import drive
        print('  (Drive connection lost: remounting)', flush=True)
        drive.mount('/content/drive', force_remount=True)
        time.sleep(3)
        return True
    except Exception as e:
        print(f'  (remount failed: {e!r})', flush=True)
        return False


def with_retry(fn, what, tries=4):
    for k in range(tries):
        try:
            return fn()
        except OSError as e:
            if k == tries - 1:
                raise
            print(f'  {what}: {e!r} -> retry {k + 1}', flush=True)
            if getattr(e, 'errno', None) in (107, 5, 103, 110) or 'endpoint' in str(e):
                remount()
            time.sleep(5 * (k + 1))


def local_copy(path, sub=''):
    """Copy a Drive file to the local disk once (with retries); returns the local path."""
    d = os.path.join(LOCAL_CACHE, sub); os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, os.path.basename(path))
    if os.path.exists(dst):
        return dst
    def go():
        shutil.copyfile(path, dst + '.part'); os.replace(dst + '.part', dst)
    with_retry(go, f'copy {os.path.basename(path)}')
    return dst


def save_csv(df, path):
    with_retry(lambda: df.to_csv(path, index=False), f'save {os.path.basename(path)}')


class Tee:
    """Write to the notebook output and to a log file. Use: with Tee(path): ..."""
    """The log is written on the local disk and copied to Drive at the end (a Drive drop cannot crash it)."""
    def __init__(self, path):
        self.path = path; self.f = None; self.out = None
        os.makedirs(LOCAL_CACHE, exist_ok=True)
        self.local = os.path.join(LOCAL_CACHE, os.path.basename(path))
    def __enter__(self):
        self.out = sys.stdout
        if not os.path.exists(self.local) and os.path.exists(self.path):
            try:
                shutil.copyfile(self.path, self.local)
            except OSError:
                pass
        self.f = open(self.local, 'a', encoding='utf-8'); sys.stdout = self
        return self
    def __exit__(self, *exc):
        if exc[0] is not None:
            self.write(''.join(traceback.format_exception(*exc)))
        sys.stdout = self.out; self.f.close()
        try:
            with_retry(lambda: shutil.copyfile(self.local, self.path), 'copy the log to Drive')
        except OSError as e:
            print(f'log kept locally at {self.local} ({e!r})')
        return False
    def write(self, s):
        self.out.write(s); self.f.write(s); self.f.flush()
    def flush(self):
        self.out.flush(); self.f.flush()


def find_dir(root, *patterns):
    for p in patterns:
        hits = sorted(glob.glob(os.path.join(root, p)))
        if hits:
            return hits[0]
    return None


def walk_files(top, ext, limit=200000):
    out = []
    for dp, dn, fn in os.walk(top):
        out += [os.path.join(dp, f) for f in fn if f.lower().endswith(ext) and not f.startswith('~$')]
        if len(out) > limit:
            break
    return sorted(out)


def parse_time(col):
    """Numbers, or text such as '0 sec', '0.01 sec', '10 ms', '00:00:01.250'. Returns seconds and a note."""
    if pd.api.types.is_numeric_dtype(pd.Series(col)):
        return np.asarray(col, float), 'numeric'
    s = pd.Series(col).astype(str).str.strip()
    if s.str.contains(r'^\d+:\d+:\d+', regex=True).mean() > 0.5:
        return pd.to_timedelta(s, errors='coerce').dt.total_seconds().to_numpy(), 'hh:mm:ss'
    num = pd.to_numeric(s.str.extract(r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)')[0], errors='coerce').to_numpy(float)
    unit = s.str.extract(r'([a-zA-Z]+)\s*$')[0].dropna()
    u = unit.str.lower().mode().iloc[0] if len(unit) else ''
    if u in ('ms', 'msec', 'millisecond', 'milliseconds'):
        return num / 1000.0, f"text '{s.iloc[0]}' (ms)"
    return num, f"text '{s.iloc[0]}' ({u or 'no unit'}, read as s)"


def fs_from_time(t):
    t = np.asarray(t, float)
    dt = float(np.median(np.diff(t[np.isfinite(t)][:5000])))
    if dt <= 0:
        return None, 'time not increasing'
    if dt < 1.0:
        return 1.0 / dt, 's'
    return 1000.0 / dt, 'ms'


def to_g(acc):
    med = float(np.nanmedian(np.linalg.norm(acc, axis=1)))
    if 6.0 < med < 13.0:
        return acc / 9.81, 'm/s^2'
    return acc, 'g'


def to_rad(gyr):
    p99 = float(np.nanpercentile(np.linalg.norm(gyr, axis=1), 99))
    if p99 > 25.0:
        return np.radians(gyr), 'deg/s'
    return gyr, 'rad/s'


def fill(x):
    x = np.asarray(x, float)
    if not np.isnan(x).any():
        return x
    idx = np.arange(len(x))
    for j in range(x.shape[1]):
        ok = np.isfinite(x[:, j])
        x[:, j] = np.interp(idx, idx[ok], x[ok, j]) if ok.sum() > 1 else 0.0
    return x


# ---------------------------------------------------------------- readers
WG_SENSORS = ('R_LatShank', 'L_LatShank', 'R_Ankle', 'L_Ankle', 'R_MidLatThigh', 'L_MidLatThigh', 'R_Wrist', 'L_Wrist', 'LowerBack')


def wg_read(path, sensors=WG_SENSORS, nrows=None, cache=True):
    if cache and path.startswith('/content/drive'):
        path = local_copy(path, 'weargait')
    cols = pd.read_csv(path, nrows=0).columns
    tcol = next((c for c in cols if c.strip().lower() == 'time'), None)
    use = ([tcol] if tcol else []) + [c for c in cols if any(c.startswith(s + '_Acc_') or c.startswith(s + '_Gyr_') for s in sensors)]
    df = pd.read_csv(path, usecols=use, nrows=nrows)
    if tcol:
        tsec, tnote = parse_time(df[tcol].to_numpy())
        fs, tunit = fs_from_time(tsec)
        tunit = f'{tnote} -> {tunit}'
    else:
        fs, tunit = None, 'no time column'
    if not fs or not np.isfinite(fs):
        raise ValueError(f'cannot get the sampling rate from the time column ({tunit})')
    out, units = {}, {}
    for s in sensors:
        a = [f'{s}_Acc_{k}' for k in 'XYZ']; g = [f'{s}_Gyr_{k}' for k in 'XYZ']
        if all(c in df for c in a + g):
            acc, ua = to_g(fill(df[a].to_numpy(float))); gyr, ug = to_rad(fill(df[g].to_numpy(float)))
            out[s] = dict(acc=acc, gyr=gyr); units[s] = (ua, ug)
    return out, fs, dict(time_unit=tunit, units=units, n=len(df))


KP_FS = 148.148
KP_UNITS = {'R_thigh_front': 0, 'R_thigh_back': 1, 'R_shank_TA': 2, 'R_shank_GA': 3,
            'L_thigh_front': 4, 'L_thigh_back': 5, 'L_shank_TA': 6, 'L_shank_GA': 7}
KP_TASKS = {0: 'squat', 1: 'squat (weight on healthy leg)', 2: 'squat (injured leg in front)', 3: 'seated extension',
            4: 'seated extension (partial)', 5: 'seated extension (limb lifted)', 6: 'walking', 7: 'walking (knee not extended)',
            8: 'walking (extension + hip abduction)'}


def kp_members(zpath):
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if n.replace('\\', '/').endswith('imu.npy')]
    rows = []
    for n in names:
        m = re.search(r'Subject_(\d+)[/\\](\d+)[/\\]Trial_(\d+)', n)
        if m:
            rows.append(dict(member=n, subject=int(m.group(1)), label=int(m.group(2)), trial=int(m.group(3))))
    return pd.DataFrame(rows)


def kp_load(z, member):
    x = np.load(io.BytesIO(z.read(member)))
    if x.shape[0] != 48 and x.shape[1] == 48:
        x = x.T
    out = {}
    for name, u in KP_UNITS.items():
        acc, ua = to_g(x[6 * u:6 * u + 3].T.astype(float)); gyr, ug = to_rad(x[6 * u + 3:6 * u + 6].T.astype(float))
        out[name] = dict(acc=fill(acc), gyr=fill(gyr), units=(ua, ug))
    return out


# ---------------------------------------------------------------- stage 0
def inventory(root, out_dir):
    res = {}
    def rec(name, ok, **facts):
        res[name] = dict(status='OK' if ok else 'PROBLEM', **facts)
        print(f"{name:22s} {'OK     ' if ok else 'PROBLEM'} " + '; '.join(f'{k}: {v}' for k, v in facts.items()), flush=True)
    def guard(name, fn):
        try:
            fn()
        except Exception as e:
            rec(name, False, error=repr(e)[:300])
    def camargo():
        d = find_dir(root, 'Camargo*/Data', 'Camargo*')
        zips = sorted(f for f in os.listdir(d) if re.fullmatch(r'ab\d+\.zip', f, re.I)) if d else []
        rec('Camargo', len(zips) > 0, folder=d, subject_zips=len(zips))
    def weargait():
        d = find_dir(root, 'WearGait*')
        man = os.path.join(d, 'manifest.csv') if d else None
        files = walk_files(d, '.csv') if d else []
        data = [f for f in files if WG_NAME.search(os.path.basename(f))]
        tasks = sorted({WG_NAME.search(os.path.basename(f)).group(2) for f in data})
        people = sorted({WG_NAME.search(os.path.basename(f)).group(1).upper() for f in data})
        print('    WearGait-PD example file names:', [os.path.basename(f) for f in data[:3]] + [os.path.basename(f) for f in data if not re.match(r'(HC|PD)\d+_', os.path.basename(f), re.I)][:3], flush=True)
        sp = next((f for f in data if f.endswith('_SelfPace.csv')), None)
        S, fs, info = wg_read(sp, nrows=4000) if sp else ({}, None, {})
        rec('WearGait-PD', bool(data) and bool(S), folder=d, csv_files=len(data), people=len(people),
            controls=sum(wg_is_control(p) for p in people), parkinson=sum(not wg_is_control(p) for p in people),
            id_prefixes=sorted({re.match(r'[A-Z]*', p).group(0) for p in people}), tasks=tasks,
            sensors_found=sorted(S), fs_hz=round(fs, 2) if fs else None, time_unit=info.get('time_unit'),
            units={k: v for k, v in info.get('units', {}).items()}, manifest=bool(man and os.path.exists(man)))
    def kneepad():
        zp = None
        for d in (find_dir(root, 'Clement*'), find_dir(root, 'KneE*', 'ROAM*')):
            if d:
                hits = walk_files(d, '.zip')
                zp = hits[0] if hits else zp
        df = kp_members(zp) if zp else pd.DataFrame()
        shape = None
        if len(df):
            with zipfile.ZipFile(zp) as z:
                shape = list(np.load(io.BytesIO(z.read(df.member.iloc[0]))).shape)
        rec('KneE-PAD', len(df) > 0 and shape is not None and 48 in shape, zip=zp, trials=len(df),
            subjects=int(df.subject.nunique()) if len(df) else 0, labels=sorted(df.label.unique().tolist()) if len(df) else [],
            imu_shape=shape, fs_hz=KP_FS)
    def marpino():
        d = find_dir(root, 'Marpino*')
        x = walk_files(d, '.xlsx') if d else []
        rec('Marpino', len(x) > 0, folder=d, workbooks=len(x))
    def ceti():
        d = find_dir(root, 'CeTI*')
        zp = (walk_files(d, '.zip') or [None])[0] if d else None
        with zipfile.ZipFile(zp) as z:
            names = z.namelist()
            mot = [n for n in names if n.endswith('_motion.tsv')]; ch = [n for n in names if n.endswith('_channels.tsv')]
            js = [n for n in names if n.endswith('_motion.json')]
            chan = pd.read_csv(io.BytesIO(z.read(ch[0])), sep='\t') if ch else pd.DataFrame()
            meta = json.loads(z.read(js[0])) if js else {}
        types = chan['type'].value_counts().to_dict() if 'type' in chan else {}
        rec('CeTI-Age-Kinematics', bool(mot), zip=zp, motion_files=len(mot), channels_in_first=len(chan),
            channel_types=types, first_channels=chan['name'].head(12).tolist() if 'name' in chan else [],
            fs_hz=meta.get('SamplingFrequency'), tracking_systems=meta.get('TrackingSystemName'))
    def pamap2():
        d = find_dir(root, 'PAMAP2*')
        zp = (walk_files(d, '.zip') or [None])[0] if d else None
        with zipfile.ZipFile(zp) as z:
            dat = [n for n in z.namelist() if re.search(r'Protocol/subject\d+\.dat$', n)]
            first = z.read(dat[0])[:400000].decode(errors='ignore').splitlines()[:2000] if dat else []
        ncol = int(np.median([len(l.split()) for l in first])) if first else 0
        rec('PAMAP2', bool(dat) and ncol == 54, zip=zp, protocol_files=len(dat), columns=ncol, expected_columns=54)
    def mhealth():
        d = find_dir(root, 'MHEALTH*')
        logs = [f for f in walk_files(d, '.log') if 'subject' in f.lower()] if d else []
        x = pd.read_csv(logs[0], sep=r'\s+', header=None, nrows=2000) if logs else pd.DataFrame()
        rec('MHEALTH', bool(logs) and x.shape[1] == 24, folder=d, subject_logs=len(logs), columns=x.shape[1], expected_columns=24)
    def har():
        for name, pat in (('HAR70+', 'har70*'), ('HARTH', 'harth*')):
            d = find_dir(root, pat)
            c = walk_files(d, '.csv') if d else []
            rec(name, len(c) > 0, folder=d, csv_files=len(c))
    def caicedo():
        d = find_dir(root, 'Rodr*')
        c = [f for f in walk_files(d, '.csv') if re.search(r'Subject\d+_\d+', os.path.basename(f))] if d else []
        rec('Caicedo/Rodriguez', len(c) > 0, folder=d, walk_csvs=len(c))
    for name, fn in (('Camargo', camargo), ('WearGait-PD', weargait), ('KneE-PAD', kneepad), ('Marpino', marpino),
                     ('CeTI-Age-Kinematics', ceti), ('PAMAP2', pamap2), ('MHEALTH', mhealth), ('HAR', har), ('Caicedo', caicedo)):
        guard(name, fn)
    json.dump(res, open(os.path.join(out_dir, 'stage0_inventory.json'), 'w'), indent=1, default=str)
    return res


# ---------------------------------------------------------------- stage 1a: Camargo
def _lag(a, b, max_lag):
    from scipy.signal import correlate
    n = min(len(a), len(b)); a = a[:n] - a[:n].mean(); b = b[:n] - b[:n].mean()
    c = correlate(a, b, mode='full', method='fft')
    seg = c[n - 1 - max_lag:n + max_lag]
    return int(np.argmax(seg) - max_lag)


def moving_tilt(p, fs):
    """Mean sagittal tilt (deg, + = top of the tibia forward) of an implant signal over its moving samples."""
    a = V.lowpass(p, LP, fs)
    mv = np.convolve(np.linalg.norm(a - a.mean(0), axis=1), np.ones(int(fs)) / fs, mode='same') > 0.1
    a = a[mv] if mv.sum() > fs else a
    return float(np.degrees(np.arctan2(-a[:, 0].mean(), a[:, 2].mean())))


def plausible(p, fs):
    t = moving_tilt(p, fs)
    return dict(implant_tilt_deg=round(t, 1), plausible=bool(TILT_OK[0] <= t <= TILT_OK[1]))


def metrics(p, q, fs):
    a, b = V.lowpass(p, LP, fs), V.lowpass(q, LP, fs)
    r = [float(np.corrcoef(a[:, i], b[:, i])[0, 1]) for i in range(3)]
    ra = float(np.corrcoef(np.linalg.norm(a, axis=1), np.linalg.norm(b, axis=1))[0, 1])
    tilt = lambda u: np.degrees(np.arctan2(-u[:, 0].mean(), u[:, 2].mean()))
    return dict(rms_g=float(np.sqrt(((a - b) ** 2).sum(1).mean())), r_x=r[0], r_y=r[1], r_z=r[2], r_mag=ra,
                tilt_diff_deg=float(tilt(a) - tilt(b)))


def camargo_subject(subj, zip_path, local, modes, per_mode, log=print):
    import camargo_replay as C
    import mujoco
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    _extract(zip_path, subj, local, modes)
    m, info = C.model_for(subj)
    fs = C.FS_DATA
    imu_site, shin_site = m.site('imu').id, m.site('shin_r').id
    dpos = m.site_pos[imu_site] - m.site_pos[shin_site]              # tibia body frame: x anterior, y superior
    distance, anterior = float(dpos[1]), float(dpos[0])
    cols = lambda seg, kind: [f'{seg}_{kind}_{a}' for a in 'XYZ']
    z_up, cal_from = None, None
    for name, pik, pimu in C.find_trials(local, subj, 'levelground') + C.find_trials(local, subj, 'treadmill'):
        imu = C.load_table(pimu)
        z_up = V.calibrate_up(imu[cols('shank', 'Accel')].values, imu[cols('shank', 'Gyro')].values, fs)
        if z_up is not None:
            cal_from = name; break
    rows = []
    for mode in modes:
        trials = C.find_trials(local, subj, mode)
        for name, pik, pimu in trials[::max(1, len(trials) // per_mode)][:per_mode]:
            try:
                ik, imu = C.load_table(pik), C.load_table(pimu)
                t, Q = C.ik_to_Q(m, info, ik)
                o = C.replay(m, Q, fs, sensors=('acc_imu', 'gyr_shin_r'))
                n = min(len(t), len(imu))
                f, w = imu[cols('shank', 'Accel')].values[:n], imu[cols('shank', 'Gyro')].values[:n]
                tgt, ws = o['acc_imu'][:n], o['gyr_shin_r'][:n]
                L = _lag(np.linalg.norm(V.lowpass(w, LP, fs), axis=1), np.linalg.norm(V.lowpass(ws, LP, fs), axis=1), int(fs))
                sr, ss = (slice(L, None), slice(None, n - L)) if L >= 0 else (slice(None, n + L), slice(-L, None))
                f, w, tgt = f[sr], w[sr], tgt[ss]
                for variant, kw in (('calibrated', dict(z_up=z_up)), ('no calibration', dict(z_up=None)), ('no transfer', dict(z_up=z_up, distance=0.0, anterior=0.0))):
                    if variant == 'calibrated' and z_up is None:
                        continue
                    kw.setdefault('distance', distance); kw.setdefault('anterior', anterior)
                    p, g = V.virtual_implant(f, w, fs, **kw)
                    rows.append(dict(subject=subj, mode=mode, trial=name, variant=variant, lag=L, up_source=g['up_source'],
                                     seconds=round(len(f) / fs, 1), **plausible(p, fs), **metrics(p, tgt, fs)))
                r = [x for x in rows if x['trial'] == name and x['variant'] == ('calibrated' if z_up is not None else 'no calibration')][-1]
                log(f"  {subj} {name:32s} |a| r {r['r_mag']:.2f}, r x/z {r['r_x']:+.2f}/{r['r_z']:+.2f}, RMS {r['rms_g']:.3f} g, "
                    f"tilt {r['implant_tilt_deg']:+.0f} deg{'' if r['plausible'] else '  <- FLAGGED (implausible lean: sensor data suspect)'}")
            except Exception as e:
                log(f'  {subj} {name}: FAILED {e!r}')
    return rows, dict(subject=subj, calibration_trial=cal_from, distance_m=distance, anterior_m=anterior)


def _extract(zip_path, subj, local, modes, sensors=('ik', 'imu')):
    dst_root = os.path.join(local, subj); flag = os.path.join(dst_root, '.extracted.json')
    if os.path.exists(flag):
        return
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            parts = info.filename.replace('\\', '/').split('/')
            if info.is_dir() or len(parts) < 3 or not parts[-1].lower().endswith('.mat'):
                continue
            mode, sensor = parts[-3].lower(), parts[-2].lower()
            if mode in modes and sensor in sensors:
                dst = os.path.join(dst_root, mode, sensor, parts[-1]); os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(info) as src, open(dst + '.part', 'wb') as fo:
                    shutil.copyfileobj(src, fo, 1 << 20)
                os.replace(dst + '.part', dst); n += 1
    if not n:
        raise RuntimeError(f'{subj}: no <mode>/<ik|imu>/<trial>.mat files in {zip_path}')
    os.makedirs(dst_root, exist_ok=True); json.dump(dict(files=n), open(flag, 'w'))


def stage1a(root, out_dir, subjects, per_mode=4, modes=('treadmill', 'levelground', 'stair'), local='/content/camargo_local', keep_local=False):
    d = find_dir(root, 'Camargo*/Data', 'Camargo*')
    zips = {re.match(r'(ab\d+)', f, re.I).group(1).lower(): os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(r'ab\d+\.zip', f, re.I)}
    subs = sorted(zips) if subjects == 'all' else [s for s in subjects if s in zips]
    csv = os.path.join(out_dir, 'stage1a_camargo_trials.csv')
    done = pd.read_csv(csv) if os.path.exists(csv) else pd.DataFrame()
    geo = []
    for s in subs:
        if len(done) and (done.subject == s).any():
            print(f'{s}: already done (delete stage1a_camargo_trials.csv to redo)'); continue
        t0 = time.time()
        try:
            rows, g = camargo_subject(s, zips[s], local, modes, per_mode)
            geo.append(g)
            done = pd.concat([done, pd.DataFrame(rows)], ignore_index=True); done.to_csv(csv, index=False)
            print(f'{s}: {len({r["trial"] for r in rows})} trials in {time.time() - t0:.0f} s (calibrated from {g["calibration_trial"]})', flush=True)
        except Exception as e:
            print(f'{s}: FAILED {e!r}\n{traceback.format_exc()}')
        if not keep_local:
            shutil.rmtree(os.path.join(local, s), ignore_errors=True)
    if geo:
        json.dump(geo, open(os.path.join(out_dir, 'stage1a_geometry.json'), 'w'), indent=1)
    return done


# ---------------------------------------------------------------- stage 1b: two sensors on one tibia
KP_GEOM = {'TA': dict(distance=0.12, anterior=-0.03, medial=0.03), 'GA': dict(distance=0.14, anterior=0.07, medial=0.0)}
WG_GEOM = {'LatShank': dict(distance=0.18, anterior=0.0, medial=0.04), 'Ankle': dict(distance=0.33, anterior=0.0, medial=0.04)}


def stage1b_kneepad(root, out_dir, max_subjects=10, labels=(0, 6), log=print):
    zp = None
    d = find_dir(root, 'Clement*')
    if d:
        zp = (walk_files(d, '.zip') or [None])[0]
    if not zp:
        log('KneE-PAD zip not found'); return []
    csv = os.path.join(out_dir, 'stage1b_kneepad.csv')
    old = pd.read_csv(csv) if os.path.exists(csv) else pd.DataFrame()
    done_subj = set(old.subject.unique()) if len(old) else set()
    log(f'  copying the KneE-PAD zip to the local disk ({os.path.getsize(zp) / 1e9:.2f} GB, once)'); zp = local_copy(zp, 'kneepad')
    df = kp_members(zp)
    rows = old.to_dict(orient='records') if len(old) else []
    with zipfile.ZipFile(zp) as z:
        for s in sorted(df.subject.unique())[:max_subjects]:
            if s in done_subj:
                log(f'  KneE-PAD subject {s}: already done'); continue
            sd = df[df.subject == s]
            loaded = {r.member: kp_load(z, r.member) for r in sd[sd.label.isin(list(range(9)))].itertuples()}
            for side in 'RL':
                cal = {}
                for kind in ('TA', 'GA'):
                    nm = f'{side}_shank_{kind}'
                    f = np.vstack([v[nm]['acc'] for v in loaded.values()]); w = np.vstack([v[nm]['gyr'] for v in loaded.values()])
                    cal[kind] = V.calibrate_up(f, w, KP_FS)
                for r in sd[sd.label.isin(labels)].itertuples():
                    v = loaded[r.member]
                    try:
                        imp = {}
                        for kind in ('TA', 'GA'):
                            nm = f'{side}_shank_{kind}'
                            imp[kind], g = V.virtual_implant(v[nm]['acc'], v[nm]['gyr'], KP_FS, z_up=cal[kind], side=side, **KP_GEOM[kind])
                        pa, pb = plausible(imp['TA'], KP_FS), plausible(imp['GA'], KP_FS)
                        rows.append(dict(dataset='KneE-PAD', subject=s, side=side, task=KP_TASKS.get(r.label, r.label), trial=r.trial,
                                         pair='TA vs GA', calibrated=all(c is not None for c in cal.values()),
                                         tilt_a=pa['implant_tilt_deg'], tilt_b=pb['implant_tilt_deg'], plausible=pa['plausible'] and pb['plausible'],
                                         **metrics(imp['TA'], imp['GA'], KP_FS)))
                    except Exception as e:
                        log(f'  KneE-PAD S{s} {side} {r.member}: {e!r}')
            log(f'  KneE-PAD subject {s}: {sum(1 for x in rows if x["subject"] == s)} comparisons')
            save_csv(pd.DataFrame(rows), csv)
    return rows


def stage1b_weargait(root, out_dir, max_people=10, log=print):
    d = find_dir(root, 'WearGait*')
    files = [f for f in walk_files(d, '.csv') if WG_NAME.search(os.path.basename(f))] if d else []
    by = {}
    for f in files:
        p = WG_NAME.search(os.path.basename(f))
        by.setdefault(p.group(1).upper(), {})[p.group(2)] = f
    csv = os.path.join(out_dir, 'stage1b_weargait.csv')
    old = pd.read_csv(csv) if os.path.exists(csv) else pd.DataFrame()
    rows = old.to_dict(orient='records') if len(old) else []
    done_p = set(old.subject.astype(str)) if len(old) else set()
    people = sorted(by)
    pick = [p for p in people if wg_is_control(p)][:max_people // 2] + [p for p in people if not wg_is_control(p)][:max_people - max_people // 2]
    for p in pick:
        t = by[p]
        if 'SelfPace' not in t or p in done_p:
            if p in done_p:
                log(f'  WearGait-PD {p}: already done')
            continue
        try:
            sens = tuple(f'{s}_{k}' for s in 'RL' for k in ('LatShank', 'Ankle'))
            cal = {}
            if 'Balance' in t:
                B, fsb, _ = wg_read(t['Balance'], sensors=sens)
                cal = {k: V.calibrate_up(v['acc'], v['gyr'], fsb) for k, v in B.items()}
            for task in ('SelfPace', 'HurriedPace', 'TUG'):
                if task not in t:
                    continue
                S, fs, info = wg_read(t[task], sensors=sens)
                for side in 'RL':
                    a, b = f'{side}_LatShank', f'{side}_Ankle'
                    if a not in S or b not in S:
                        continue
                    pa, _ = V.virtual_implant(S[a]['acc'], S[a]['gyr'], fs, z_up=cal.get(a), side=side, **WG_GEOM['LatShank'])
                    pb, _ = V.virtual_implant(S[b]['acc'], S[b]['gyr'], fs, z_up=cal.get(b), side=side, **WG_GEOM['Ankle'])
                    qa, qb = plausible(pa, fs), plausible(pb, fs)
                    rows.append(dict(dataset='WearGait-PD', subject=p, side=side, task=task, trial=1, pair='LatShank vs Ankle',
                                     calibrated=cal.get(a) is not None and cal.get(b) is not None, tilt_a=qa['implant_tilt_deg'],
                                     tilt_b=qb['implant_tilt_deg'], plausible=qa['plausible'] and qb['plausible'], **metrics(pa, pb, fs)))
            log(f'  WearGait-PD {p}: {sum(1 for x in rows if x["subject"] == p)} comparisons')
            save_csv(pd.DataFrame(rows), csv)
        except Exception as e:
            log(f'  WearGait-PD {p}: FAILED {e!r}')
        finally:
            shutil.rmtree(os.path.join(LOCAL_CACHE, 'weargait'), ignore_errors=True)
    return rows


def stage1b_all(root, out_dir, kneepad_subjects=10, weargait_people=10):
    a = stage1b_kneepad(root, out_dir, max_subjects=kneepad_subjects)
    b = stage1b_weargait(root, out_dir, max_people=weargait_people)
    print(f'stage 1b: {len(a)} KneE-PAD and {len(b)} WearGait-PD comparisons saved')
    return a + b


# ---------------------------------------------------------------- summary
def summarise(out_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    a = pd.read_csv(os.path.join(out_dir, 'stage1a_camargo_trials.csv')) if os.path.exists(os.path.join(out_dir, 'stage1a_camargo_trials.csv')) else pd.DataFrame()
    parts = [pd.read_csv(os.path.join(out_dir, f)) for f in ('stage1b_kneepad.csv', 'stage1b_weargait.csv') if os.path.exists(os.path.join(out_dir, f))]
    b = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    summ = {}
    print('\n=== STAGE 1 SUMMARY (all after the 6 Hz low-pass; medians) ===')
    if len(a):
        bad = a[(a.variant == 'calibrated') & ~a.plausible.astype(bool)]
        print(f'\n1a  Camargo: virtual implant from the real shank IMU vs implant of the replayed joint angles')
        print(f'    flagged as implausible (left out below): {len(bad)} of {(a.variant == "calibrated").sum()} trials'
              + (f' -> {sorted(set(bad.subject + " " + bad["mode"]))}' if len(bad) else ''))
        flagged = set(bad.trial + bad.subject)
        a = a[~(a.trial + a.subject).isin(flagged)]
        t = a.groupby('variant')[['r_mag', 'r_x', 'r_y', 'r_z', 'rms_g', 'tilt_diff_deg']].median().round(3)
        t['trials'] = a.groupby('variant').size(); print(t.to_string())
        print('\n    calibrated, by mode:'); print(a[a.variant == 'calibrated'].groupby('mode')[['r_mag', 'r_x', 'r_z', 'rms_g']].median().round(3).to_string())
        summ['camargo'] = t.reset_index().to_dict(orient='records')
    if len(b):
        nb = int((~b.plausible.astype(bool)).sum()) if 'plausible' in b else 0
        print(f'\n1b  Two sensors on the same tibia (same implant point computed from each); flagged and left out: {nb} of {len(b)}')
        b = b[b.plausible.astype(bool)] if 'plausible' in b else b
        t2 = b.groupby(['dataset', 'pair', 'task'])[['r_mag', 'r_x', 'r_z', 'rms_g', 'tilt_diff_deg']].median().round(3)
        t2['n'] = b.groupby(['dataset', 'pair', 'task']).size(); print(t2.to_string())
        summ['two_sensor'] = t2.reset_index().to_dict(orient='records')
    json.dump(summ, open(os.path.join(out_dir, 'stage1_summary.json'), 'w'), indent=1, default=float)
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.2))
    if len(a):
        vs = ['calibrated', 'no calibration', 'no transfer']
        data = [a[a.variant == v]['r_mag'].dropna() for v in vs]
        ax[0].boxplot(data); ax[0].set_xticks(range(1, len(vs) + 1), [f'{v}\n(n={len(x)})' for v, x in zip(vs, data)]); ax[0].set_ylim(-0.2, 1.02)
        ax[0].set_ylabel('correlation of |a| with the replay implant'); ax[0].set_title('a  Camargo: real shank IMU -> implant', loc='left')
    if len(b):
        grp = list(b.groupby(['dataset', 'task']))
        ax[1].boxplot([g['r_mag'].dropna() for _, g in grp]); ax[1].set_xticks(range(1, len(grp) + 1), [f'{k[0]}\n{k[1]}' for k, _ in grp]); ax[1].set_ylim(-0.2, 1.02)
        ax[1].tick_params(axis='x', labelsize=7); ax[1].set_title('b  Two sensors on one tibia: |a| agreement', loc='left')
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, 'stage1_summary.png'), dpi=130)
    return summ
