# E2 fix report: unknown posture column, single-tree config

## 1. Status

Done — both review points fixed, all checks re-run and passing.

## 2. Files

Firmware worktree (`kneil_firmware_agent`, branch `agent/E2`, commit `6d41b77`):
- `pc_app/kneil/protocol.py`: `DEVICE_STILL_UNKNOWN = 9`, `N_DEVICE_COLUMNS = 10`; `device_column()` maps v2
  still + unknown posture to the 10th column (an `unknown_col` argument lets the totals keep the old mapping);
  docstring updated.
- `pc_app/kneil/session.py`: `Confusion` has 10 device columns; new `sitting()`, `standing()` (known posture only),
  `posture_unknown()` (share of the device's still windows with an unknown posture); `upright_and_still()` now counts
  the 10th column as still; `overall()` divides by all device outcomes of the 9 truth classes; `Totals.add` calls
  `device_column(..., unknown_col=3)` so the totals counters stay exactly as they were.
- `pc_app/kneil/ui.py`: the accuracy table has the 10th column (hidden for v1), the accuracy line shows walking,
  upright and still, sitting, standing (known posture only), the unknown-posture share and the overall figures, and the
  note under the table explains the new column and the 4 s window centre.
- `pc_app/tests/test_session.py`: 3 new tests (unknown-posture column, known-posture sitting/standing with the
  denominator, totals unchanged).
- `tree_build.conf` (new, committed): only `CONFIG_KNEIL_TINYML_MODEL_SMALL=y` plus a comment with the build command.
- `docs/BUILD.md`: the single-tree command uses `kneil.conf;tree_build.conf`, the config-file table has a
  `tree_build.conf` row.

Workspace (`kneil_v4_agent`, branch `agent/E2`):
- `prompts/PROMPT_gui_KNEIL_live.md`: the accuracy rule is now the 10th-column rule (never counted as sitting,
  known-posture denominators, unknown-posture share).
- `tasks/E2_fix_report.md` (this file).

## 3. Commands

```
cd pc_app ; python -m unittest discover -s tests          # 38 tests
cd ..      ; python tests\run_host_test.py                # HOST TEST: PASS (both models)
gcc -std=c99 -Wall -Wextra -o test_kneil_proto protocol\test_kneil_proto.c protocol\kneil_proto.c ; test_kneil_proto
```
(The firmware and bridge builds are unchanged by this fix — only the PC app, the docs and the new config fragment
changed; the C code was not touched, so the builds of E2 still apply.)

## 4. Acceptance checks

1. **Unknown posture is not sitting** — PASS. `device_column(3, events=0, version=2) == 9`
   (`still (posture unknown)`), `device_column(3, posture sitting) == 3`, `device_column(3, posture standing) == 4`;
   `Confusion` has 10 columns; a truth-sitting window with an unknown posture lands in column 9 and
   `conf.sitting()` returns `(None, 0)` (no window with a known posture); with one known and one unknown window it
   returns `100.0 % over 1 window` and `posture_unknown() = 50 % of 2 still windows`; `upright_and_still()` counts
   both (100 %). Covered by `test_still_with_unknown_posture_is_its_own_column` and
   `test_known_posture_sitting_and_standing`.
2. **Totals unchanged** — PASS: `Totals.add` still puts still minutes into sitting / standing / unknown as before
   (`seconds_sitting/standing/still_unknown` = 1/1/1 for one of each, `test_totals_keep_the_old_still_split`).
3. **PC app tests** — PASS: `Ran 38 tests ... OK` (was 35; 3 added).
4. **Protocol and host tests** — PASS: `PROTOCOL TEST: PASS`, `HOST TEST: PASS (both models)`.
5. **Single-tree config committed and documented** — PASS: `tree_build.conf` is in the repository and
   `docs/BUILD.md` gives the exact command and a config-file table row.

## 5. Problems and open questions

1. The 10th column changes the meaning of the `overall` figure slightly: a v2 still window with an unknown posture is
   no longer counted as a hit for a truth-sitting row (it was before). The "upright and still" figure, which the owner
   uses for the sitting/standing question, counts it as still (blue/violet), so the two numbers differ by design.
2. `overall(merge_sit_stand=True)` still only merges columns 3 and 4 (the trace), not the 10th column; say if the merged
   figure should also accept the unknown-posture still.
3. For v1 sessions the 10th column is hidden and every count is identical to before (v1 has no posture).
