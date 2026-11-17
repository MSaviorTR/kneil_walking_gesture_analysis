"""Add the V3 model to kneil_tinyml and run the host test.   v1.0
Usage (in this folder, with your Python):   python add_v3_model.py "<folder with the 4 files>"
The folder is KNEIL_results/tinyml_final_v3_lp6 (download it from Google Drive if needed). It must contain
kneil_model_forest.h, kneil_model_tree.h, kneil_model_info.h and kneil_test_vectors.h. Needs gcc on the PATH."""
import os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), 'kneil_tinyml')      # the library is in the workspace root, not in docs/
FILES = {'kneil_model_forest.h': 'include', 'kneil_model_tree.h': 'include', 'kneil_model_info.h': 'include',
         'kneil_test_vectors.h': 'tests'}


def main():
    print('add_v3_model v1.1')
    if len(sys.argv) < 2:
        print(__doc__); return 2
    # the library ships its V4 model since step E: adding V3 would silently replace it
    cur = os.path.join(LIB, 'include', 'kneil_model_info.h')
    if os.path.exists(cur):
        text = open(cur).read()
        if re.search(r'^\s*#define\s+KNEIL_MODEL_WIN_S\b', text, re.M):
            name = re.search(r'KNEIL_MODEL_NAME\s+"([^"]*)"', text)
            print(f'REFUSED: kneil_tinyml/include/kneil_model_info.h already defines KNEIL_MODEL_WIN_S '
                  f'(model {name.group(1) if name else "?"}).')
            print('This library ships the V4 model (8 classes, 4 s). Adding the V3 headers would replace it and the')
            print('firmware would build the wrong model. For a V3 image use the V3 branch of the firmware repository')
            print('(or copy the V3 files into a separate copy of the library). Nothing was changed.')
            return 1
    src = sys.argv[1]
    missing = [f for f in FILES if not os.path.exists(os.path.join(src, f))]
    if missing:
        print(f'not found in {src}: {missing}'); return 1
    info = open(os.path.join(src, 'kneil_model_info.h')).read()
    fs = re.search(r'KNEIL_MODEL_FS_HZ\s+(\d+)', info); lp = re.search(r'KNEIL_MODEL_LOWPASS_HZ\s+([\d.]+)', info)
    ds = re.search(r'KNEIL_MODEL_DATASET\s+"([^"]*)"', info)
    print(f"model info: {fs.group(1) if fs else '?'} Hz, low-pass {lp.group(1) if lp else '?'} Hz, dataset: {ds.group(1) if ds else '?'}")
    problems = []
    if not fs or fs.group(1) != '50':
        problems.append('KNEIL_MODEL_FS_HZ is not 50')
    if not lp or float(lp.group(1)) != 6.0:
        problems.append('KNEIL_MODEL_LOWPASS_HZ is not 6')
    if not ds or not ds.group(1).strip().endswith('V3'):
        problems.append('the dataset line does not end with V3 (is this the V3 export?)')
    if problems:
        print('WARNING: ' + '; '.join(problems))
    for f, sub in FILES.items():
        shutil.copyfile(os.path.join(src, f), os.path.join(LIB, sub, f))
        print(f'copied {f} -> kneil_tinyml/{sub}/  ({os.path.getsize(os.path.join(LIB, sub, f)) / 1024:.0f} kB)')
    r = subprocess.run([sys.executable, os.path.join(LIB, 'tests', 'run_host_test.py')], cwd=LIB, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    ok = 'HOST TEST: PASS' in r.stdout
    print('\nREADY: build the firmware with this kneil_tinyml folder (see FLASH_V3.md)' if ok and not problems else
          '\nNOT READY: fix the messages above before building the firmware')
    return 0 if ok and not problems else 1


if __name__ == '__main__':
    sys.exit(main())
