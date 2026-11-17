# E2 fix (manager review, 17 Nov 2026)

E2 is accepted except for two points. Same branches as E2 (`base: existing`): firmware code on `agent/E2` in
`kneil_firmware_agent`, report on `agent/E2` in `kneil_v4_agent`. Never push, never flash.

## 1. Still with unknown posture must not count as sitting (PC app)
`pc_app/kneil/protocol.py:device_column` maps v2 `still` + posture unknown to sitting (3). The owner will use the
truth keys to measure sitting vs standing, so this biases the result. Change:
- Add a 10th device column `still (posture unknown)` to the confusion table for v2 only (v1 tables unchanged).
- The UI's accuracy line: sitting and standing accuracy computed over windows with a known posture only, plus
  "posture unknown: x % of still windows". "Upright and still" (truth sitting or standing vs device still, any posture)
  stays as it is.
- Totals (`seconds_still_unknown` etc.) unchanged. Update the docstring, the GUI prompt line if it states the old rule,
  and add a unit test (v2 still + unknown -> the new column; known posture -> sitting / standing).

## 2. Single-tree build config
Your build command uses `tree_build.conf`, but the file is not committed and not documented. Commit it (only
`CONFIG_KNEIL_TINYML_MODEL_SMALL=y` and a comment) and add the command to `docs/BUILD.md`.

## Checks
PC app tests OK (count), protocol test PASS, host test PASS. Write `tasks/E2_fix_report.md` (five sections) and commit it
last in `kneil_v4_agent`.
