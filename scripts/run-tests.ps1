$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Prefer THIS repo's venv interpreter. A bare `python` may be the global one,
# which has editable installs of an OLDER copy of this project registered on
# sys.meta_path — those shadow PYTHONPATH and tests silently run stale code
# (see the interpreter note in dev-backend.ps1 for the full story).
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  Write-Host "WARNING: no .venv at $python - falling back to 'python'. Run 'uv sync' first." -ForegroundColor Yellow
  $python = "python"
}

$env:PYTHONPATH = @(
  "$root/packages/schemas/src",
  "$root/packages/shared-utils/src",
  (Get-ChildItem "$root/services/*/src" -Directory | ForEach-Object { $_.FullName })
) -join ";"

& $python -m pytest tests/ -v --tb=short
