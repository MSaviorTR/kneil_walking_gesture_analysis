"""
KNEIL pipeline paths (local PC). Every module takes its paths from here.   v1.0, 16 Nov 2026
Override any path with an environment variable of the same name (for example KNEIL_DATA_ROOT).

DATA_ROOT     the dataset folder (Google Drive, synced offline; read in place)
RESULTS       earlier results V1-V3 (read only: never write here)
V4_OUT        new results of the V4 work
CACHE         scratch inside the workspace (extracted Camargo trials, temporary logs); safe to delete
TINYML        the chip library (C feature code is compiled from here)
OPENSIM_DIR   the OpenSim Gait2354 model used by the Camargo replay
"""
import os

VERSION = 'config 1.0'
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _p(name, default):
    return os.path.normpath(os.environ.get(name, default))


DATA_ROOT = _p('KNEIL_DATA_ROOT', r'G:\My Drive\Walking_Gesture_Datasets')
RESULTS = _p('KNEIL_RESULTS', os.path.join(DATA_ROOT, 'KNEIL_results'))
V4_OUT = _p('KNEIL_V4_OUT', os.path.join(RESULTS, 'v4'))
CACHE = _p('KNEIL_CACHE', os.path.join(WORKSPACE, 'cache'))
TINYML = _p('KNEIL_TINYML', os.path.join(WORKSPACE, 'kneil_tinyml'))
OPENSIM_DIR = _p('KNEIL_OPENSIM_DIR', os.path.join(CACHE, 'opensim'))


def out_dir(*parts):
    """A folder under V4_OUT (created). Refuses to point into the V1-V3 results."""
    d = os.path.join(V4_OUT, *parts)
    assert os.path.commonpath([d, V4_OUT]) == V4_OUT, d
    os.makedirs(d, exist_ok=True)
    return d


def show():
    for k in ('DATA_ROOT', 'RESULTS', 'V4_OUT', 'CACHE', 'TINYML', 'OPENSIM_DIR'):
        v = globals()[k]
        print(f'  {k:11s} {v}  ({"found" if os.path.exists(v) else "missing"})')
