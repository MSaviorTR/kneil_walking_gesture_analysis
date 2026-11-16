# Rules for coding agents (OpenCode / DeepSeek and others)

You work for the project owner, together with a manager agent (Claude Code) that writes your tasks and reviews your work.

## Before you start
1. Read `CLAUDE.md` (project context, working rules, known pitfalls) and `README.md` (status, paths, how to run).
2. Read your task file in `tasks/` (for example `tasks/D0_windows_and_loaders.md`). Do **only** what it says.

## Where you work
- You work in your own git worktree: `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_agent`, on the branch named in
  the task (for example `agent/D0`). Never switch branches, never touch `main`, never merge, never push, never force.
- Commit your work on your branch (small commits with clear messages). The manager reviews and merges.
- Python: `C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe` (the system Python; no venv). Do not install
  packages; if you need one, stop and write it in your report.
- Shell: Windows PowerShell 5.1 (no `&&`; use `;`).

## Hard rules
- **Never write into `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results` except under `KNEIL_results\v4\stepD\`**
  (use `config.out_dir('stepD', ...)`). V1-V3 results are read-only. Datasets are read-only.
- For test runs set `$env:KNEIL_V4_OUT = "<your worktree>\cache\test_v4"` so nothing real is overwritten.
- Do not change: `kneil_tinyml/` (chip library), `pipeline/stage2.py`, `pipeline/stage3.py`, `pipeline/stage2_v4.py`,
  `pipeline/vimp.py`, the class list, the window length used by the chip, the BLE protocol, `CLAUDE.md`, `AGENTS.md`.
  New code goes into new files unless the task says otherwise.
- Every script prints a version line first, writes a log file, saves results as it goes, and can resume.
- Test on a small subset first (`--max-people` or similar); run the full job only if the task says so.
- When something fails: add a diagnostic that shows the cause; do not guess, do not silence errors.
- Measured numbers only in reports. Mark assumptions as assumptions. Never invent a result.
- Do not edit `README.md`; put everything for the README into your report (the manager updates it).

## When you finish
Write `tasks/<task id>_report.md` with exactly these sections and commit it:
1. **Status**: done / partly done / blocked (one line).
2. **Files**: every file you added or changed, one line each.
3. **Commands**: the exact commands you ran for the acceptance checks.
4. **Acceptance checks**: each check from the task with its measured result and PASS / FAIL.
5. **Problems and open questions**: anything unclear, anything you could not do, anything that looked wrong in the data.
