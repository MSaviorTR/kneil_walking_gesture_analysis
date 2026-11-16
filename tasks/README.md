# Task board (manager: Claude Code; worker: OpenCode / DeepSeek V4.1 Flash)

How it works:
1. The manager writes `tasks/<id>_<name>.md` on `main` (goal, files, rules, acceptance checks) and points
   `tasks/NEXT.md` (on `main`) at it: `id`, `task`, `branch`, `base` (`main` = new branch from main, `existing` = keep
   working on that branch, e.g. for a fix).
2. The owner starts the worker once in the agent worktree `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_agent`
   with: *"Read AGENTS.md and follow it."*
3. The worker commits on its branch `agent/<id>`, commits `tasks/<id>_report.md` last, then runs
   `tasks/wait_for_task.ps1` (waits for a new id in `main:tasks/NEXT.md`, 9 min per call, repeated).
4. The manager's watcher sees the committed report; the manager reviews the diff, reruns the key checks, merges into
   `main` or writes `tasks/<id>_fix.md`, and updates `NEXT.md` (or writes `id: STOP`).

| Id | Task | Branch | State |
|---|---|---|---|
| D0 | [Window-length loaders + C feature check](D0_windows_and_loaders.md) | `agent/D0` | **merged** ([report](D0_report.md)) |
| D1 | [CV: 8 classes x window length x data variant](D1_cv_classes_windows.md) | `agent/D1` | **merged** ([report](D1_report.md)) |
| D2 | [Seeds, weight of new data, stairs evidence rule](D2_seeds_weight_stairs_rule.md) | `agent/D2` | open |
