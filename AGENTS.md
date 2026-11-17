# Rules for coding agents (OpenCode / DeepSeek and others)

You work for the project owner, together with a manager agent (Claude Code) that writes your tasks and reviews your work.

## Before you start
1. Read `CLAUDE.md` (project context, working rules, known pitfalls) and `README.md` (status, paths, how to run).
2. Read your task file in `tasks/` (for example `tasks/D0_windows_and_loaders.md`). Do **only** what it says.

## Where you work
- You work in your own git worktree: `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_agent`, on the branch named in
  the task (for example `agent/D0`). Never commit to `main`, never merge into `main`, never push, never force. Branch
  changes only as described in "Then wait for the next order".
- Commit your work on your branch (small commits with clear messages). The manager reviews and merges.
- Python: `C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe` (the system Python; no venv). Do not install
  packages; if you need one, stop and write it in your report.
- Shell: Windows PowerShell 5.1 (no `&&`; use `;`).

## Hard rules
- **Never write into `G:\My Drive\Walking_Gesture_Datasets\KNEIL_results` except under `KNEIL_results\v4\stepD\`,
  `KNEIL_results\v4\stepE\` and `KNEIL_results\v4\tinyml_final_v4_lp6\`** (use `config.out_dir(...)`). V1-V3 results
  are read-only. Datasets are read-only.
- A task file may explicitly allow a change to a file listed below (for example `kneil_tinyml/` in step E). Only then,
  and only the files it names.
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

The manager is notified when your report is committed. Commit the report LAST, after all code and results.

## Then wait for the next order (do not stop)
1. Run `powershell -NoProfile -File tasks\wait_for_task.ps1 -Done <the task id you just finished>`.
   It reads `tasks/NEXT.md` from `main` and waits up to 9 minutes. Its last line is `TASK <id>`, `STOP` or `NO_TASK`.
   If your shell tool has a time limit below 10 minutes, add `-MaxMinutes <smaller>`.
2. `NO_TASK`: run the same command again. Do not do anything else in between. After 8 hours of `NO_TASK` in a row, stop.
3. `STOP`: stop and tell the owner you are done.
4. `TASK <id>`: read the printed `tasks/NEXT.md` lines (id, task file, branch, base). Then:
   - `base: main` -> start a new branch from main: `git switch -c <branch> main` (this is the ONLY branch change you may
     make; your working tree must be clean first: everything committed).
   - `base: existing` -> stay on (or switch to) the named existing branch and continue there; first bring in the
     manager's new files with `git merge --ff-only main` if the task says so.
   - Read the task file **from main** (`git show main:<task file>`) if it is not in your branch yet, then do it.
   - A fix task (`<id>_fix.md`) means: change your work on the same branch as the review says, then write
     `tasks/<id>_fix_report.md` (same five sections) and commit it last.
