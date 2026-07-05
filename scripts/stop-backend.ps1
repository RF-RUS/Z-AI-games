$ErrorActionPreference = "SilentlyContinue"

# Stop all UNO Operator backend services by killing whatever listens on their
# ports. Use this before restarting so new code (after a git pull) actually loads
# — uvicorn runs without --reload and will otherwise keep serving stale code.

$ports = 8100,8101,8102,8103,8104,8105,8106,8107,8108,8109,8110,8111,8112,8113

Write-Host "Stopping UNO Operator backend services..."
foreach ($port in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conns) {
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    Write-Host "  Stopped pid $($c.OwningProcess) on :$port"
  }
}
Write-Host "Done."
