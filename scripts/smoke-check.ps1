$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ports = @(8100..8113)
$failed = @()

foreach ($port in $ports) {
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2
    Write-Host "[OK] $($r.service) :$port"
  } catch {
    $failed += $port
    Write-Host "[FAIL] :$port"
  }
}

if ($failed.Count -gt 0) { exit 1 }
