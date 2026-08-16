$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# ---------------------------------------------------------------------------
# Load .env into the process environment BEFORE starting uvicorn.
#
# Why this exists: nothing else in the repo reads .env. No Python module calls
# load_dotenv(), and Start-Process below inherits only THIS process's env. So a
# .env with VLM_PERCEPTION=1 was silently ignored - perception fell back to the
# brightness-profile heuristic, card values were never read, and the agent
# played from the desynced simulator instead of the screen ("launches the game
# but can't play"). docs/USAGE.md tells the user to create .env, so it must
# actually be wired up here.
#
# Timing matters: vlm_provider.py reads VLM_PERCEPTION at MODULE IMPORT time,
# so the value has to be set before the service process starts, not after.
#
# Precedence: an already-set shell variable WINS over .env, so you can still
# override ad-hoc with `$env:VLM_PERCEPTION = "0"` before running this script.
# ---------------------------------------------------------------------------
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
  $loaded = 0
  foreach ($line in Get-Content $envFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
    $idx = $trimmed.IndexOf("=")
    if ($idx -lt 1) { continue }
    # Trim around "=" so `KEY = "value"` doesn't produce a key with a trailing
    # space (which would never match os.getenv("KEY")).
    $key = $trimmed.Substring(0, $idx).Trim()
    $val = $trimmed.Substring($idx + 1).Trim()
    # Strip one layer of matching surrounding quotes - otherwise the literal
    # quotes end up in the value and e.g. VLM_PROFILE_ID becomes
    # '"local/ollama-vlm"', which model-runtime answers with a 404.
    if ($val.Length -ge 2 -and (
          ($val.StartsWith('"') -and $val.EndsWith('"')) -or
          ($val.StartsWith("'") -and $val.EndsWith("'")))) {
      $val = $val.Substring(1, $val.Length - 2)
    }
    if ([string]::IsNullOrEmpty([System.Environment]::GetEnvironmentVariable($key))) {
      [System.Environment]::SetEnvironmentVariable($key, $val)
      $loaded++
    }
  }
  Write-Host "Loaded $loaded variable(s) from .env"
} else {
  Write-Host "WARNING: no .env found at $envFile (copy .env.example .env)" -ForegroundColor Yellow
}

if (-not $env:AGENT_SCREENSHOT_TRACE) { $env:AGENT_SCREENSHOT_TRACE = "1" }
if (-not $env:AGENT_SCREENSHOT_TRACE_DIR) { $env:AGENT_SCREENSHOT_TRACE_DIR = "services\artifacts" }

# Echo the perception-critical settings. Visibility-first, same reasoning as the
# [CVv3] marker: if VLM is off here, expect rec=heuristic and a non-playing agent.
$vlmRaw = $env:VLM_PERCEPTION
$vlmOn = if ([string]::IsNullOrEmpty($vlmRaw)) { "0 (unset)" } else { $vlmRaw }
Write-Host "  VLM_PERCEPTION=$vlmOn  VLM_PROFILE_ID=$($env:VLM_PROFILE_ID)" -ForegroundColor Cyan
if ([string]::IsNullOrEmpty($vlmRaw) -or $vlmRaw -in @("0", "false", "False")) {
  Write-Host "  NOTE: VLM perception is OFF - the agent will run on the colour-only heuristic and will misplay." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Use THIS repo's venv interpreter, never a bare `python`.
#
# Why: the global interpreter on this machine has uno-core, uno-schemas and
# uno-shared-utils pip-installed as EDITABLE from E:\dev\AI-games - an OLDER
# copy of this project. Modern pip editable installs register a MetaPathFinder
# on sys.meta_path, which is consulted BEFORE sys.path, so those three win over
# PYTHONPATH no matter how correctly we set it below. Result: every service ran
# the OLD uno_schemas (the shared inter-service contracts!) and the OLD
# uno_shared.ServiceApp, while service-local packages like uno_perception did
# load from this repo - a half-old, half-new process. That is exactly why
# GET :8103/health returned an empty `details` even though perception's api.py
# sets four health details at import time.
#
# This repo's .venv already has all 20 packages installed editable pointing at
# E:\dev\Z-AI-games (see .venv/Lib/site-packages/_editable_impl_*.pth), so its
# interpreter resolves everything to this working tree.
# ---------------------------------------------------------------------------
$python = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $python) {
  Write-Host "  Python: $python" -ForegroundColor Cyan
} else {
  Write-Host "  WARNING: no .venv at $python - falling back to the global 'python'." -ForegroundColor Yellow
  Write-Host "  Editable installs from another project may shadow this repo. Run 'uv sync' first." -ForegroundColor Yellow
  $python = "python"
}

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

# Per-service log files. Previously every service wrote to the same console with
# -NoNewWindow, so 14 interleaved stdout streams made the [CVv3] perception line
# effectively unfindable. One file per service makes it greppable:
#   Select-String -Path logs\session-orchestrator.log -Pattern CVv3 | Select-Object -Last 5
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Write-Host "  Logs: $logDir"

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
  # stdout and stderr must go to DIFFERENT files - PowerShell errors if both
  # redirect to the same path. structlog prints to stdout (PrintLoggerFactory),
  # uvicorn's own access/error lines go to stderr, so [CVv3] lands in the .log.
  # -u is REQUIRED: without it Python block-buffers stdout once it is redirected
  # to a file, so `Get-Content -Wait` would show nothing until a buffer flush.
  $outLog = Join-Path $logDir "$($svc.Name).log"
  $errLog = Join-Path $logDir "$($svc.Name).err.log"
  Start-Process -NoNewWindow $python `
    -ArgumentList "-u","-m","uvicorn",$svc.Module,"--host","127.0.0.1","--port",$svc.Port `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog
  Write-Host "  Started $($svc.Name) on :$($svc.Port)  (src: $srcDir)"
}
Write-Host "All services started."

# ---------------------------------------------------------------------------
# Wait for readiness before returning the prompt.
#
# Start-Process returns immediately, but uvicorn needs a moment to import the app
# and bind - so a health call issued right after this script looked like a dead
# backend ("Unable to connect to the remote server") when in fact the service came
# up a second later. Poll instead of guessing, and name whatever is genuinely down.
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Waiting for services to become ready..."
$deadline = (Get-Date).AddSeconds(60)
$pending = [System.Collections.ArrayList]::new()
foreach ($svc in $services) { [void]$pending.Add($svc) }

while ($pending.Count -gt 0 -and (Get-Date) -lt $deadline) {
  $ready = @()
  foreach ($svc in $pending) {
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:$($svc.Port)/health" -TimeoutSec 2 -UseBasicParsing
      if ($r.StatusCode -eq 200) {
        Write-Host "  ready: $($svc.Name) on :$($svc.Port)" -ForegroundColor Green
        $ready += $svc
      }
    } catch {}
  }
  foreach ($svc in $ready) { $pending.Remove($svc) }
  if ($pending.Count -gt 0) { Start-Sleep -Milliseconds 500 }
}

if ($pending.Count -gt 0) {
  Write-Host ""
  foreach ($svc in $pending) {
    Write-Host "  NOT READY: $($svc.Name) on :$($svc.Port) - see logs\$($svc.Name).err.log" -ForegroundColor Red
  }
} else {
  Write-Host "All services ready." -ForegroundColor Green
}

# Perception's /health carries the VLM gate (vlm_enabled/vlm_profile_id), which is
# the cheapest confirmation that VLM_PERCEPTION actually reached the process -
# no game cycle required.
try {
  $ph = Invoke-RestMethod -Uri "http://127.0.0.1:8103/health" -TimeoutSec 5
  $d = $ph.details
  if ($null -ne $d -and $null -ne $d.vlm_enabled) {
    $colour = if ($d.vlm_enabled) { "Green" } else { "Yellow" }
    Write-Host "  perception: vlm_enabled=$($d.vlm_enabled) profile=$($d.vlm_profile_id) timeout=$($d.vlm_timeout_s)s" -ForegroundColor $colour
  } else {
    # An empty `details` here means the process is not running THIS repo's
    # uno_shared/uno_schemas - see the interpreter note above.
    Write-Host "  perception: /health has no VLM details - stale uno_shared? check the interpreter." -ForegroundColor Yellow
  }
} catch {
  Write-Host "  perception: could not read /health details" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Watch perception live with:" -ForegroundColor Cyan
Write-Host "  Get-Content logs\session-orchestrator.log -Wait | Select-String CVv3" -ForegroundColor Cyan
