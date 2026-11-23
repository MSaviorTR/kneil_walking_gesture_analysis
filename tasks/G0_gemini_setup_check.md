# Task G0 (worker gemini): setup check, no code changes

Branch `gemini/G0`, new from `main` in your worktree `kneil_v4_gemini`. Report `tasks/G0_report.md`, committed last.
Read `GEMINI.md`, `AGENTS.md`, `CLAUDE.md` and `README.md` first. Change no file except the report.

## Check and report
1. Git: `git status`, `git branch --show-current`, `git log --oneline -3` in your worktree.
2. Python: run `C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe -c "import numpy, pandas, sklearn, matplotlib; print('ok')"`
   and `python pipeline/config.py` (prints the data paths; say if G: is reachable).
3. Wait loop: run `powershell -NoProfile -File tasks\wait_for_task.ps1 -Worker gemini -Done G0 -MaxMinutes 1` once and
   give its last line. Say whether Antigravity runs such commands without asking the owner each time; if it asks,
   write which setting the owner must change (terminal auto-execution / allow list) so the loop can run alone.
4. Tools: which model you are, whether you can read images (PNG), run PowerShell, and how long one command may run
   before it is stopped.
5. A 5-line summary of the project status, in your own words, from `README.md` (to show you read it).

Then commit the report and start the wait loop (`-Worker gemini -Done G0`).
