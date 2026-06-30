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

Write-Host "Starting UNO Operator backend services..."
foreach ($svc in $services) {
  $env:PYTHONPATH = "$root/packages/schemas/src;$root/packages/shared-utils/src;$root/services/$($svc.Name -replace '-service','')/src"
  Start-Process -NoNewWindow python -ArgumentList "-m","uvicorn",$svc.Module,"--host","127.0.0.1","--port",$svc.Port
  Write-Host "  Started $($svc.Name) on :$($svc.Port)"
}
Write-Host "All services started."
