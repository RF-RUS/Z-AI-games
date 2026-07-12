$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:AGENT_SCREENSHOT_TRACE = "1"
$env:AGENT_SCREENSHOT_TRACE_DIR = "services\artifacts"

$services = @(
  @{Name="config-service"; Module="uno_config.api:app"; Port=8113},
  @{Name="uno-core"; Module="uno_core.api:app"; Port=8101},
  @{Name="state-replay-service"; Module="uno_replay.api:app"; Port=8102},
  @{Name="perception-service"; Module="uno_perception.api:app"; Port=8103},
  @{Name="adapter-web"; Module="uno_adapter_web.api:app"; Port=8104},
  @{Name="adapter-windows"; Module="uno_adapter_windows.api:app"; Port=8105},
  @{Name="decision-service"; Module="uno_decision.api:app"; Port=8106},
  @{Name="policy-guard"; Module="uno_policy.api:app"; Port=8107},
  @{Name="chat-intent-service"; Module="uno_chat_intent.api:app"; Port=8108},
  @{Name="chat-response-service"; Module="uno_chat_response.api:app"; Port=8109},
  @{Name="model-registry-service"; Module="uno_model_registry.api:app"; Port=8110},
  @{Name="model-runtime-service"; Module="uno_model_runtime.api:app"; Port=8111},
  @{Name="observability-service"; Module="uno_observability.api:app"; Port=8112},
  @{Name="session-orchestrator"; Module="uno_orchestrator.api:app"; Port=8100}
)

# Clean restart: STOP any process already listening on a service port first.
# uvicorn runs WITHOUT --reload, so old processes keep serving OLD code after a
# git pull. Without this, re-running the script just spawns duplicates that fail
# to bind while the stale code keeps answering (e.g. perception on :8103 showing
# pcv=MISSING and the agent never recognising the game). This makes new code live.
Write-Host "Stopping any existing backend services..."
foreach ($svc in $services) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $svc.Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
      Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
      Write-Host "  Stopped stale $($svc.Name) (pid $($c.OwningProcess)) on :$($svc.Port)"
    }
  } catch {}
}
Start-Sleep -Milliseconds 700

Write-Host "Starting UNO Operator backend services..."
foreach ($svc in $services) {
  # Service SOURCE dir = the service Name verbatim (e.g. "perception-service"),
  # NOT the name with "-service" stripped. The folders on disk are
  # services/perception-service/src, services/config-service/src, etc. The old
  # `-replace '-service',''` pointed PYTHONPATH at services/perception/src which
  # does NOT exist, so uvicorn silently imported the STALE globally-installed
  # `uno_perception` package instead of this repo — the new CV code (cv_build=v3)
  # never loaded and every restart still showed pcv=MISSING. Use $svc.Name as-is.
  $srcDir = "$root/services/$($svc.Name)/src"
  if (-not (Test-Path $srcDir)) {
    Write-Host "  WARNING: source dir not found for $($svc.Name): $srcDir" -ForegroundColor Yellow
  }
  $env:PYTHONPATH = "$root/packages/schemas/src;$root/packages/shared-utils/src;$srcDir"
  Start-Process -NoNewWindow python -ArgumentList "-m","uvicorn",$svc.Module,"--host","127.0.0.1","--port",$svc.Port
  Write-Host "  Started $($svc.Name) on :$($svc.Port)  (src: $srcDir)"
}
Write-Host "All services started."
