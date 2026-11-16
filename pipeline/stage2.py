"""
KNEIL virtual implant, stage 2: implant-site data from real recordings, with labels.   v1.0, Nov 2026
  2a  HAR labeller: thigh + lower-back accelerometers -> activity every second; trained on HAR70+ and HARTH (video
      labels), validated leaving whole people out; used where a dataset has no per-second labels (WearGait-PD, Marpino).
  2b  WearGait-PD, 2c KneE-PAD, 2d Marpino, 2e PAMAP2 + MHEALTH: virtual implant from the shank (or ankle) IMU with
      ONE tibia frame per person and leg (standing -> up, walking -> forward; vimp.person_frame), 50 Hz, both legs
      where available; wrist signals kept for the smartwatch work (stage 4).
  2f  CeTI: look at one real file (segment positions and joint angles, not raw IMU) before writing its generator.
Output: <DATA_ROOT>/KNEIL_results/virtual_implant/stage2/<dataset>/<person>.npz plus stage2_index_<dataset>.csv
(one row per recording). Every part saves after each person and skips people already done.
npz keys: '<task>|<side>|implant' (N x 3, g, device frame x anterior / y left / z superior, 50 Hz),
'<task>|labels' (int16 per 50 Hz sample, codes in 'label_names'), '<task>|wrist_<R|L>' (N x 6: acc g, gyro rad/s).
"""
import glob, io, json, os, re, shutil, sys, time, traceback, zipfile
from fractions import Fraction
import numpy as np
import pandas as pd
from scipy.signal import resample_poly

import vimp as V
import stage01 as S1

VERSION = 'stage2 1.3'
FS = 50
LABELS = ['unknown', 'walking', 'shuffling', 'stairs_up', 'stairs_down', 'standing', 'sitting', 'lying', 'cycling', 'running',
          'transition', 'squat', 'seated_extension', 'tug', 'balance', 'other']
CODE = {n: i for i, n in enumerate(LABELS)}
WALK_TASKS = {'walking'}


# ---------------------------------------------------------------- helpers
def resample(x, fs_in, fs_out=FS):
    if abs(fs_in - fs_out) < 1e-6:
        return np.asarray(x, np.float32)
    fr = Fraction(fs_out / fs_in).limit_denominator(1000)
    return resample_poly(np.asarray(x, float), fr.numerator, fr.denominator, axis=0).astype(np.float32)


def resample_labels(codes, fs_in, n_out):
    idx = np.minimum((np.arange(n_out) * fs_in / FS).astype(int), len(codes) - 1)
    return np.asarray(codes)[idx].astype(np.int16)


class Store:
    """Per-dataset output: one npz per person (written locally, copied to Drive) and an index CSV; resumable."""
    def __init__(self, out_dir, dataset):
        self.dir = os.path.join(out_dir, 'stage2', dataset); os.makedirs(self.dir, exist_ok=True)
        self.index_path = os.path.join(out_dir, f'stage2_index_{dataset}.csv')
        self.index = pd.read_csv(self.index_path) if os.path.exists(self.index_path) else pd.DataFrame()
        self.dataset = dataset
    def done(self, person):
        return len(self.index) > 0 and (self.index.person.astype(str) == str(person)).any()
    def save(self, person, arrays, rows):
        local = os.path.join(S1.LOCAL_CACHE, 'stage2_out'); os.makedirs(local, exist_ok=True)
        fn = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(person)) + '.npz'
        arrays['label_names'] = np.array(LABELS)
        np.savez_compressed(os.path.join(local, fn), **arrays)
        S1.with_retry(lambda: shutil.copyfile(os.path.join(local, fn), os.path.join(self.dir, fn)), f'save {fn}')
        os.remove(os.path.join(local, fn))
        for r in rows:
            r.update(dataset=self.dataset, person=str(person), file=fn)
        self.index = pd.concat([self.index, pd.DataFrame(rows)], ignore_index=True)
        S1.save_csv(self.index, self.index_path)


def implant(f, w, fs, T, geom, side):
    p, _ = V.virtual_implant(f, w, fs, z_up=T[2], T=T, side=side, **geom)
    return resample(p, fs)


def walk_check(p50, codes50=None):
    """Mean forward lean while walking (deg) and whether it is plausible (stage 1 rule)."""
    x = p50 if codes50 is None or not (codes50 == CODE['walking']).sum() > FS * 3 else p50[codes50 == CODE['walking']]
    q = S1.plausible(x, FS)
    return q['implant_tilt_deg'], q['plausible']


# ---------------------------------------------------------------- 2a: HAR labeller (thigh + lower back)
HAR70_CODES = {1: 'walking', 3: 'shuffling', 4: 'stairs_up', 5: 'stairs_down', 6: 'standing', 7: 'sitting', 8: 'lying'}
HARTH_CODES = {1: 'walking', 2: 'running', 3: 'shuffling', 4: 'stairs_up', 5: 'stairs_down', 6: 'standing', 7: 'sitting', 8: 'lying',
               13: 'cycling', 14: 'cycling', 130: 'cycling', 140: 'cycling'}
HAR_CLASSES = ['walking', 'shuffling', 'stairs_up', 'stairs_down', 'standing', 'sitting', 'lying', 'cycling', 'running']
HAR_FEATURES = ['thigh_tilt', 'thigh_mean', 'thigh_std', 'thigh_energy', 'thigh_ac05', 'thigh_ac1', 'thigh_domf',
                'back_tilt', 'back_mean', 'back_std', 'back_energy', 'back_ac1']


def _ac(x, lag):
    x = x - x.mean()
    d = (x * x).sum()
    return float((x[:-lag] * x[lag:]).sum() / d) if d > 1e-12 and lag < len(x) else 0.0


def _domf(x):
    x = x - x.mean()
    P = np.abs(np.fft.rfft(x * np.hanning(len(x)), 512)) ** 2
    f = np.fft.rfftfreq(512, 1 / FS)
    m = (f >= 0.5) & (f <= 3.5)
    return float(f[m][np.argmax(P[m])]) if P[m].sum() > 1e-9 else 0.0


def _seg_feats(a, up, full):
    mag = np.linalg.norm(a, axis=1); m = a.mean(0)
    tilt = float(np.degrees(np.arccos(np.clip(m @ up / max(np.linalg.norm(m), 1e-9), -1, 1))))
    out = [tilt, float(mag.mean()), float(mag.std()), float(a.std(0).sum())]
    if full:
        out += [_ac(mag, FS // 2), _ac(mag, FS), _domf(mag)]
    else:
        out += [_ac(mag, FS)]
    return out


def har_windows(thigh, back, up_t, up_b, labels=None, W=2 * FS, H=FS):
    """thigh, back: (N, 3) in g at 50 Hz (back may be None). Returns features, labels (or None), window ends."""
    X, y, ends = [], [], []
    for s in range(0, len(thigh) - W + 1, H):
        f = _seg_feats(thigh[s:s + W], up_t, True)
        f += _seg_feats(back[s:s + W], up_b, False) if back is not None else [np.nan] * 5
        if labels is not None:
            v, c = np.unique(labels[s:s + W], return_counts=True); j = np.argmax(c)
            if c[j] < 0.6 * W or v[j] not in HAR_CLASSES:
                continue
            y.append(v[j])
        X.append(f); ends.append(s + W)
    return np.array(X, float).reshape(-1, len(HAR_FEATURES)), (np.array(y) if labels is not None else None), np.array(ends)


def _har_file(path, codes):
    df = pd.read_csv(path)
    fs = 50.0
    if 'timestamp' in df:
        ts = df['timestamp']
        if pd.api.types.is_numeric_dtype(ts):                                   # seconds, or milliseconds
            t = ts.to_numpy(float); dt = float(np.median(np.diff(t[:5000])))
            fs = 1.0 / (dt / 1000.0 if dt > 1.0 else dt)
        else:                                                                    # date and time text
            tt = pd.to_datetime(ts.iloc[:5000], errors='coerce')
            dt = float(np.median(np.diff((tt - tt.iloc[0]).dt.total_seconds().to_numpy())))
            fs = 1.0 / dt if dt > 0 else 50.0
    th = df[['thigh_x', 'thigh_y', 'thigh_z']].to_numpy(float); bk = df[['back_x', 'back_y', 'back_z']].to_numpy(float)
    lab = df['label'].map(lambda v: codes.get(int(v), 'unknown') if pd.notna(v) else 'unknown').to_numpy(str)
    th, bk = resample(th, fs), resample(bk, fs)
    lab = lab[np.minimum((np.arange(len(th)) * fs / FS).astype(int), len(lab) - 1)]
    return th, bk, lab, fs


def train_har_labeller(root, out_dir, log=print):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    from sklearn.metrics import f1_score, recall_score
    import joblib
    path = os.path.join(out_dir, 'stage2', 'har_labeller.joblib')
    if os.path.exists(path):
        log('HAR labeller: already trained (delete stage2/har_labeller.joblib to retrain)'); return joblib.load(path)
    Xs, ys, gs, fs_seen = [], [], [], set()
    for name, pat, codes in (('HAR70+', 'har70*', HAR70_CODES), ('HARTH', 'harth*', HARTH_CODES)):
        d = S1.find_dir(root, pat)
        for f in (S1.walk_files(d, '.csv') if d else []):
            try:
                th, bk, lab, fs = _har_file(S1.local_copy(f, 'har'), codes); fs_seen.add(round(fs))
                st = lab == 'standing'
                if st.sum() < FS:
                    log(f'  {os.path.basename(f)}: no labelled standing, skipped'); continue
                up_t, up_b = V.unit(th[st].mean(0)), V.unit(bk[st].mean(0))
                X, y, _ = har_windows(th, bk, up_t, up_b, lab)
                Xs.append(X); ys.append(y); gs += [f'{name}:{os.path.basename(f)}'] * len(y)
            except Exception as e:
                log(f'  {os.path.basename(f)}: {e!r}')
        shutil.rmtree(os.path.join(S1.LOCAL_CACHE, 'har'), ignore_errors=True)
    if not Xs:
        raise RuntimeError('HAR labeller: no usable HAR70+/HARTH files (see the lines above)')
    X, y, g = np.vstack(Xs), np.concatenate(ys), np.array(gs)
    log(f'HAR labeller: {len(y)} windows from {len(set(g))} people (rates seen {sorted(fs_seen)} Hz); classes {pd.Series(y).value_counts().to_dict()}')
    def model():
        return RandomForestClassifier(150, min_samples_leaf=2, class_weight='balanced_subsample', n_jobs=-1, random_state=0)
    k = min(5, len(set(g)))
    if k < 2:
        raise RuntimeError('HAR labeller needs at least 2 people')
    pred = np.empty(len(y), dtype=object)
    for tr, te in GroupKFold(k).split(X, y, g):
        pred[te] = model().fit(X[tr], y[tr]).predict(X[te])
    cls = [c for c in HAR_CLASSES if (y == c).any()]
    rec = recall_score(y, pred, labels=cls, average=None)
    log(f'  leave-people-out macro-F1 {f1_score(y, pred, labels=cls, average="macro"):.3f}; recall ' + ', '.join(f'{c} {r:.2f}' for c, r in zip(cls, rec)))
    thigh_only = np.r_[np.arange(7)]
    pred2 = np.empty(len(y), dtype=object)
    for tr, te in GroupKFold(k).split(X, y, g):
        pred2[te] = model().fit(X[tr][:, thigh_only], y[tr]).predict(X[te][:, thigh_only])
    log(f'  thigh only (when no back sensor): macro-F1 {f1_score(y, pred2, labels=cls, average="macro"):.3f}')
    M = dict(full=model().fit(X, y), thigh=model().fit(X[:, thigh_only], y), classes=cls, version=VERSION)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    local = os.path.join(S1.LOCAL_CACHE, 'har_labeller.joblib'); joblib.dump(M, local); S1.with_retry(lambda: shutil.copyfile(local, path), 'save labeller')
    return M


def label_seconds(M, thigh50, back50, up_t, up_b):
    """Per-50-Hz-sample label codes from the labeller (each second = the window ending at it)."""
    X, _, ends = har_windows(thigh50, back50, up_t, up_b)
    n = len(thigh50); codes = np.zeros(n, np.int16)
    if not len(X):
        return codes
    if back50 is None or np.isnan(X).any():
        pred = M['thigh'].predict(X[:, :7])
    else:
        pred = M['full'].predict(X)
    for e, c in zip(ends, pred):
        codes[max(0, e - FS):e] = CODE.get(c, 0)
    codes[:max(0, ends[0] - FS)] = CODE.get(pred[0], 0)
    return codes


# ---------------------------------------------------------------- 2b: WearGait-PD
WG_TASK_LABEL = {'Balance': 'balance', 'SelfPace': 'walking', 'HurriedPace': 'walking', 'TandemGait': 'walking', 'TUG': 'tug',
                 'SelfPace_matTURN': 'walking'}


def gen_weargait(root, out_dir, M, max_people=None, log=print):
    st = Store(out_dir, 'WearGait-PD')
    d = S1.find_dir(root, 'WearGait*')
    by = {}
    for f in (S1.walk_files(d, '.csv') if d else []):
        m = S1.WG_NAME.search(os.path.basename(f))
        if m and not m.group(2).endswith('_mat'):
            by.setdefault(m.group(1).upper(), {})[m.group(2)] = f
    people = sorted(by)[:max_people] if max_people else sorted(by)
    sens = ('R_LatShank', 'L_LatShank', 'R_MidLatThigh', 'L_MidLatThigh', 'LowerBack', 'R_Wrist', 'L_Wrist')
    for p in people:
        if st.done(p):
            continue
        t0 = time.time()
        try:
            data = {}
            for task, f in by[p].items():
                if task in WG_TASK_LABEL:
                    data[task] = S1.wg_read(f, sensors=sens)
            if not data:
                continue
            fs = next(iter(data.values()))[1]
            frames = {}
            for side in 'RL':
                k = f'{side}_LatShank'
                stand = [(data[t][0][k]['acc'], data[t][0][k]['gyr']) for t in ('Balance', 'TUG') if t in data and k in data[t][0]]
                walk = [(data[t][0][k]['acc'], data[t][0][k]['gyr']) for t in ('SelfPace', 'HurriedPace') if t in data and k in data[t][0]]
                frames[side] = V.person_frame(stand, walk, fs)
            ups = {}
            if 'Balance' in data:
                B = data['Balance'][0]
                for k in ('R_MidLatThigh', 'L_MidLatThigh', 'LowerBack'):
                    if k in B:
                        ups[k] = V.calibrate_up(B[k]['acc'], B[k]['gyr'], fs)
            thigh_k = 'R_MidLatThigh' if ups.get('R_MidLatThigh') is not None else ('L_MidLatThigh' if ups.get('L_MidLatThigh') is not None else None)
            arrays, rows = {}, []
            for task, (Sd, fs_t, info) in data.items():
                codes = None
                if thigh_k and thigh_k in Sd:
                    back = resample(Sd['LowerBack']['acc'], fs_t) if 'LowerBack' in Sd and ups.get('LowerBack') is not None else None
                    codes = label_seconds(M, resample(Sd[thigh_k]['acc'], fs_t), back, ups[thigh_k], ups.get('LowerBack'))
                    arrays[f'{task}|labels'] = codes
                for wk in ('R_Wrist', 'L_Wrist'):
                    if wk in Sd:
                        arrays[f'{task}|wrist_{wk[0]}'] = resample(np.c_[Sd[wk]['acc'], Sd[wk]['gyr']], fs_t)
                for side in 'RL':
                    k = f'{side}_LatShank'; T, note = frames[side]
                    if k not in Sd or T is None:
                        continue
                    p50 = implant(Sd[k]['acc'], Sd[k]['gyr'], fs_t, T, S1.WG_GEOM['LatShank'], side)
                    arrays[f'{task}|{side}|implant'] = p50
                    tilt, ok = walk_check(p50, codes) if WG_TASK_LABEL[task] == 'walking' else (np.nan, True)
                    first = not any(r['task'] == task for r in rows)                  # label time counted once per task
                    lab = pd.Series(codes).map(lambda c: LABELS[c]).value_counts(normalize=True).round(3).to_dict() if codes is not None and first else {}
                    rows.append(dict(group='control' if S1.wg_is_control(p) else 'parkinson', task=task, task_label=WG_TASK_LABEL[task], side=side,
                                     seconds=round(len(p50) / FS, 1), walk_tilt_deg=tilt, plausible=ok, frame=note,
                                     label_source='HAR labeller' if codes is not None else 'task only', label_mix=json.dumps(lab)))
            st.save(p, arrays, rows)
            log(f'  WearGait-PD {p}: {len(rows)} recordings, {sum(r["seconds"] for r in rows) / 60:.1f} min, '
                f'{sum(not r["plausible"] for r in rows)} flagged ({time.time() - t0:.0f} s)')
        except Exception as e:
            log(f'  WearGait-PD {p}: FAILED {e!r}')
        finally:
            shutil.rmtree(os.path.join(S1.LOCAL_CACHE, 'weargait'), ignore_errors=True)
    return st.index


# ---------------------------------------------------------------- 2c: KneE-PAD
KP_LABEL = {0: 'squat', 1: 'squat', 2: 'squat', 3: 'seated_extension', 4: 'seated_extension', 5: 'seated_extension',
            6: 'walking', 7: 'walking', 8: 'walking'}


def gen_kneepad(root, out_dir, log=print):
    st = Store(out_dir, 'KneE-PAD')
    d = S1.find_dir(root, 'Clement*')
    zp = (S1.walk_files(d, '.zip') or [None])[0] if d else None
    if not zp:
        log('KneE-PAD zip not found'); return st.index
    zp = S1.local_copy(zp, 'kneepad')
    df = S1.kp_members(zp)
    check = []
    with zipfile.ZipFile(zp) as z:
        for s in sorted(df.subject.unique()):
            if st.done(s):
                continue
            try:
                sd = df[df.subject == s]
                T = {r.member: S1.kp_load(z, r.member) for r in sd.itertuples()}
                short = [m for m, v in T.items() if len(v['R_shank_TA']['acc']) < S1.KP_FS]
                if short:
                    log(f'  KneE-PAD subject {s}: {len(short)} recordings shorter than 1 s skipped')
                    sd = sd[~sd.member.isin(short)]
                arrays, rows = {}, []
                for side in 'RL':
                    frames = {}
                    for kind in ('TA', 'GA'):
                        nm = f'{side}_shank_{kind}'
                        order = sd.assign(o=sd.label.map({0: 0, 1: 0, 2: 0, 6: 1, 7: 1, 8: 1}).fillna(2)).sort_values('o').member
                        stand = [(T[m][nm]['acc'], T[m][nm]['gyr']) for m in order]          # trials that start standing first
                        walk = [(T[m][nm]['acc'], T[m][nm]['gyr']) for m in sd[sd.label >= 6].member]
                        frames[kind] = V.person_frame(stand, walk, S1.KP_FS)
                    for r in sd.itertuples():
                        v = T[r.member]; key = f'{S1.KP_TASKS[r.label]} #{r.trial}'
                        TA, note = frames['TA']
                        if TA is None:
                            continue
                        p50 = implant(v[f'{side}_shank_TA']['acc'], v[f'{side}_shank_TA']['gyr'], S1.KP_FS, TA, S1.KP_GEOM['TA'], side)
                        arrays[f'{key}|{side}|implant'] = p50
                        arrays[f'{key}|labels'] = np.full(len(p50), CODE[KP_LABEL[r.label]], np.int16)
                        tilt, ok = walk_check(p50) if KP_LABEL[r.label] == 'walking' else (np.nan, True)
                        rows.append(dict(group='knee pathology', task=key, task_label=KP_LABEL[r.label], side=side, seconds=round(len(p50) / FS, 1),
                                         walk_tilt_deg=tilt, plausible=ok, frame=note, label_source='task'))
                        if frames['GA'][0] is not None and r.label in (0, 6):          # stage 1b re-check with person frames
                            pb, _ = V.virtual_implant(v[f'{side}_shank_GA']['acc'], v[f'{side}_shank_GA']['gyr'], S1.KP_FS, z_up=frames['GA'][0][2],
                                                      T=frames['GA'][0], side=side, **S1.KP_GEOM['GA'])
                            pa, _ = V.virtual_implant(v[f'{side}_shank_TA']['acc'], v[f'{side}_shank_TA']['gyr'], S1.KP_FS, z_up=TA[2], T=TA,
                                                      side=side, **S1.KP_GEOM['TA'])
                            check.append(dict(subject=s, side=side, task=KP_LABEL[r.label], **S1.metrics(pa, pb, S1.KP_FS)))
                st.save(s, arrays, rows)
                log(f'  KneE-PAD subject {s}: {len(rows)} recordings, {sum(r["seconds"] for r in rows) / 60:.1f} min')
            except Exception as e:
                log(f'  KneE-PAD subject {s}: FAILED {e!r}')
    if check:
        c = pd.DataFrame(check)
        p = os.path.join(out_dir, 'stage2_kneepad_twosensor_recheck.csv')
        c = pd.concat([pd.read_csv(p), c], ignore_index=True) if os.path.exists(p) else c
        S1.save_csv(c, p)
    return st.index


# ---------------------------------------------------------------- 2d: Marpino
MP_SENS = {1: 'R_foot', 2: 'R_shank', 3: 'R_thigh', 4: 'L_thigh', 5: 'L_shank', 6: 'L_foot', 7: 'back'}
MP_GEOM = dict(distance=0.20, anterior=0.0, medial=0.04)


def mp_read(path):
    df = pd.read_excel(S1.local_copy(path, 'marpino'), sheet_name=0)
    df.columns = [re.sub(r'\s', '', str(c)).lower() for c in df.columns]
    out = {}
    for k, nm in MP_SENS.items():
        a = [f'acc_read_{x}_{k}' for x in 'xyz']; g = [f'gyro_read_{x}_{k}' for x in 'xyz']
        if all(c in df for c in a + g):
            acc = S1.fill(df[a].to_numpy(float) / 10000.0); gyr = S1.fill(np.radians(df[g].to_numpy(float) / 100.0))
            if np.nanmedian(np.linalg.norm(acc, axis=1)) > 0.5:
                out[nm] = dict(acc=acc, gyr=gyr)
    return out, 100.0


def gen_marpino(root, out_dir, M, log=print):
    st = Store(out_dir, 'Marpino')
    d = S1.find_dir(root, 'Marpino*')
    for f in (S1.walk_files(d, '.xlsx') if d else []):
        rel = os.path.relpath(f, d); person = re.sub(r'[\\/]+', '__', os.path.splitext(rel)[0])
        if st.done(person):
            continue
        try:
            S, fs = mp_read(f)
            group = next((g for g in ('Elderly', 'Young', 'LongDistance', 'Marzia', 'Disability') if g.lower() in rel.lower().replace(' ', '')), 'other')
            arrays, rows = {}, []
            codes = None
            if 'R_thigh' in S:
                up_t = V.calibrate_up(S['R_thigh']['acc'], S['R_thigh']['gyr'], fs)
                up_b = V.calibrate_up(S['back']['acc'], S['back']['gyr'], fs) if 'back' in S else None
                if up_t is not None:
                    codes = label_seconds(M, resample(S['R_thigh']['acc'], fs), resample(S['back']['acc'], fs) if up_b is not None else None, up_t, up_b)
                    arrays['walk|labels'] = codes
            for side in 'RL':
                k = f'{side}_shank'
                if k not in S:
                    continue
                T, note = V.person_frame([(S[k]['acc'], S[k]['gyr'])], [(S[k]['acc'], S[k]['gyr'])], fs)
                if T is None:
                    continue
                p50 = implant(S[k]['acc'], S[k]['gyr'], fs, T, MP_GEOM, side)
                arrays[f'walk|{side}|implant'] = p50
                tilt, ok = walk_check(p50, codes)
                rows.append(dict(group=group, task='walk', task_label='walking', side=side, seconds=round(len(p50) / FS, 1), walk_tilt_deg=tilt,
                                 plausible=ok, frame=note, label_source='HAR labeller' if codes is not None else 'task only'))
            if rows:
                st.save(person, arrays, rows)
        except Exception as e:
            log(f'  Marpino {os.path.basename(f)}: FAILED {e!r}')
        finally:
            shutil.rmtree(os.path.join(S1.LOCAL_CACHE, 'marpino'), ignore_errors=True)
    log(f'  Marpino: {st.index.person.nunique() if len(st.index) else 0} recordings done')
    return st.index


# ---------------------------------------------------------------- 2e: PAMAP2 and MHEALTH (own per-sample labels)
PAMAP_ACT = {1: 'lying', 2: 'sitting', 3: 'standing', 4: 'walking', 5: 'running', 6: 'cycling', 7: 'walking', 12: 'stairs_up',
             13: 'stairs_down', 0: 'unknown'}
MH_ACT = {1: 'standing', 2: 'sitting', 3: 'lying', 4: 'walking', 5: 'stairs_up', 6: 'other', 7: 'other', 8: 'squat', 9: 'cycling',
          10: 'running', 11: 'running', 12: 'other', 0: 'unknown'}
ANKLE_GEOM = dict(distance=0.36, anterior=0.0, medial=0.0)


def _gen_labelled(st, person, ankle_f, ankle_w, wrist, fs, act, side, group, log):
    codes_src = np.array([CODE.get(a, CODE['other']) for a in act], np.int16)
    stand = codes_src == CODE['standing']; walk = codes_src == CODE['walking']
    if stand.sum() < 2 * fs or walk.sum() < 5 * fs:
        log(f'  {st.dataset} {person}: skipped ({stand.sum() / fs:.0f} s labelled standing, {walk.sum() / fs:.0f} s walking)'); return
    bias = np.median(ankle_w[stand], axis=0)                       # gyroscope offset while standing still
    ankle_w = ankle_w - bias
    z_up = V.unit(np.median(ankle_f[stand], axis=0))              # the labelled standing gives 'up' directly
    note = f'labelled standing ({stand.sum() / fs:.0f} s, gyro offset {np.degrees(np.linalg.norm(bias)):.1f} deg/s removed) + walking'
    codes = None
    for gsign in (1.0, -1.0):                                       # a backward walking lean = gyro sign opposite to the accelerometer
        T = V.tibia_frame_pca(gsign * ankle_w[walk], fs, z_up)
        p50 = implant(ankle_f, gsign * ankle_w, fs, T, ANKLE_GEOM, side)
        codes = resample_labels(codes_src, fs, len(p50))
        tilt, ok = walk_check(p50, codes)
        if tilt > -3.0:
            break
    if gsign < 0:
        note += '; gyroscope sign inverted (walking leaned backward with the original sign)'
        log(f'  {st.dataset} {person}: gyroscope sign inverted (original sign gave a backward walking lean)')
    arrays = {f'all|{side}|implant': p50, 'all|labels': codes}
    if wrist is not None:
        arrays[f'all|wrist_{wrist[0]}'] = resample(wrist[1], fs)[:len(p50)]
    tilt, ok = walk_check(p50, codes)
    mix = pd.Series(codes).map(lambda c: LABELS[c]).value_counts(normalize=True).round(3).to_dict()
    st.save(person, arrays, [dict(group=group, task='protocol', task_label='mixed', side=side, seconds=round(len(p50) / FS, 1), walk_tilt_deg=tilt,
                                  plausible=ok, frame=note, label_source='dataset labels', label_mix=json.dumps(mix))])
    log(f'  {st.dataset} {person}: {len(p50) / FS / 60:.1f} min, walking tilt {tilt:+.0f} deg{"" if ok else " FLAGGED"}')


def gen_pamap2(root, out_dir, log=print):
    st = Store(out_dir, 'PAMAP2')
    d = S1.find_dir(root, 'PAMAP2*')
    zp = (S1.walk_files(d, '.zip') or [None])[0] if d else None
    if not zp:
        log('PAMAP2 zip not found'); return st.index
    zp = S1.local_copy(zp, 'pamap2')
    with zipfile.ZipFile(zp) as z:
        for m in sorted(n for n in z.namelist() if re.search(r'Protocol/subject\d+\.dat$', n)):
            person = re.search(r'subject(\d+)', m).group(1)
            if st.done(person):
                continue
            try:
                X = pd.read_csv(io.BytesIO(z.read(m)), sep=r'\s+', header=None).to_numpy(float)
                act = [PAMAP_ACT.get(int(a), 'other') for a in X[:, 1]]
                ank_f, _ = S1.to_g(S1.fill(X[:, 38:41])); ank_w, _ = S1.to_rad(S1.fill(X[:, 44:47]))
                hf, _ = S1.to_g(S1.fill(X[:, 4:7])); hw, _ = S1.to_rad(S1.fill(X[:, 10:13]))
                _gen_labelled(st, person, ank_f, ank_w, ('H', np.c_[hf, hw]), 100.0, act, 'R', 'adult', log)
            except Exception as e:
                log(f'  PAMAP2 {person}: FAILED {e!r}')
    return st.index


def gen_mhealth(root, out_dir, log=print):
    st = Store(out_dir, 'MHEALTH')
    d = S1.find_dir(root, 'MHEALTH*')
    for f in [f for f in (S1.walk_files(d, '.log') if d else []) if 'subject' in f.lower()]:
        person = re.search(r'subject(\d+)', os.path.basename(f)).group(1)
        if st.done(person):
            continue
        try:
            X = pd.read_csv(S1.local_copy(f, 'mhealth'), sep=r'\s+', header=None).to_numpy(float)
            act = [MH_ACT.get(int(a), 'other') for a in X[:, 23]]
            ank_f, _ = S1.to_g(S1.fill(X[:, 5:8])); ank_w, _ = S1.to_rad(S1.fill(X[:, 8:11]))
            wf, _ = S1.to_g(S1.fill(X[:, 14:17])); ww, _ = S1.to_rad(S1.fill(X[:, 17:20]))
            _gen_labelled(st, person, ank_f, ank_w, ('R', np.c_[wf, ww]), 50.0, act, 'L', 'adult', log)
        except Exception as e:
            log(f'  MHEALTH {person}: FAILED {e!r}')
        finally:
            shutil.rmtree(os.path.join(S1.LOCAL_CACHE, 'mhealth'), ignore_errors=True)
    return st.index


# ---------------------------------------------------------------- 2f: CeTI look
def _ceti_read(z, member, nrows=None):
    """CeTI motion.tsv: header row or not, values to numbers."""
    raw = z.read(member)
    first = raw.split(b'\n', 1)[0].decode(errors='ignore').split('\t')
    has_header = sum(pd.to_numeric(pd.Series(first), errors='coerce').isna()) > len(first) / 2
    x = pd.read_csv(io.BytesIO(raw), sep='\t', header=0 if has_header else None, nrows=nrows)
    return x.apply(pd.to_numeric, errors='coerce'), has_header


def inspect_ceti(root, out_dir, log=print):
    d = S1.find_dir(root, 'CeTI*')
    zp = (S1.walk_files(d, '.zip') or [None])[0] if d else None
    if not zp:
        log('CeTI zip not found'); return
    zp = S1.local_copy(zp, 'ceti')
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        mot = sorted(n for n in names if n.endswith('_motion.tsv'))
        tasks = sorted({re.search(r'task-([^_]+)', n).group(1) for n in mot if re.search(r'task-([^_]+)', n)})
        subs = sorted({re.search(r'sub-([^_/]+)', n).group(1) for n in mot if re.search(r'sub-([^_/]+)', n)})
        log(f'CeTI: {len(mot)} motion files, {len(subs)} participants (e.g. {subs[:6]}), {len(tasks)} tasks')
        info = {}
        for t in tasks:
            js = next((n for n in names if f'task-{t}_' in n and n.endswith('_motion.json')), None)
            m = json.loads(z.read(js)) if js else {}
            info[t] = dict(name=m.get('TaskName', ''), description=str(m.get('TaskDescription') or m.get('Instructions') or '')[:110],
                           fs=m.get('SamplingFrequency'), files=sum(f'task-{t}_' in n for n in mot))
        log('  tasks:\n' + pd.DataFrame(info).T.to_string())
        pick = next((t for t, v in info.items() if re.search(r'walk', v['name'] + v['description'], re.I)), 'w01' if 'w01' in tasks else tasks[0])
        member = next(n for n in mot if f'task-{pick}_' in n)
        ch = pd.read_csv(io.BytesIO(z.read(member.replace('_motion.tsv', '_channels.tsv'))), sep='\t')
        x, hdr = _ceti_read(z, member, nrows=6000)
        if not hdr and 'name' in ch and len(ch) == x.shape[1]:
            x.columns = ch['name'].tolist()
        log(f'  example (task {pick}): {member}\n  {x.shape[1]} columns, header row: {hdr}; channel table columns {list(ch.columns)}')
        seg = r'(?:Pelvis|Hips|RightUpperLeg|RightLowerLeg|RightFoot|RightHand|RightForeArm|RightKnee|LeftLowerLeg|LeftFoot)'
        if 'name' in ch:
            log('  channel table (leg and hand segments):\n' + ch[ch['name'].astype(str).str.contains(seg)].to_string(index=False)[:6000])
        tcol = next((c for c in x.columns if 'time' in str(c).lower()), None)
        if tcol is not None:
            dt = np.nanmedian(np.diff(x[tcol].to_numpy(float)))
            log(f'  time column {tcol!r}: median step {dt:g} (-> {1000 / dt if dt > 1 else 1 / dt:.1f} Hz if {"ms" if dt > 1 else "s"})')
        keep = [c for c in x.columns if re.search(seg, str(c))]
        st = x[keep].agg(['mean', 'std', 'min', 'max']).T.round(3)
        log('  per-channel statistics (first 6000 samples):\n' + st.to_string())
        pv = [c for c in x.columns if re.search(r'Pelvis.*position', str(c))]
        if pv:
            log('  pelvis position means (the vertical axis is the one near 0.9-1.1 m when standing): ' + str(x[pv].mean().round(3).to_dict()))
        st.to_csv(os.path.join(out_dir, 'stage2_ceti_example_channels.csv'))
        pd.DataFrame(info).T.to_csv(os.path.join(out_dir, 'stage2_ceti_tasks.csv'))


# ---------------------------------------------------------------- 2g: CeTI (segment positions from the suit)
CETI_TASK = {'w': 'walking', 's': 'sit_to_stand', 'o': 'walking', 'e': 'lift_from_floor', 'r': 'reaching', 'g': 'arm_task',
             'h': 'arm_task', 'u': 'arm_task', 'c': 'calibration'}


def ceti_frame_signals(X, units, fs=100.0, below=0.025, anterior=0.005, forward_sign=None):
    """X: DataFrame with <Segment>_position_<x|y|z>. Returns implant specific force (device frame, g) per leg,
    per-sample codes from the pelvis (height -> sitting, speed -> walking), wrist signals (world frame) and notes."""
    sc = {'cm': 0.01, 'mm': 0.001, 'm': 1.0}.get(str(units).strip().lower(), 0.01)
    P = lambda seg: X[[f'{seg}_position_{a}' for a in 'xyz']].to_numpy(float) * sc
    pel = S1.fill(P('Pelvis'))
    feet = (S1.fill(P('RightFoot')) + S1.fill(P('LeftFoot'))) / 2
    above = np.median(pel - feet, axis=0)                         # the pelvis is ~0.9 m above the feet along 'up'
    v = int(np.argmax(np.abs(above)))
    e_up = np.zeros(3); e_up[v] = np.sign(above[v])
    lp = lambda x: V.lowpass(S1.fill(x), 8.0, fs)
    h = pel @ e_up; hor = pel - np.outer(h, e_up)
    vel = np.gradient(V.lowpass(hor, 1.0, fs), 1 / fs, axis=0); speed = np.linalg.norm(vel, axis=1)
    walking = speed > 0.25
    out, notes = {}, dict(vertical_axis=('+' if e_up[v] > 0 else '-') + 'xyz'[v], scale_to_m=sc)
    hipR, hipL = lp(P('RightUpperLeg')), lp(P('LeftUpperLeg'))
    right = hipR - hipL
    for side, S in (('R', 'Right'), ('L', 'Left')):
        K, A = lp(P(f'{S}LowerLeg')), lp(P(f'{S}Foot'))
        z = V.unit(K - A)
        r = right - np.sum(right * z, 1, keepdims=True) * z
        y = -V.unit(r)                                             # device y = subject's left
        x = np.cross(y, z)
        # forward = the direction the person walks: does not depend on the handedness of the lab coordinates
        if walking.sum() > 3 * fs:
            sgn = np.sign(np.sum(np.sum(vel[walking] * x[walking], 1)))
        else:
            sgn = forward_sign if forward_sign is not None else 1.0
        x = sgn * x
        notes[f'forward_sign_{side}'] = float(sgn); notes['forward_from'] = 'walking' if walking.sum() > 3 * fs else 'person/default'
        p = K - below * z + anterior * x
        acc = np.gradient(np.gradient(p, 1 / fs, axis=0), 1 / fs, axis=0)
        f = (acc + 9.81 * e_up) / 9.81
        out[side] = np.stack([np.sum(f * x, 1), np.sum(f * y, 1), np.sum(f * z, 1)], axis=1)
    h_stand = np.percentile(h, 90)
    codes = np.full(len(h), CODE['transition'], np.int16)
    codes[(h < 0.80 * h_stand) & (speed < 0.15)] = CODE['sitting']
    codes[(h > 0.92 * h_stand) & (speed < 0.12)] = CODE['standing']
    codes[(h > 0.85 * h_stand) & (speed > 0.25)] = CODE['walking']
    wr = {}
    for side, S in (('R', 'Right'), ('L', 'Left')):
        if f'{S}Hand_position_x' in X and f'{S}ForeArm_position_x' in X:
            Wp, Ep = lp(P(f'{S}Hand')), lp(P(f'{S}ForeArm'))
            fw = (np.gradient(np.gradient(Wp, 1 / fs, axis=0), 1 / fs, axis=0) + 9.81 * e_up) / 9.81
            wr[side] = np.c_[fw, V.unit(Wp - Ep)]                 # wrist specific force (world, g) + forearm direction
    return out, codes, wr, notes


def gen_ceti(root, out_dir, max_people=None, log=print):
    st = Store(out_dir, 'CeTI')
    d = S1.find_dir(root, 'CeTI*')
    zp = (S1.walk_files(d, '.zip') or [None])[0] if d else None
    if not zp:
        log('CeTI zip not found'); return st.index
    log(f'  copying the CeTI zip to the local disk ({os.path.getsize(zp) / 1e9:.2f} GB, once)'); zp = S1.local_copy(zp, 'ceti')
    with zipfile.ZipFile(zp) as z:
        mot = sorted(n for n in z.namelist() if n.endswith('_motion.tsv'))
        by = {}
        for n in mot:
            m = re.search(r'sub-([^_/]+)', n)
            if m:
                by.setdefault(m.group(1), []).append(n)
        people = sorted(by)[:max_people] if max_people else sorted(by)
        for pid in people:
            if st.done(pid):
                continue
            try:
                arrays, rows = {}, []
                fsign = None
                files = sorted(by[pid], key=lambda n: 0 if re.search(r'task-[wo]', n) else 1)   # walking tasks first
                for n in files:
                    task = re.search(r'task-([^_]+)', n).group(1)
                    ses = (re.search(r'ses-([^_/]+)', n) or re.search('(x)', 'x')).group(1)
                    run = (re.search(r'run-([^_]+)', n) or re.search('(x)', 'x')).group(1)
                    ch = pd.read_csv(io.BytesIO(z.read(n.replace('_motion.tsv', '_channels.tsv'))), sep='\t')
                    X, hdr = _ceti_read(z, n)
                    if not hdr:
                        X.columns = ch['name'].tolist()[:X.shape[1]]
                    units = ch.set_index('name')['units'].get('Pelvis_position_x', 'cm') if 'units' in ch else 'cm'
                    fs = 100.0
                    if 'Timestamp' in X:
                        dt = np.nanmedian(np.diff(X['Timestamp'].to_numpy(float)))
                        fs = 1000.0 / dt if dt > 1 else 1.0 / dt
                    if len(X) < 2 * fs:
                        continue
                    imp, codes, wr, notes = ceti_frame_signals(X, units, fs, forward_sign=fsign)
                    if notes.get('forward_from') == 'walking':
                        fsign = notes.get('forward_sign_R', fsign)
                    key = f'{task}_ses{ses}_run{run}'
                    codes50 = resample_labels(codes, fs, len(resample(imp['R'], fs)))
                    arrays[f'{key}|labels'] = codes50
                    for side, w6 in wr.items():
                        arrays[f'{key}|wrist_world_{side}'] = resample(w6, fs)
                    tl = CETI_TASK.get(task[0], 'other')
                    for side in 'RL':
                        p50 = resample(imp[side], fs)
                        arrays[f'{key}|{side}|implant'] = p50
                        tilt, ok = walk_check(p50, codes50) if tl == 'walking' else (np.nan, True)
                        first = side == 'R'
                        mix = pd.Series(codes50).map(lambda c: LABELS[c]).value_counts(normalize=True).round(3).to_dict() if first else {}
                        rows.append(dict(group=pid[:1], task=key, task_label=tl, side=side, seconds=round(len(p50) / FS, 1), walk_tilt_deg=tilt,
                                         plausible=ok, frame=f"positions ({notes['vertical_axis']} vertical, x{notes['scale_to_m']} to m)",
                                         label_source='pelvis height and speed', label_mix=json.dumps(mix)))
                if rows:
                    st.save(pid, arrays, rows)
                    log(f'  CeTI {pid}: {len(rows) // 2} recordings, {sum(r["seconds"] for r in rows) / 120:.1f} min, '
                        f'{sum(not r["plausible"] for r in rows)} flagged')
            except Exception as e:
                log(f'  CeTI {pid}: FAILED {e!r}')
    return st.index


def redo(out_dir, datasets, log=print):
    """Remove a dataset's stage 2 output so that its part regenerates it."""
    for ds in [d.strip() for d in datasets.replace(';', ',').split(',') if d.strip()]:
        for path in (os.path.join(out_dir, f'stage2_index_{ds}.csv'), os.path.join(out_dir, 'stage2', ds)):
            if os.path.isdir(path):
                S1.with_retry(lambda: shutil.rmtree(path), f'remove {path}')
            elif os.path.exists(path):
                S1.with_retry(lambda: os.remove(path), f'remove {path}')
        log(f'redo: {ds} output removed, its part will regenerate it')


# ---------------------------------------------------------------- summary
def summarise(out_dir, log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    idx = [pd.read_csv(f) for f in sorted(glob.glob(os.path.join(out_dir, 'stage2_index_*.csv'))) if not f.endswith('_all.csv')]
    if not idx:
        log('no stage 2 output yet'); return
    I = pd.concat(idx, ignore_index=True)
    I['hours'] = I.seconds / 3600
    log('\n=== STAGE 2 SUMMARY ===')
    t = I.groupby('dataset').agg(people=('person', 'nunique'), recordings=('task', 'size'), hours=('hours', 'sum'),
                                 flagged=('plausible', lambda v: int((~v.astype(bool)).sum())))
    log(t.round(2).to_string())
    w = I[I.task_label.isin(['walking', 'mixed']) & I.plausible.astype(bool)]
    if len(w):
        log('\nwalking lean of the virtual implant (deg; real walking in Camargo was 10-17):')
        log(w.groupby('dataset').walk_tilt_deg.describe()[['count', '25%', '50%', '75%']].round(1).to_string())
    if 'label_mix' in I:
        rows = []
        for r in I.dropna(subset=['label_mix']).itertuples():
            for k, v in (json.loads(r.label_mix) if isinstance(r.label_mix, str) else {}).items():
                rows.append(dict(dataset=r.dataset, task=r.task_label if r.task_label != 'mixed' else 'protocol', label=k, hours=v * r.hours))
        if rows:
            L = pd.DataFrame(rows).groupby(['dataset', 'label']).hours.sum().unstack(fill_value=0).round(2)
            log('\nhours per label (labeller or dataset labels):\n' + L.to_string())
            wg = pd.DataFrame(rows); wg = wg[wg.dataset == 'WearGait-PD']
            if len(wg):
                s = wg.groupby(['task', 'label']).hours.sum().unstack(fill_value=0)
                s = s.div(s.sum(1), axis=0).round(2)
                log('\nWearGait-PD sanity check (share of time per label, by task):\n' + s.to_string())
    p = os.path.join(out_dir, 'stage2_kneepad_twosensor_recheck.csv')
    if os.path.exists(p):
        c = pd.read_csv(p)
        log('\nKneE-PAD two-sensor re-check with one frame per person (stage 1b squats had r_x -0.99):')
        log(c.groupby('task')[['r_mag', 'r_x', 'r_z', 'rms_g']].median().round(3).to_string())
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.2))
    t.hours.plot.bar(ax=ax[0], color='#2c5d8f'); ax[0].set_ylabel('hours of implant-site data'); ax[0].set_title('a  Generated implant data', loc='left')
    for ds, g in w.groupby('dataset'):
        ax[1].hist(g.walk_tilt_deg.dropna(), bins=np.arange(-10, 41, 2.5), alpha=0.5, label=ds)
    ax[1].axvspan(10, 17, color='#cccccc', alpha=0.4, label='Camargo real walking')
    ax[1].set_xlabel('mean forward lean while walking (deg)'); ax[1].legend(fontsize=8); ax[1].set_title('b  Walking lean of the virtual implant', loc='left')
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, 'stage2_summary.png'), dpi=130)
    I.to_csv(os.path.join(S1.LOCAL_CACHE, 'stage2_index_all.csv'), index=False)
    S1.with_retry(lambda: shutil.copyfile(os.path.join(S1.LOCAL_CACHE, 'stage2_index_all.csv'), os.path.join(out_dir, 'stage2_index_all.csv')), 'save index')
