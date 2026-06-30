$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root/apps/control-center"
if (-not (Test-Path node_modules)) { npm install }
npm run dev
