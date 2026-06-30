$ErrorActionPreference = 'Stop'
Write-Host '[UNO Operator] Windows setup...'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw 'Python 3.11+ required. Install from https://www.python.org/'
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host 'Installing uv...'
  irm https://astral.sh/uv/install.ps1 | iex
  $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

uv sync --all-packages
uv pip install -e packages/schemas -e packages/shared-utils

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
}
if (-not (Test-Path data/replays)) {
  New-Item -ItemType Directory -Path data/replays -Force | Out-Null
}

try {
  python -m playwright install chromium 2>$null
  if ($LASTEXITCODE -ne 0) {
    throw 'playwright install returned non-zero exit code'
  }
}
catch {
  Write-Host 'Playwright browser install skipped or failed - run: python -m playwright install chromium'
}

Write-Host 'Setup complete. Next: .\scripts\dev-backend.ps1'
