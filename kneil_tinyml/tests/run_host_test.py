"""Host test on any OS with gcc (Windows: MinGW-w64): builds both models and runs the self-test vectors.
Same as run_host_test.sh. Usage: python tests/run_host_test.py [stream.txt]   (must print RESULT: PASS twice)"""
import os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = ['src/kneil_features.c', 'src/kneil_classifier.c', 'src/kneil_metrics.c', 'src/kneil_selftest.c', 'tests/host_test.c']


def main():
    ok = True
    for model in ('forest', 'tree'):
        exe = os.path.join(tempfile.gettempdir(), f'kneil_host_test_{model}' + ('.exe' if os.name == 'nt' else ''))
        cmd = ['gcc', '-O2', '-std=c99', '-Wall', '-Wno-unused-parameter'] + (['-DKNEIL_MODEL_SMALL'] if model == 'tree' else []) \
              + ['-Iinclude'] + SRC + ['-o', exe, '-lm']
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            print(f'[{model}] build failed:\n{r.stderr}'); ok = False; continue
        r = subprocess.run([exe] + sys.argv[1:], cwd=ROOT, capture_output=True, text=True)
        print(f'[{model}]\n{r.stdout.strip()}')
        ok &= 'RESULT: PASS' in r.stdout
    print('HOST TEST:', 'PASS (both models)' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
