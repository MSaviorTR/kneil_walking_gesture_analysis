<#
.SYNOPSIS
    Build the standalone Windows one-folder executable for the KNEIL 3D Motion Viewer.
    build_exe 1.0, 23 Nov 2026

.DESCRIPTION
    1. Pre-builds the 50-motion cache + catalog.json + libkneil_v4.dll via viewer/kneil_viewer.py --prebuild-all
    2. Converts the 3 knee implant CAD parts into cache/viewer/cad/ via viewer/implant_cad.py --prepare
    3. Stages build\bundled_data\ (motions, cad, opensim, libkneil_v4.dll, catalog.json, blender_render.py)
    4. Runs PyInstaller (--onedir --windowed) -> dist\KNEIL_viewer\KNEIL_viewer.exe

    Never commits dist/, build/, *.spec, cache/, or CAD meshes (all git-ignored).
#>
param(
    [string]$Python = "C:\Users\Mehdi\AppData\Local\Programs\Python\Python312\python.exe",
    [switch]$SkipPrebuild
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "build_exe 1.0 | repo=$RepoRoot"
$t0 = Get-Date

if (-not $SkipPrebuild) {
    Write-Host "[1/4] Pre-building all 50 motion caches + libkneil_v4.dll + catalog.json..."
    & $Python viewer\kneil_viewer.py --prebuild-all
    if ($LASTEXITCODE -ne 0) { throw "kneil_viewer.py --prebuild-all failed ($LASTEXITCODE)" }

    Write-Host "[2/4] Preparing converted CAD meshes under cache\viewer\cad\..."
    & $Python viewer\implant_cad.py --prepare
    if ($LASTEXITCODE -ne 0) { throw "implant_cad.py --prepare failed ($LASTEXITCODE)" }
} else {
    Write-Host "[1-2/4] Skipping prebuild (--SkipPrebuild set)"
}

Write-Host "[3/4] Staging build\bundled_data\..."
$Stage = Join-Path $RepoRoot "build\bundled_data"
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "motions") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "cad") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "opensim") | Out-Null

Copy-Item "cache\viewer\catalog.json" (Join-Path $Stage "catalog.json")
Copy-Item "cache\viewer\libkneil_v4.dll" (Join-Path $Stage "libkneil_v4.dll")
Copy-Item "viewer\blender_render.py" (Join-Path $Stage "blender_render.py")
Copy-Item "cache\viewer\motions\*" (Join-Path $Stage "motions") -Force
Copy-Item "cache\viewer\cad\*" (Join-Path $Stage "cad") -Force
Copy-Item "cache\opensim\*" (Join-Path $Stage "opensim") -Force

$nMot = (Get-ChildItem (Join-Path $Stage "motions\*.npz")).Count
Write-Host "Staged $nMot motions, CAD meshes, OpenSim model, and libkneil_v4.dll."

Write-Host "[4/4] Running PyInstaller one-folder build -> dist\KNEIL_viewer\KNEIL_viewer.exe..."
& $Python -m PyInstaller `
    --onedir `
    --windowed `
    --noconfirm `
    --clean `
    --name KNEIL_viewer `
    --paths viewer `
    --paths pipeline `
    --add-data "$Stage;bundled_data" `
    --collect-all mujoco `
    --collect-all glfw `
    --collect-submodules matplotlib.backends `
    --hidden-import mujoco.renderer `
    --hidden-import mujoco.viewer `
    --hidden-import mujoco.glfw `
    --hidden-import mujoco.gl_context `
    --hidden-import PIL.ImageGrab `
    --hidden-import kneil_viewer `
    --hidden-import implant_cad `
    --hidden-import export_motion `
    --hidden-import kneil_v1 `
    --hidden-import camargo_replay `
    --hidden-import config `
    viewer\launcher.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed ($LASTEXITCODE)" }

$ExePath = Join-Path $RepoRoot "dist\KNEIL_viewer\KNEIL_viewer.exe"
$BundleBytes = (Get-ChildItem -Recurse (Join-Path $RepoRoot "dist\KNEIL_viewer") | Measure-Object -Property Length -Sum).Sum
$BundleMB = [math]::Round($BundleBytes / 1MB, 1)
$Elapsed = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)

Write-Host "DONE: $ExePath | size=$BundleMB MB | elapsed=${Elapsed}s"
