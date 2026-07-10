# JARVIS OS — Golden Startup (PowerShell wrapper)
#
# Thin PowerShell launcher around run.py for Windows users who prefer
# PowerShell over python directly.
#
# Usage:
#   .\scripts\golden_startup.ps1
#   .\scripts\golden_startup.ps1 -Port 9000
#   .\scripts\golden_startup.ps1 -InProcess      # run validation only
#   .\scripts\golden_startup.ps1 -DryRun

[CmdletBinding()]
param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8765,
    [string]$Config = "config.yaml",
    [switch]$Reload,
    [switch]$DryRun,
    [switch]$InProcess,
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "[JARVIS] Golden Startup (PowerShell wrapper)" -ForegroundColor Cyan
Write-Host "[JARVIS] Root:   $RepoRoot"
Write-Host "[JARVIS] Bind:   ${Host}:${Port}"
Write-Host ""

# Resolve Python interpreter
$venvPy = Join-Path $RepoRoot ".venv/Scripts/python.exe"
if (Test-Path $venvPy) {
    $python = $venvPy
} else {
    $python = (Get-Command python).Source
}
Write-Host "[JARVIS] Python: $python"

if ($InProcess) {
    Write-Host "[JARVIS] Running in-process validation..." -ForegroundColor Yellow
    & $python (Join-Path $RepoRoot "scripts/validate_startup.py") --in-process
    exit $LASTEXITCODE
}

$args = @(
    (Join-Path $RepoRoot "run.py"),
    "--host", $Host,
    "--port", $Port,
    "--config", $Config
)
if ($Reload) { $args += "--reload" }
if ($DryRun) { $args += "--print-only" }
if ($SkipPreflight) { $args += "--no-preflight" }

Write-Host "[JARVIS] Launching: $python $($args -join ' ')"
& $python @args