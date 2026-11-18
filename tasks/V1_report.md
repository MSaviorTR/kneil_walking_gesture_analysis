# V1 report: figures (accuracy, data handling, future work)

## 1. Status

Done. `pipeline/make_figures.py` (v1.0) turns the step D results into nine figures (A1-A5, B1-B3, C1), each as PNG
(300 dpi) and SVG in `docs/figures/`, with `docs/figures/make_figures_log.txt` and one section per figure in
`docs/FIGURES.md`. It runs in about 8 s, trains nothing and rebuilds no windows.

## 2. Files

- `pipeline/make_figures.py` — new (v1.0). Reads `stepD/D3/stairs_rule_results.csv`, `stepD/D3/transition_events_results.csv`,
  `stepD/D2/pred_*_W*s_8cls_seed{0,1,2}.npz`, `stepD/windows_v11/windows_W{2,4}s.npz`, `tasks/E2_report.md`,
  `../kneil_firmware/protocol/kneil_proto.h` and `../kneil_firmware/pc_app/kneil/protocol.py`; imports `config`,
  `cv_v4`, `stairs_rule` (the repo's own rule code); prints and logs, per panel, the source file and the values plotted.
- `docs/figures/A1_walking_called_stairs.{png,svg}` … `docs/figures/C1_future_work.{png,svg}` — nine figures, two files each
  (list with sizes below).
- `docs/figures/make_figures_log.txt` — version line, python/matplotlib versions, and per panel the source and numbers.
- `docs/FIGURES.md` — one section per figure: image, 2-3 sentence caption, sources, limits.
- `tasks/V1_report.md` (this file).

No other file changed (`git status` after the commit: clean apart from this report).

## 3. Commands

```
python pipeline/make_figures.py
python -c "import matplotlib.image as m, glob; [print(p, m.imread(p).shape) for p in glob.glob('docs/figures/*.png')]"
python -c "import xml.etree.ElementTree as ET, glob; [ET.parse(p) for p in glob.glob('docs/figures/*.svg')]; print('svg ok')"
git add pipeline/make_figures.py docs/FIGURES.md docs/figures ; git commit
```

## 4. Acceptance checks

1. **Runs clean, prints the source and values per panel** — PASS. Exit code 0 in 7.5-9.1 s (limit: 2 min). Sources
   printed for each of the nine panels, e.g.

   ```
   [style] class names/colours: ..\kneil_firmware\pc_app\kneil\protocol.py (CLASS_LABELS_V2, CLASS_COLOURS_V2)
   [style] packet sizes: ..\kneil_firmware\protocol\kneil_proto.h LIVE_V2_LEN=22 SUMMARY_LEN=41 ...
   [style] build sizes: tasks\E2_report.md forest=157366 B, flash=386664 B, RAM=51632 B, classifier=3436 B, ...
   [A1] sources: stepD/D3/stairs_rule_results.csv (today / no rule) and stepD/D2/pred_V4half_W4s_8cls_seed*.npz + ...
      today (V3recipe 2 s) | Lencioni speed_abs=fast: 12.84 % (sd 0.85 over 3 seeds, n 1197)
      ...
   ```

2. **Spot check against `docs/STEP_D_SUMMARY.md`** — PASS (plotted = summary, or the rule difference explained):

   | panel | plotted | STEP_D_SUMMARY | result |
   |---|---|---|---|
   | A1 Lencioni fast, today | 12.84 % | 12.8 | match |
   | A1 Lencioni fast, V4half 4 s | 4.94 % | 4.9 | match |
   | A1 Luo FE, today | 17.47 % | 17.5 | match |
   | A1 Luo FE, V4half 4 s | 11.01 % | 11.0 | match |
   | A1 WearGait HurriedPace, today / V4 | 7.91 / 6.20 % | 7.9 / 6.2 | match |
   | A3 Luo up recall/precision, today | 50.4 / 41.3 % | 50.4 / 41.3 | match |
   | A3 Luo up recall/precision, V4half 4 s | 71.5 / 58.0 % | 71.5 / 58.0 | match |
   | A3 Luo down recall/precision, today | 83.4 / 28.7 % | 83.4 / 28.7 | match |
   | A3 Luo down recall/precision, V4half 4 s | 95.5 / 38.1 % | 95.5 / 38.1 | match |
   | A4 Luo stairs F0.5 at 2 s / 4 s (V4half) | 76.00 / 82.39 % | 76.0 / 82.4 | match |
   | A4 STS event recall at 2/4/5 s (V4half) | 83.33 / 78.06 / 64.31 % | 83.3 / 78.1 / 64.4 | match (rounding at 5 s) |
   | A4 false events/h at 2 s / 4 s (V4half) | 2.39 / 0.91 | 2.4 / 0.9 | match (the summary reports the worst source, as here) |

   **Explained difference (A1/A3 rule bars):** the task asks for "V4half 4 s + rule (vote >= 0.6)"; the summary's rule
   column is the F0.5-**tuned** rule, which at 4 s on V4half chose theta = 0.5 in all five folds. The figures use the
   recommended 0.6, computed from the stored predictions with `pipeline/stairs_rule.py` (k=1, n=1), so the rule bars are
   slightly stricter than the summary's: Lencioni fast 0.61 % (summary 1.1), Luo FE 1.22 % (2.8), Luo stairs up
   43.4 / 85.9 % (summary 49.2 / 75.7), down 89.2 / 69.4 % (90.6 / 61.4). Both sets are in the log; the "today" and
   "no rule" numbers are the CSV rows and match exactly.
3. **`docs/FIGURES.md`, images open, PNG + SVG each** — PASS. Nine sections, each with the image, a caption, sources and
   limits. All 18 images open (PNG 2850-3381 x 1640-1685 px; every SVG parses):

   ```
   A1 .png/.svg  157 kB / 24 kB    A4 .png/.svg  196 kB / 26 kB    B2 .png/.svg  246 kB / 24 kB
   A2 .png/.svg  215 kB / 43 kB    A5 .png/.svg  238 kB / 47 kB    B3 .png/.svg  150 kB / 19 kB
   A3 .png/.svg  208 kB / 44 kB    B1 .png/.svg  279 kB / 22 kB    C1 .png/.svg  344 kB / 14 kB
   ```
4. **No new package, no file outside the allowed paths** — PASS. Only numpy, pandas and matplotlib (already installed)
   plus the repository's `config`, `cv_v4`, `stairs_rule`; nothing installed. `git status` before the report showed only
   `docs/FIGURES.md`, `docs/figures/` and `pipeline/make_figures.py`.

## 5. Problems and open questions

1. **Rule theta (see 4.2).** The recommendation "vote >= 0.6" is stricter than the tuned rule in the published tables
   (0.5 at 4 s V4half); the figures show 0.6 as the task asks, the report and the log keep both. Say if the figures
   should use the tuned rule instead (one line in the script).
2. **A4 mixes rule versions by design**: the F0.5 line is the rule tuned per window length (theta 0.3-0.6), exactly as
   in the summary's trade-off table; the event and false-event lines use rule R1.
3. **"Simulated" is two sources**: 60 synthetic personas plus the Camargo replay (22 people) = 82 streams in the
   window file; A2 labels the row `simulated*` and the footnote spells this out.
4. **Real data has no transition windows**: A5's real panel rows for sit-to-stand, stand-to-sit and bed transfer are 0
   (shown with their counts), so their percentages mean "no data", not 0 %.
5. **Font sizes**: the charts use 11-13 pt; the three diagrams (B1, B2, C1) use 10-12 pt on a 12 x 6.75 in canvas (a
   10 in canvas made the box text overflow). They are readable when projected; if the owner wants larger text, the
   simplest change is a bigger canvas, not a smaller font.
6. **External inputs**: the script reads `..\kneil_firmware` for the class colours and packet sizes and stops with a clear
   message if that clone or the Google Drive results are missing. `README.md` was not edited; the figures are ready to be
   linked from it (`docs/FIGURES.md`).
7. Nothing outside the repository was written; the step D results were opened read-only.
