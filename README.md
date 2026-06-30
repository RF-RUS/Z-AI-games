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
                                            heuristic ← → model-assist
                                            template  ← → model-generate
                                            rule-based ← → model-classify
```

See [Architecture Overview](docs/architecture/overview.md), [Intermediate Contract](docs/architecture/intermediate-contract.md), and [Model Integration](docs/architecture/model-integration.md).

## Current Game Plugins

| Game | Status | Adapter | Notes |
|------|--------|---------|-------|
| **UNO** (DOM) | Working | adapter-web (Playwright) | Pizzuno via `real-unoh-web` profile |
| **UNO** (Canvas) | In progress | adapter-web (screenshot + CV) | `scuffed-uno-web` — E2E not confirmed |
| **UNO** (Desktop) | Working | adapter-windows (pywinauto) | Mock + real via `local-mock-uno` |
| **Svintus** | Working | adapter-web | Second game plugin — proves multi-game architecture |
| Chess, Poker, etc. | Planned | any adapter | See [Plugin Interfaces](docs/architecture/plugin-interfaces.md) |

## Model Capabilities

| Task | Heuristic/Template | Model-backed | Fallback |
|------|-------------------|--------------|----------|
| **Strategy** | `decide_heuristic()` | `decide_model()` → policy_advice prompt | heuristic |
| **Chat intent** | `detect_intent_rules()` | `detect_intent_model()` → chat_intent prompt | rule-based |
| **Chat reply** | `generate_reply_template()` | `generate_reply_model()` → chat_reply_generate prompt | template |
| **Vision/CV** | DOM/UIA parsing | `infer_from_screenshot()` → VLM | DOM-only |

**Providers:** OpenAI-compatible (OpenAI, vLLM, llama.cpp), Mock (fallback).
**Config:** Per-game `GameModelConfig` declares preferred models per task.
**Safety:** `ChatPolicy` gates all chat responses — rate limiting, strategy leakage prevention, operator override.
**Observability:** `ModelUsageTracker` logs every model call with latency, fallback reason, provider.

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
cd e:\dev\AI-games
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

# Windows desktop
python scripts/start-orchestrator-session-windows.py --tick
```

## Service Ports

| Service | Port | Role |
|---------|------|------|
| session-orchestrator | 8100 | Session lifecycle, tick loop, recovery |
| uno-core | 8101 | UNO rules engine (game plugin) |
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
| observability-service | 8112 | Metrics (planned) |
| config-service | 8113 | Runtime configuration |
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

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Pydantic |
| Frontend | TypeScript, React, Vite, Electron |
| Browser automation | Playwright (Chromium) |
| Windows automation | pywinauto, UIA |
| Testing | pytest |
| Dependencies | uv (Python), npm (Node) |
