# Wait for the next order from the manager.   v1.1, 23 Nov 2026
# The manager writes the order file on the branch main: tasks/NEXT.md for the default worker (OpenCode/DeepSeek),
# tasks/NEXT_<worker>.md for any other worker (e.g. -Worker gemini). This script reads it (from main, not from your
# branch) every 60 s and exits as soon as it names a task id different from -Done, or says STOP, or after -MaxMinutes.
# Output, last line: TASK <id> | STOP | NO_TASK
# Use (worker, after finishing a task):  powershell -NoProfile -File tasks\wait_for_task.ps1 -Done D0
#                                        powershell -NoProfile -File tasks\wait_for_task.ps1 -Worker gemini -Done G0
param([string]$Done = '', [int]$MaxMinutes = 9, [string]$Worker = '')
$git = 'C:\Program Files\Git\cmd\git.exe'
$file = if ($Worker) { "tasks/NEXT_$Worker.md" } else { 'tasks/NEXT.md' }
$t0 = Get-Date
while ($true) {
    $next = & $git show "main:$file" 2>$null
    if ($next) {
        $text = ($next -join "`n")
        $id = ([regex]::Match($text, '(?m)^id:\s*(\S+)')).Groups[1].Value
        if ($id -eq 'STOP') { $text; 'STOP'; exit 0 }
        if ($id -and $id -ne $Done) { $text; "TASK $id"; exit 0 }
    }
    if (((Get-Date) - $t0).TotalMinutes -ge $MaxMinutes) { 'NO_TASK'; exit 0 }
    Start-Sleep 60
}
