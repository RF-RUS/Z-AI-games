$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONPATH = @(
  "$root/packages/schemas/src",
  "$root/packages/shared-utils/src",
  (Get-ChildItem "$root/services/*/src" -Directory | ForEach-Object { $_.FullName })
) -join ";"

python -m pytest tests/ -v --tb=short
