# Game Agent Platform

**Human-in-the-loop universal game-playing agent platform.** Supervises turn-based games through browser automation (Playwright), Windows UI automation (pywinauto), and screenshot-based vision. Any game that runs in a browser or on a Windows desktop is a first-class target.

**UNO is the first implemented game plugin** — not the architecture center. The platform is plugin-based: adapters observe and execute, perception plugins interpret, rules plugins validate, strategy plugins choose, and execution plugins plan multi-step interactions.

**Model-capable, model-optional.** Heuristics, templates, and rules remain valid fallback paths. Models enhance strategy, chat, and vision when available. OpenAI-compatible providers (OpenAI, vLLM, llama.cpp) are supported out of the box.

> **New developers**: Start with [Project Overview](docs/PROJECT_OVERVIEW.md) for architecture, service map, and plugin model.

## Architecture at a Glance

```
Adapters (eyes/hands) → ObservedState → PerceptionPlugin → InferredState
                                                              ↓
StrategyPlugin ← LegalActions ← RulesPlugin (rules ∩ affordances)
     ↓                                                      ↑
ExecutionPlugin → adapter clicks/keypresses        ModelLayer (optional)
     ↓ (where to click?)                     heuristic ← → model-assist
GroundingProvider (UIA→template→VLM)         template  ← → model-generate
                                             rule-based ← → model-classify
```

See [Architecture Overview](docs/architecture/overview.md), [Intermediate Contract](docs/architecture/intermediate-contract.md), and [Model Integration](docs/architecture/model-integration.md).

## Current Game Plugins

| Game | Status | Adapter | Notes |
|------|--------|---------|-------|
| **UNO** (DOM) | Working | adapter-web (Playwright) | Pizzuno via `real-unoh-web` profile |
| **UNO** (Canvas) | In progress | adapter-web (screenshot + CV) | `scuffed-uno-web` — E2E not confirmed |
| **UNO** (Desktop) | Working | adapter-windows (pywinauto) | Mock + real via `local-mock-uno` |
| **Svintus** | Working | in-process plugin (no port) | Second game plugin — proves multi-game architecture |
| Chess, Poker, etc. | Planned | any adapter | See [Plugin Interfaces](docs/architecture/plugin-interfaces.md) |

## Model Capabilities

| Task | Heuristic/Template | Model-backed | Fallback |
|------|-------------------|--------------|----------|
| **Strategy** | `decide_heuristic()` | `decide_model()` → policy_advice prompt | heuristic |
| **Chat intent** | `detect_intent_rules()` | `detect_intent_model()` → chat_intent prompt | rule-based |
| **Chat reply** | `generate_reply_template()` | `generate_reply_model()` → chat_reply_generate prompt | template |
| **Vision/CV** | DOM/UIA parsing | `infer_from_screenshot()` → VLM | DOM-only |
| **Grounding** | UIA element / perceived prompt | `POST /ground` → VLM click-point | UIA-only |

**Providers:** OpenAI-compatible (OpenAI, vLLM, llama.cpp), Mock (fallback).
**Config:** Per-game `GameModelConfig` declares preferred models per task.
**Shadow mode:** Set `shadow_evaluation=true` on a session and the opposite strategy (heuristic ↔ model) runs non-binding each tick; disagreement surfaces in decision explanations and eval reports (`shadow_agree_rate`) so strategy promotion is data-backed.
**Caching:** VLM inference results are content-hashed and cached (`VLM_CACHE_ENABLED`, TTL `VLM_CACHE_TTL_S`) — unchanged frames never pay model latency again.
**Safety:** `ChatPolicy` gates all chat responses — rate limiting, strategy leakage prevention, operator override. Global kill switch: `POST :8107/guard/kill-switch {"active": true}` halts every session's next action instantly (arm at startup with `UNO_KILL_SWITCH=1`). Dry-run sessions (`dry_run=true`) run the full observe→decide→guard pipeline without ever executing an action.
**Observability:** Every service propagates `X-Trace-Id` through inter-service calls (binds into structured logs); per-step latency is aggregated at observability-service `/metrics/summary` and one pipeline run is reconstructable via `GET /traces/{correlation_id}`. `ModelUsageTracker` logs every model call with latency, fallback reason, provider.
**Evaluation:** `python scripts/run-eval.py --dataset full_operator` runs scenario datasets through the full in-process pipeline and appends to `models/benchmarks/history.jsonl` — the long-run quality curve. CI gates on `success_rate >= 0.8`; nightly adds shadow measurement.

See [Model Integration](docs/architecture/model-integration.md) for full details.

## Quick Start

### Prerequisites

| Requirement | When |
|-------------|------|
| **Python 3.11+** | Always |
| **[uv](https://docs.astral.sh/uv/)** | Dependency install |
| **Node.js 20+** | Control Center |
| **Playwright Chromium** | Real web profiles |
| **Docker** | Optional — Postgres/Redis |

### Install

```powershell
cd e:\dev\Z-AI-games
.\scripts\setup-windows.ps1
```

### Start Backend

```powershell
.\scripts\dev-backend.ps1
```

### Start Control Center

```powershell
 .\scripts\dev-desktop.ps1
```

### Run a Session

```powershell
# Local mock (no browser)
python scripts/serve-test-target.py
python scripts/start-orchestrator-session-web.py --profile local-mock-uno --url http://127.0.0.1:8765/ --tick

# Real Pizzuno (network + Playwright)
python scripts/start-orchestrator-session-web.py --profile real-unoh-web --tick

# Windows desktop (single tick)
python scripts/start-orchestrator-session-windows.py --tick

# Windows desktop — autonomous, long-running, resumable (see runbook)
python scripts/run-windows-agent.py --profile local-mock-uno --max-ticks 20
python scripts/watchdog-windows-agent.py --run-id nightly --pywinauto --max-duration 3600
```

## Service Ports

| Service | Port | Role |
|---------|------|------|
| session-orchestrator | 8100 | Session lifecycle, tick loop, recovery |
| uno-core | 8101 | UNO rules engine (game plugin, also a service) |
| state-replay-service | 8102 | Event recording + replay |
| perception-service | 8103 | Evidence merge, plugin dispatch |
| adapter-web | 8104 | Browser automation (Playwright) |
| adapter-windows | 8105 | Desktop automation (pywinauto) |
| decision-service | 8106 | Strategy dispatch, action selection |
| policy-guard | 8107 | Safety validation |
| chat-intent-service | 8108 | Operator chat intent |
| chat-response-service | 8109 | Chat response generation |
| model-registry-service | 8110 | Model version management |
| model-runtime-service | 8111 | Model inference |
| observability-service | 8112 | Logs/traces/metrics aggregation |
| config-service | 8113 | Runtime configuration |
| svintus-core | — | Svintus rules engine (in-process game plugin library) |
| control-center | 5173 | Operator UI (Electron/React) |

## Documentation

| Document | Contents |
|----------|----------|
| [Project Overview](docs/PROJECT_OVERVIEW.md) | Platform overview, goals, status |
| [Architecture Overview](docs/architecture/overview.md) | Canonical platform architecture, ownership boundaries |
| [Intermediate Contract](docs/architecture/intermediate-contract.md) | Pipeline data contracts: ObservedState → InferredState → LegalActions |
| [Plugin Interfaces](docs/architecture/plugin-interfaces.md) | PerceptionPlugin, RulesPlugin, StrategyPlugin, ExecutionPlugin protocols |
| [Model Integration](docs/architecture/model-integration.md) | Model providers, routing, GameModelConfig, observability, chat policy |
| [Usage Guide](docs/USAGE.md) | Operator workflows, runbooks, model usage |
| [Operator Debug Checkpoint](docs/runbooks/operator-debug-checkpoint.md) | Debug session notes, resume instructions |
| [Autonomous Windows Agent](docs/runbooks/autonomous-windows-agent.md) | Long unattended runs, checkpoint/resume, watchdog |
| [VLM Perception with Ollama](docs/runbooks/vlm-ollama-setup.md) | Enable local vision-model perception (reads card values, any game) |

## Repository Layout

```
apps/control-center/        Electron + React operator UI
services/                   FastAPI microservices
  session-orchestrator/     Pipeline coordination
  adapter-web/              Browser automation + profiles
  adapter-windows/          Desktop automation
  perception-service/       Evidence merge + game plugins
  decision-service/         Strategy dispatch
  policy-guard/             Safety validation
  uno-core/                 UNO rules engine (game plugin)
  state-replay-service/     Event recording
packages/schemas/           Shared Pydantic contracts
packages/shared-utils/      Logging, HTTP helpers
docs/                       Architecture, runbooks, usage
tests/                      Unit, integration, e2e
scripts/                    Setup, dev, evaluation
```

## Core Commands

| Command | Purpose |
|---------|---------|
| `.\scripts\setup-windows.ps1` | Install Python deps, `.env`, Playwright browser |
| `.\scripts\dev-backend.ps1` | Start all FastAPI services (ports 8100–8113) |
| `.\scripts\dev-desktop.ps1` | Start Control Center (Vite + Electron) |
| `.\scripts\smoke-check.ps1` | HTTP health check on all service ports |
| `.\scripts\run-tests.ps1` | Full pytest suite |
| `python scripts/run-eval.py --dataset full_operator` | Eval harness — in-process pipeline runs, appends quality curve |
| `docker compose --profile backend up --build` | Full backend stack as containers (staging/prod parity) |

### Operations: Safety & Quality

- **Kill switch** (instant halt of every session): `POST http://127.0.0.1:8107/guard/kill-switch {"active": true, "reason": "..."}` — release with `{"active": false}`. Arm at startup for unattended runs via `UNO_KILL_SWITCH=1`.
- **Dry-run sessions**: create a session with `config.dry_run=true` — observe→decide→guard run fully; nothing is ever clicked. For trying new strategies/profiles against a live UI with zero risk.
- **Shadow evaluation**: `config.shadow_evaluation=true` runs the opposite strategy non-binding each tick; `shadow_agree_rate` appears in eval reports and disagreement is logged per tick (`shadow_comparison`).
- **Tracing**: one cycle = one `X-Trace-Id` across all services. Grep any log file for it, or reconstruct the whole run: `GET :8112/traces/{correlation_id}`. Per-step latency: `GET :8112/metrics/summary`; per-service snapshot: `GET :<port>/metrics`.
- **Eval gate**: CI fails if scenario `success_rate < 0.8` on the full operator dataset; nightly additionally measures shadow agreement and uploads `models/benchmarks/history.jsonl` (the quality curve).
- **Windows coverage**: adapter-windows (pywinauto/UIA) runs in the `windows.yml` workflow on a real Windows runner — no more blind spot.

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Pydantic |
| Frontend | TypeScript, React, Vite, Electron |
| Browser automation | Playwright (Chromium) |
| Windows automation | pywinauto, UIA |
| Testing | pytest |
| Dependencies | uv (Python), npm (Node) |
