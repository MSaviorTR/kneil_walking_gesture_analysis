"""
Readers for the two V4 datasets.   v1.0, 16 Nov 2026

Luo et al. 2020 (Sci Data 7:219): data.mat is MATLAB 7.3 (HDF5). data/ID<n>/<sensor> is a MATLAB table object
  (MCOS). There are 180 tables (30 people x 6 sensors: trunk, thighR, thighL, shankR, shankL, wrist); table k (its
  object id, the 5th number of the uint32 reference) takes 7 cells of #subsystem#/MCOS starting at 2 + 7 (k - 1):
  [column data (37 cells of 1x57), ndims, nrows, rownames, nvars, variable names, properties]. Rows = 57 trials:
  3 CALIB, then 6 each of FE, CS, StrU/StrD (alternating), SlpU/SlpD (alternating), BnkL/BnkR (alternating), GR.
  Acc in m/s^2, Gyr in rad/s, 100 Hz (Xsens MTw). Read with h5py: one table at a time, never the whole file.
  The per-trial CSVs in 'input data_SD' carry the same PacketCounter but are named by sensor serial, not position.

Lencioni et al. 2019 (Sci Data 6:309): SubjectN.mat (MATLAB 5) with struct s: Age, BH (cm), BM, KinFreq (60 or 200 Hz),
  MarkerVarName (87 = 29 markers x XYZ, metres, Y up), Data (one entry per STRIDE: Task, Foot, Marker 87 x n, speed,
  cadence, ...), StandingData (one static marker frame). Tasks: Walking, HeelWalking, ToeWalking, StepUp, StepDown.
"""
import glob, os, re
import numpy as np

VERSION = 'v4_readers 1.0'
LUO_SENSORS = ('trunk', 'thighR', 'thighL', 'shankR', 'shankL', 'wrist')
LUO_SURFACES = {'CALIB': 'calibration', 'FE': 'flat even', 'CS': 'cobblestone', 'StrU': 'stairs up', 'StrD': 'stairs down',
                'SlpU': 'slope up', 'SlpD': 'slope down', 'BnkL': 'bank left', 'BnkR': 'bank right', 'GR': 'grass'}
LUO_FS = 100.0


# ------------------------------------------------------------------------------------------------ Luo
def _h5val(f, ref):
    import h5py
    u = f[ref]
    c = u.attrs.get('MATLAB_class', b'').decode()
    if c == 'char':
        return ''.join(chr(x) for x in u[()].ravel())
    if c == 'cell':
        return [_h5val(f, r) for r in u[()].ravel()]
    if 'MATLAB_empty' in u.attrs:
        return None
    return u[()]


class Luo:
    """Use: with Luo(path) as L: L.people(); T = L.table(1, 'shankR')"""
    def __init__(self, path):
        self.path = path; self.f = None

    def __enter__(self):
        import h5py
        self.f = h5py.File(self.path, 'r')
        self.refs = self.f['#subsystem#/MCOS'][()].ravel()
        return self

    def __exit__(self, *exc):
        self.f.close()
        return False

    def people(self):
        return sorted(int(k[2:]) for k in self.f['data'].keys())

    def object_id(self, person, sensor):
        return int(self.f[f'data/ID{person}/{sensor}'][()].ravel()[4])

    def table(self, person, sensor, channels=('Acc', 'Gyr')):
        """dict: info columns (lists of 57) + channels as lists of (n, 3) arrays."""
        oid = self.object_id(person, sensor)
        base = 2 + 7 * (oid - 1)
        names = _h5val(self.f, self.refs[base + 5])
        cols = dict(zip(names, self.f[self.refs[base]][()].ravel()))
        out = {}
        for n in ('Participant', 'Trial', 'TrialDuration', 'Surface', 'Sensor', 'MissingCount', 'Missingpct'):
            v = _h5val(self.f, cols[n])
            out[n] = [x if isinstance(x, str) else (float(np.asarray(x).ravel()[0]) if x is not None and np.size(x) else np.nan) for x in v]
        for ch in channels:
            parts = [[np.asarray(a, float).ravel() for a in _h5val(self.f, cols[f'{ch}_{k}'])] for k in 'XYZ']
            out[ch] = [np.c_[x, y, z] for x, y, z in zip(*parts)]
        if 'PacketCounter' in cols:
            out['PacketCounter'] = [np.asarray(a, float).ravel() for a in _h5val(self.f, cols['PacketCounter'])]
        assert all(int(p) == person for p in out['Participant']), f'table {oid}: participant mismatch'
        assert all(s == sensor for s in out['Sensor']), f'table {oid}: sensor mismatch'
        return out


def luo_csv_files(root, person, trial):
    d = os.path.join(root, 'input data_SD', 'input data_SD', str(person))
    return {re.search(r'_([0-9A-F]{8})\.txt\.csv$', p).group(1): p for p in glob.glob(os.path.join(d, f'{trial}-000_*.txt.csv'))}


def luo_csv_read(path):
    import pandas as pd
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    return dict(PacketCounter=df['PacketCounter'].to_numpy(float), Acc=df[['Acc_X', 'Acc_Y', 'Acc_Z']].to_numpy(float),
                Gyr=df[['Gyr_X', 'Gyr_Y', 'Gyr_Z']].to_numpy(float))


# ------------------------------------------------------------------------------------------------ Lencioni
def lencioni_files(root):
    fs = glob.glob(os.path.join(root, 'All_Subjects', 'Subject*.mat'))
    return sorted(fs, key=lambda p: int(re.search(r'Subject(\d+)', p).group(1)))


def lencioni_load(path):
    import scipy.io as sio
    s = sio.loadmat(path, squeeze_me=True, struct_as_record=False)['s']
    names = [str(n).strip() for n in s.MarkerVarName]
    markers = [n[1:] for n in names[::3]]
    assert all(names[3 * i][0] == 'X' and names[3 * i + 1][0] == 'Y' and names[3 * i + 2][0] == 'Z' for i in range(len(markers)))
    strides = []
    for k, x in enumerate(np.atleast_1d(s.Data)):
        M = np.asarray(x.Marker, float)                       # (87, n)
        strides.append(dict(index=k, task=str(x.Task).strip(), foot=str(x.Foot).strip(), t0=float(x.TimeStampKin),
                            speed=float(x.speed), cadence=float(x.cadence), stride_length=float(x.strideLength),
                            markers={m: M[3 * i:3 * i + 3].T for i, m in enumerate(markers)}))
    S = np.asarray(s.StandingData.Marker, float)
    return dict(name=str(s.name), age=int(s.Age), sex=str(s.Gender).strip(), height_cm=float(s.BH), mass_kg=float(s.BM),
                fs=float(s.KinFreq), marker_names=markers, strides=strides,
                standing={m: S[3 * i:3 * i + 3] for i, m in enumerate(markers)})
