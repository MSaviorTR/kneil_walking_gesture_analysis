# Instructions for Gemini (Antigravity)

You are the worker **gemini** in this project. Read `AGENTS.md` and follow it exactly; it has your worktree, order file
(`tasks/NEXT_gemini.md` on `main`), branch names (`gemini/<id>`) and the wait command
(`powershell -NoProfile -File tasks\wait_for_task.ps1 -Worker gemini -Done <id>`).

Short version:
- Work only in `C:\Users\Mehdi\Desktop\PROJECTS\kneil_sims\kneil_v4_gemini`, on the branch your task names.
- Never commit to `main`, never merge, never push, never touch the other worker's worktree (`kneil_v4_agent`).
- Measured numbers only; say what you did not check. Commit your report `tasks/<id>_report.md` last, then wait for
  the next order with the command above.
