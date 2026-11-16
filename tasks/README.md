# Task board (manager: Claude Code; worker: OpenCode / DeepSeek V4.1 Flash)

How it works:
1. The manager writes `tasks/<id>_<name>.md` on `main` (goal, files, rules, acceptance checks).
2. The owner starts the worker in the agent worktree `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_agent`
   with: *"Read AGENTS.md, then do tasks/<file>."*
3. The worker commits on its branch `agent/<id>` and writes `tasks/<id>_report.md`.
4. The manager reviews the diff, reruns the key checks, merges into `main` or writes `tasks/<id>_fix.md`.

| Id | Task | Branch | State |
|---|---|---|---|
| D0 | [Window-length loaders + C feature check](D0_windows_and_loaders.md) | `agent/D0` | open |
