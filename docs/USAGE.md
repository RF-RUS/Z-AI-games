# Game Agent Platform — Usage Guide

Practical guide for developers and operators on **Windows** (primary). Commands are validated against the current repo layout.

This is a **universal game-playing agent platform**. UNO is the first implemented game plugin — the examples below use UNO as the reference implementation, but the platform supports any turn-based game across browser, canvas, and desktop environments.

For architecture details see [architecture/overview.md](architecture/overview.md). For plugin development see [architecture/plugin-interfaces.md](architecture/plugin-interfaces.md). For model integration see [architecture/model-integration.md](architecture/model-integration.md).

## Using Models (Optional)

Models enhance strategy, chat, and vision — but heuristics and templates always work as fallback.

### Strategy Model-Assist

Enable model-assisted decision making for a session:

```python
# In session config
spec = {
    "config": {
        "adapter_type": "web",
        "strategy_id": "model_assist",  # or "heuristic" (default)
        "model_assist_enabled": True,
    },
    ...
}
```

Or enable hybrid mode (heuristic primary, model secondary opinion):

```python
spec = {
    "config": {
        "strategy_id": "heuristic",
        "model_assist_enabled": True,  # hybrid: heuristic + model
    },
    ...
}
```

### Chat with Models

Enable model-backed chat responses:

```python
# In chat reply request
ChatReplyRequest(
    session_id="...",
    intent=intent,
    use_model=True,  # enable model-backed reply
    correlation_id="...",
)
```

### Vision/CV for Canvas Games

VLM perception is auto-triggered when DOM elements are unavailable:

```python
# perception-service automatically routes to VLM when:
# - No DOM elements detected (canvas/WebGL game)
# - screenshot_path is provided
# - GameModelConfig.vision_models is non-empty
```

### Configuring Model Profiles

Add model profiles to `models/profiles/`:

```json
// models/profiles/remote-gpt4.json
{
  "profile_id": "remote-gpt4",
  "provider": "llama_cpp_openai",
  "base_url": "https://api.openai.com/v1",
  "model_name": "gpt-4",
  "api_key_env": "OPENAI_API_KEY",
  "priority": 10,
  "use_cases": ["policy_advice", "chat_reply"],
  "safety_limits": {"max_tokens": 1024, "temperature": 0.3}
}
```

### Fallback Behavior

All model paths have automatic fallback:
- Strategy: model → heuristic → mock
- Chat intent: model → rule-based
- Chat reply: model → template
- Vision: VLM → DOM-only

Fallback reasons are logged via `ModelUsageTracker`.

## Who this is for

- Running game sessions (UNO, or any game with a registered plugin)
- Operating the Control Center UI
- Running evaluation and profile health checks
- Responding to selector drift on web profiles

---

## First setup (Windows)

### Requirements

- Python **3.11+** (see `pyproject.toml`)
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js **20+** for Control Center
- Playwright Chromium for real web flows

### Install

```powershell
cd e:\dev\AI-games
.\scripts\setup-windows.ps1
```

The script:

1. Runs `uv sync --all-packages`
2. Editable-installs `packages/schemas` and `packages/shared-utils`
3. Copies `.env.example` → `.env` if missing
4. Creates `data/replays/`
5. Installs Playwright Chromium (best effort)

### Manual setup (if script unavailable)

```powershell
uv sync --all-packages
uv pip install -e packages/schemas -e packages/shared-utils
copy .env.example .env
python -m playwright install chromium
```

### Optional: Postgres / Redis

```powershell
docker compose up -d
```

Not required for default in-memory local dev.

---

## Start the stack

### Backend services

```powershell
.\scripts\dev-backend.ps1
```

Starts 14 FastAPI processes on ports **8100–8113**. Each opens in its own window/process.

Verify:

```powershell
.\scripts\smoke-check.ps1
```

### Control Center

```powershell
.\scripts\dev-desktop.ps1
```

Runs Vite dev server + Electron shell. UI talks to orchestrator on **8100** and adapter-web on **8104**.

Tabs:

| Tab | Use |
|-----|-----|
| **Dashboard** | Service health, start session, profile health panel |
| **Operator** | Session list, tick/pause/resume/stop, step log (orchestrator **8100** required) |
| **Replay** | Browse replays, events, artifacts |

### Dashboard service health

Each card calls `GET /health` on its port (see [README service ports](../README.md#service-ports)).

| UI label | When |
|----------|------|
| `checking…` | First load |
| `healthy` | JSON `status: "healthy"` |
| `degraded` / `unhealthy` | Matching `status` from service |
| `offline` | Service not reachable |
| `error` | HTTP error or invalid JSON |

Works without Electron: opening `http://localhost:5173` uses browser fetch (same endpoints).

### Profile Health panel (Dashboard)

Independent of the **session** adapter dropdown:

- **Mock** session adapter → panel explains profile health is for Web/`real-unoh-web`, not mock play.
- **Web** session adapter → panel loads summary from adapter-web `:8104` if online.
- Prerequisites: `.\scripts\dev-backend.ps1` running; optional prior smoke run for history.

```powershell
python scripts/nightly-profile-smoke.py --profile real-unoh-web --allow-network
```

### Operator tab (session list)

Requires orchestrator on port **8100** (`.\scripts\dev-backend.ps1`).

| UI state | Meaning |
|----------|---------|
| Loading | Polling `GET /sessions` |
| Offline | Orchestrator not reachable |
| Empty | No sessions — use **New Session** |
| Error | HTTP failure or non-array response |

**Mock adapter:** sessions are orchestrator-managed HTTP sessions. They are **not** the same as in-process `evaluate-full-operator.py` runs (those never hit `GET /sessions`).

**Web / Windows:** same orchestrator API; adapter type is set when creating a session.

---

## Workflow 1: Local mock web session

Deterministic page — no external network.

**Terminal 1** — test page:

```powershell
python scripts/serve-test-target.py
```

Serves `services/adapter-web/test-target/` at `http://127.0.0.1:8765/`.

**Terminal 2** — backend:

```powershell
.\scripts\dev-backend.ps1
```

**Terminal 3** — session:

```powershell
python scripts/start-orchestrator-session-web.py --profile local-mock-uno --url http://127.0.0.1:8765/ --tick
```

Without `--tick`, prints session status JSON only.

**Via Control Center:** Dashboard → Adapter **Web** → Start Session, or Operator → New Session with adapter **web**.

---

## Workflow 2: Real Pizzuno web session

Profile: `real-unoh-web` → `https://pizz.uno/singleplayer`

**Requires:** backend running, Playwright, outbound network.

```powershell
.\scripts\dev-backend.ps1
python scripts/start-orchestrator-session-web.py --profile real-unoh-web --tick
```

Bootstrap (cookie banner, start game) is defined in `services/adapter-web/profiles/real-unoh-web.json` under `action_mappings`.

**Control Center:** Dashboard → Adapter **Web (Playwright)** → Start Session (uses `real-unoh-web` when web adapter selected).

---

## Workflow 3: Windows attended RPA session

Mock (CI / no desktop):

```powershell
.\scripts\dev-backend.ps1
python scripts/start-orchestrator-session-windows.py --tick
```

Real pywinauto + visible mouse (Windows session, interactive desktop):

```powershell
.\scripts\dev-backend.ps1
python scripts/start-orchestrator-session-windows.py --pywinauto --launch-test-target --tick
```

Or launch the test target manually:

```powershell
python services/adapter-windows/test-target/uno_mock_app.py
python scripts/start-orchestrator-session-windows.py --pywinauto --tick
```

**Control Center:** Operator → Adapter **Windows** → Start Session. Live preview polls `GET :8105/adapters/{id}/preview` every 2s.

**Prerequisites:** unlocked Windows session, DPI scaling consistent, target window visible (not minimized). Low-confidence targets are refused (no blind click).

See [runbooks/windows-target-profiles.md](runbooks/windows-target-profiles.md).

---

## Workflow 4: Full-operator evaluation

Runs **in-process** — backend **not** required.

```powershell
python scripts/evaluate-full-operator.py --dataset full_operator_smoke
python scripts/evaluate-full-operator.py --dataset full_operator
```

Datasets: `orchestrator/evaluation/datasets/*.jsonl`

Results written to:

```
models/benchmarks/results/{run_id}_full_operator.json
```

See [architecture/full-operator-evaluation.md](architecture/full-operator-evaluation.md).

---

## Workflow 5: Profile health check

### Health model

| Status | Meaning | Operator action |
|--------|---------|-----------------|
| **healthy** | All required selectors match on **primary** | None |
| **degraded** | Required via **fallback**, and/or optional selectors fail | Inspect drift; fix primaries if repeated |
| **broken** | Required selector fully missing | Stop relying on profile; fix selectors immediately |

**Fallback ratio** = share of required selectors that matched via fallback (0–1). High sustained ratio → update primary selectors in profile JSON.

### Live check (API, backend required)

```powershell
curl http://127.0.0.1:8104/profiles/real-unoh-web/selector-health
curl http://127.0.0.1:8104/profiles/real-unoh-web/health/summary
curl http://127.0.0.1:8104/profiles/real-unoh-web/health/history
curl http://127.0.0.1:8104/profiles/real-unoh-web/health/alerts
curl http://127.0.0.1:8104/metrics/profile-health
```

`selector-health` launches Playwright against the real site (slow; writes artifacts).

### CLI (standalone, no backend)

```powershell
python scripts/nightly-profile-smoke.py --profile real-unoh-web --allow-network
python scripts/profile-health-summary.py --profile real-unoh-web
python scripts/profile-health-history.py --profile real-unoh-web --json
python scripts/profile-health-alerts.py --profile real-unoh-web
```

### Nightly smoke exit codes

| Code | Meaning |
|------|---------|
| `0` | Healthy, or skipped (no Playwright / CI without network) |
| `1` | **broken** |
| `2` | **degraded** (only with `--no-tolerate-degraded`) |

Skipped runs print JSON with `"status": "skipped"` — not a health pass.

### Alerts (automatic evaluation)

| Alert | Severity | Trigger |
|-------|----------|---------|
| `broken_immediate` | critical | Latest run broken |
| `sustained_degraded` | warning | ≥3 consecutive required-selector degraded runs |
| `fallback_spike` | warning | Fallback ratio ≥50% over last 2 runs |
| `recovery` | info | Recovered to healthy |

Full detail: [runbooks/real-unoh-web-profile.md](runbooks/real-unoh-web-profile.md)

---

## Workflow 6: History, summary, alerts

```powershell
# Human-readable summary (status, drift counts, alerts, artifact paths)
python scripts/profile-health-summary.py --profile real-unoh-web

# JSON history of recent runs
python scripts/profile-health-history.py --profile real-unoh-web --json

# Evaluate alerts; exit 1=critical, 2=warning
python scripts/profile-health-alerts.py --profile real-unoh-web
```

Dashboard **Profile Health** panel (adapter-web must be up) shows latest status, fallback ratio, and runbook path.

---

## Workflow 7: Capture fixtures

### Mock (no browser)

```powershell
python scripts/capture-web-fixture.py --mode mock --profile local-mock-uno
```

### Local test page

```powershell
python scripts/serve-test-target.py
python scripts/capture-web-fixture.py --mode playwright --profile local-mock-uno --url http://127.0.0.1:8765/ --output tests/fixtures/web_adapter
```

### Real Pizzuno (network)

```powershell
python scripts/capture-web-fixture.py --mode playwright --profile real-unoh-web --output tests/fixtures/web_adapter/real-unoh
```

Output files per profile:

```
{profile_id}_dom_snapshot.json
{profile_id}_dom_evidence.json
{profile_id}_meta.json
{profile_id}_screenshot.png   # playwright only
```

See [runbooks/fixture-capture.md](runbooks/fixture-capture.md).

---

## Workflow 8: Respond to selector drift

1. Run smoke or open latest artifact:

   ```powershell
   python scripts/nightly-profile-smoke.py --profile real-unoh-web --allow-network
   ```

2. Open `artifacts/profile-health/{run_id}.json` and matching `.png`.

3. Check `selector_results` — which primary/fallback failed.

4. Compare `dom_signature` across runs.

5. Inspect live DOM if needed:

   ```powershell
   python scripts/inspect-pizzuno-game.py
   ```

6. Update `services/adapter-web/profiles/real-unoh-web.json`.

7. Re-run smoke and re-capture fixtures.

8. Run tests:

   ```powershell
   python -m pytest tests/unit/test_real_unoh_profile.py tests/unit/test_profile_health.py -v
   ```

---

## Output locations

| Output | Path |
|--------|------|
| Profile health reports | `artifacts/profile-health/{run_id}.json` |
| Health screenshots | `artifacts/profile-health/{run_id}.png` |
| Health alerts | `artifacts/profile-health/alerts/{alert_id}.json` |
| Replay storage | `data/replays/` (config: `UNO_REPLAY_STORAGE_PATH`) |
| Operator evaluation results | `models/benchmarks/results/{run_id}_full_operator.json` |
| Model benchmarks | `models/benchmarks/results/` (via `benchmark-run.py`) |
| Web test fixtures | `tests/fixtures/web_adapter/` |
| Web profiles | `services/adapter-web/profiles/` |
| Service logs | stdout from `dev-backend.ps1`; optional `http://127.0.0.1:8112/logs` |

---

## Orchestrator CLI

```powershell
# List sessions
python scripts/orchestrator-status.py

# One session status + steps
python scripts/orchestrator-status.py <session_id>
```

API base: `http://127.0.0.1:8100`

```powershell
curl http://127.0.0.1:8100/sessions
curl http://127.0.0.1:8100/sessions/{id}/status
```

---

## Replay

```powershell
curl http://127.0.0.1:8102/replays
curl http://127.0.0.1:8102/replays/{replay_id}/detail
```

Control Center → **Replay** tab.

---

## Models (optional)

```powershell
python scripts/registry-status.py
python scripts/model-health.py --profile mock/uno-assistant
python scripts/benchmark-run.py --dataset chat_intent
```

Default profile: `models/profiles/mock__uno-assistant.json`. No API keys needed for mock provider.

---

## When manual intervention is required

| Task | Why |
|------|-----|
| Nightly smoke with `--allow-network` | CI skips real site by design |
| Update primary selectors | Sustained degraded / fallback spike |
| Re-capture fixtures | External UI changed |
| `inspect-pizzuno-game.py` | Investigate DOM after Pizzuno redesign |
| `inspect-unoonline-game.py` | Research only — **no supported profile** for unoonline.io |

---

## FAQ / troubleshooting

> **Web/windows operator debugging (2026-06-15):** attach diagnostics, post-attach lifecycle, resume steps — **[docs/runbooks/operator-debug-checkpoint.md](runbooks/operator-debug-checkpoint.md)**

### `.\scripts\setup-windows.ps1` errors in PowerShell

Older repo copies used **batch syntax** (`@echo off`) inside a `.ps1` file. Use the current PowerShell version from the repo, or run manual setup commands above.

### `start-orchestrator-session-web.py` connection refused

Start backend first: `.\scripts\dev-backend.ps1`

### `evaluate-full-operator.py` works without backend

Correct — it uses `InProcessClients` by default.

### Playwright `Executable doesn't exist`

```powershell
python -m playwright install chromium
```

### Real session stuck on readiness

Check cookie/bootstrap selectors in `real-unoh-web.json`. See runbook.

### Profile health shows **degraded** but game works

Fallback selectors are matching. Tolerable short-term; fix primaries before production reliance.

### Profile health **broken**

Do not use profile for automation until fixed. Open artifact JSON + screenshot.

### Control Center profile health panel empty

`adapter-web` must be running on port **8104**.

### Wrong port in old docs

- **adapter-web** = `8104` (not 8102)
- **state-replay-service** = `8102`

---

## Runbook: First Independent Bot Launch on Windows

This runbook guides you through your **first supervised bot launch** on Windows.
It is designed as a **HITL (Human-in-the-Loop) run** — you monitor the bot, not let it run fully autonomous.

### Prerequisites

Before starting, verify:

| Check | How | Pass criterion |
|-------|-----|----------------|
| Windows version | Settings → System → About | Windows 10 (1903+) or Windows 11 |
| App installed | Start Menu → "Game Agent" | App opens without crash |
| Backend running | `.\scripts\smoke-check.ps1` | All ports 8100–8113 respond |
| Game window open | Target app visible on screen | Window not minimized |
| Network available | `ping 127.0.0.1` | Loopback works |
| Logs accessible | Help → Open Logs Folder | Folder opens in Explorer |

### Quickstart (8 steps)

1. **Open Game Agent** from Start Menu or desktop shortcut
2. **Check status bar** — all service dots should be green
3. **Click "Start Playing"** on the setup screen
4. **Select adapter** — Windows Desktop for local game, Web for browser game
5. **Select profile** — UNO Desktop for local Windows game
6. **Pick game window** from the dropdown (if Windows adapter)
7. **Click "Start Playing"** — bot connects and begins
8. **Watch the Monitor panel** — observe what the bot sees and decides

**First run: use Assist mode, not Auto.** Click the "Assist" button in the status bar before starting.

### Detailed First-Run Checklist

#### A. Before Launch

- [ ] Open Game Agent
- [ ] Verify version in title bar (e.g., "Game Agent v0.2.0")
- [ ] Check all service dots are green in status bar
- [ ] Open Help → Open Logs Folder — confirm folder exists
- [ ] Set mode to **Assist** (not Auto) — click "Assist" in status bar
- [ ] Open target game window and position it visibly

#### B. Session Setup

- [ ] Click "Start Playing" or go to Operator → New Session
- [ ] Select **Windows Desktop** adapter (for local game) or **Web** (for browser game)
- [ ] Select appropriate profile (e.g., "UNO Desktop" for local Windows game)
- [ ] If Windows: pick the correct game window from dropdown
- [ ] Click "Start Playing"

#### C. Verify Connection

- [ ] Status bar shows "Connecting" then "Playing"
- [ ] Monitor panel shows "Phase: observe" then progresses
- [ ] Evidence panel shows screenshot of game window
- [ ] Observation summary shows game state (top card, hand size, etc.)
- [ ] Event log shows "observe completed" → "perceive completed"

#### D. First Actions

- [ ] Click "Tick" to execute one action manually
- [ ] Watch Monitor panel for "decide" → "execute" steps
- [ ] Verify Evidence panel updates with new screenshot
- [ ] Check Event Log for action details

#### E. Operator Commands

- [ ] Type "pause" in chat → session pauses
- [ ] Type "resume" in chat → session resumes
- [ ] Type "take over" → mode switches to Manual
- [ ] Type "return to bot" → mode switches back to Auto
- [ ] Type "обрати внимание на чат" → hint acknowledged

#### F. Escalation Test

- [ ] Wait for or trigger low-confidence situation
- [ ] Verify escalation card appears with severity and recommended actions
- [ ] Click "Acknowledge" or "Take Control"
- [ ] Verify escalation resolves

#### G. Complete Run

- [ ] Let bot run for 2-3 minutes in Assist mode
- [ ] Review Event Log for all actions taken
- [ ] Check confidence levels in Evidence panel
- [ ] Click "Stop" to end session

#### H. Post-Run Verification

- [ ] Open Help → Open Logs Folder
- [ ] Check `app-{date}.log` for any errors
- [ ] Verify no crash files in state folder
- [ ] Note any escalations or manual interventions needed

### Abort Criteria — Stop Immediately If:

| Situation | Action | Why |
|-----------|--------|-----|
| Bot attaches to wrong window | Click Stop immediately | Prevents unintended actions |
| Evidence doesn't match game screen | Click Stop, take Manual | Bot is misreading state |
| Repeated action failures (3+) | Click Stop, check logs | Something is broken |
| State mismatch after action | Click Stop, take Manual | Bot lost track of game |
| Unexpected/unsafe behavior | Click Stop, take Manual | Safety first |
| Bot stuck in loop | Click Pause, then Stop | Potential infinite loop |
| Backend errors flooding | Click Stop, check backend | Infrastructure issue |

### After Run

| Step | How |
|------|-----|
| Check logs | Help → Open Logs Folder → `app-{date}.log` |
| Export diagnostics | Help → Export Diagnostics → save zip |
| Review event log | Operator tab → Event Log panel |
| Check confidence | Monitor → Evidence → Confidence badge |
| Note escalations | Monitor → Escalation cards |
| Document issues | Note timestamps, actions, screenshots |

### Troubleshooting

| Problem | Solution |
|---------|----------|
| "Backend unavailable" | Run `.\scripts\dev-backend.ps1` in separate terminal |
| "Window not found" | Ensure game window is open and not minimized |
| "Attach failed" | Check adapter-web (8104) health; restart backend |
| "Low confidence" | Agent is uncertain — take Manual control and help |
| "Stuck in attaching" | Warmup in progress (~20s) — wait or restart |
| "No game state" | Check Evidence panel — bot may be reading wrong window |
| App crashes on start | Check `%APPDATA%\GameAgent\logs\` for crash log |
| Settings lost | Check `%APPDATA%\GameAgent\config\settings.json` |
| Update check fails | Check network; Help → Check for Updates manually |

### Log Locations

| What | Path |
|------|------|
| App logs | `%APPDATA%\GameAgent\logs\app-{date}.log` |
| Crash files | `%APPDATA%\GameAgent\state\crash-*.json` |
| Settings | `%APPDATA%\GameAgent\config\settings.json` |
| Session state | `%APPDATA%\GameAgent\state\last-session.json` |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F5 | Start / Tick |
| F6 | Pause |
| F7 | Resume |
| F8 | Toggle Auto/Manual mode |
| F9 | Return to Bot |
| / | Focus chat input |
| Escape | Dismiss alert / Focus chat |

---

## Related docs

- [runbooks/real-unoh-web-profile.md](runbooks/real-unoh-web-profile.md)
- [runbooks/local-dev.md](runbooks/local-dev.md)
- [runbooks/starting-a-session.md](runbooks/starting-a-session.md)
- [architecture/orchestrator.md](architecture/orchestrator.md)
