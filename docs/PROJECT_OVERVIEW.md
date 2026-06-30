# Game Agent Platform — Project Overview

## What Is This

A **human-in-the-loop universal game-playing agent platform**. The system supervises turn-based (and eventually real-time) games through browser automation (Playwright), Windows UI automation (pywinauto), and screenshot-based vision. Any game that runs in a browser or on a Windows desktop is a first-class target.

**UNO is the first implemented game plugin** — not the architecture center. The platform is designed so that adding a new game requires only a new perception plugin, rules plugin, and optionally a strategy plugin. The adapters, orchestrator, guard, and operator UI are fully generic.

## System Mental Model

```
┌──────────────────────────────────────────────────────────────┐
│                     ADAPTERS (eyes + hands)                   │
│  adapter-web: Playwright DOM/screenshot/canvas                │
│  adapter-windows: pywinauto UIA tree                          │
│  → produce: ObservedState + RawAffordances                    │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              PERCEPTION PLUGIN (interprets observations)       │
│  Converts raw UI detection into game-specific InferredState   │
│  UNO plugin: reads cards, hand, direction, turn               │
│  Chess plugin: reads board position, piece control            │
│  Canvas plugin: uses VLM/CV to identify game elements         │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              RULES PLUGIN (what moves are legal)               │
│  Generates legal actions from game state                      │
│  Reconciles rules with UI affordances                         │
│  LegalActions = rules ∩ affordances                           │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              STRATEGY PLUGIN (chooses action)                  │
│  Heuristic scoring, model-assist, or custom strategy          │
│  Picks best action from LegalActions                          │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              EXECUTION PLUGIN (intent → UI interaction)        │
│  Converts abstract game action into concrete click/keypress   │
│  Plans multi-step sequences: select → target → confirm        │
│  Verifies expected state changes after execution              │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              ORCHESTRATOR (coordinates + recovers)             │
│  Manages session lifecycle, tick loop, error recovery         │
│  Never interprets observations — only calls plugins           │
└──────────────────────────────────────────────────────────────┘
```

## What Makes This Universal

| Capability | How it works |
|-----------|--------------|
| **Browser DOM games** | adapter-web extracts elements via profile selectors |
| **Browser canvas/WebGL games** | adapter-web captures screenshot → VLM/CV plugin identifies elements |
| **Desktop Windows games** | adapter-windows extracts UIA tree + screenshots |
| **Any turn-based rules** | RulesPlugin implements game rules as a pluggable interface |
| **Any strategy** | StrategyPlugin is swappable (heuristic, model, custom) |
| **Multi-step interactions** | ExecutionPlugin plans select→target→confirm→verify sequences |
| **Model-enhanced decisions** | OpenAI-compatible models for strategy, chat, vision — optional, with fallback |
| **Per-game model preferences** | GameModelConfig declares preferred models per task per game |
| **Safe chat** | ChatPolicy gates all responses — rate limiting, safety, operator override |
| **Observable model usage** | ModelUsageTracker logs every model call with latency, fallback, provider |

## Goals

| Horizon | Goal | Metric |
|---------|------|--------|
| **Current** | UNO plugin fully playable across DOM, canvas, and desktop | Agent plays 10+ cycles with correct card selection |
| **Short-term** | Second game plugin (non-UNO) proving true universality | New game playable with <1 week of plugin development |
| **Long-term** | VLM-assisted universal agent — any game, minimal configuration | Agent adapts to unknown GUIs with vision model assistance |

## Users

Internal tool for agent developers and operators. Future: SaaS operators controlling multiple game sessions across different games simultaneously.

---

## Architecture

### Type: Plugin-based microservices

14 FastAPI backend services + React/Electron Control Center frontend.
All inter-service communication is synchronous HTTP REST. No message queues.

### Service Map

| Service | Port | Responsibility | Generic? |
|---------|------|---------------|----------|
| **session-orchestrator** | 8100 | Session lifecycle, tick loop, recovery | Yes |
| **adapter-web** | 8104 | Playwright browser automation, DOM/screenshot/canvas | Yes |
| **adapter-windows** | 8105 | pywinauto Windows UI automation, UIA tree | Yes |
| **perception-service** | 8103 | Evidence merge, plugin dispatch, confidence scoring | Yes (hosts per-game plugins) |
| **decision-service** | 8106 | Strategy dispatch, action selection | Yes (hosts per-game strategies) |
| **policy-guard** | 8107 | Action legality + confidence validation | Yes |
| **uno-core** | 8101 | UNO rules engine (game plugin) | No — UNO-specific |
| **svintus-core** | 8113 | Svintus rules engine (game plugin) | No — Svintus-specific |
| **chat-intent-service** | 8108 | Operator chat intent classification | Yes |
| **chat-response-service** | 8109 | Chat response generation | Yes |
| **model-runtime** | 8111 | Model inference execution | Yes |
| **model-registry** | 8110 | Model version management | Yes |
| **config-service** | 8113 | Runtime configuration | Yes |
| **observability-service** | 8112 | Metrics collection (planned) | Yes |
| **state-replay-service** | 8102 | Event recording + replay storage | Yes |
| **control-center** | 5173 | React/Electron operator UI | Yes |

### Canonical Pipeline (per tick)

```
1. OBSERVE     adapter → capture_evidence() → ObservedState + RawAffordances
2. INFER       PerceptionPlugin → InferredState (game-specific entities, turn, screen)
3. LEGALIZE    RulesPlugin → LegalActions (rules ∩ affordances)
4. DECIDE      StrategyPlugin → DecisionResult (chosen action + confidence)
5. PLAN        ExecutionPlugin → ExecutionPlan (multi-step UI interaction sequence)
6. EXECUTE     adapter → execute_action() → UI clicks/keypresses
7. VERIFY      RulesPlugin → VerifiedResult (expected state change confirmed?)
8. RECORD      state-replay-service → event stored
```

### Communication

All inter-service communication is **synchronous HTTP REST** (FastAPI + httpx). No message queues, no gRPC.

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Pydantic |
| Frontend | TypeScript, React, Vite, Electron |
| Browser automation | Playwright (Chromium) |
| Windows automation | pywinauto, UIA |
| Testing | pytest |
| Dependencies | uv (Python), npm (Node) |

### Environment

- **Local development**: primary environment, `dev-backend.ps1` + `dev-desktop.ps1`
- **Staging/production**: not yet deployed
- **CI/CD**: designed, partially implemented

---

## What Is Implemented

### Platform (DONE)

| Component | Status | Notes |
|-----------|--------|-------|
| Session orchestrator | Complete | Lifecycle, tick loop, recovery, strategy snapshot |
| Web adapter | Complete | Playwright, profile-driven DOM extraction, CDP connect, canvas coordinates |
| Windows adapter | Complete | pywinauto, UIA tree extraction, layout_targets fallback |
| Perception service | Complete | Evidence merge, plugin dispatch, confidence scoring |
| Decision service | Complete | Heuristic scoring, strategy dispatch |
| Policy guard | Complete | Legality check, confidence threshold |
| AdapterProtocol + Registry | Complete | Plugin-based adapter dispatch |
| Operator Control Center | Complete | Electron/React dashboard, operator, replay, profile health |
| Autonomous loop | Complete | `automatic=True`, first cycle produces real steps |
| CDP browser connect | Complete | Connect to existing Chrome tabs via DevTools Protocol |
| Screenshot trace pipeline | Complete | Visual evidence at each pipeline step |

### UNO Game Plugin (DONE)

| Component | Status | Notes |
|-----------|--------|-------|
| UNO rules engine (`uno-core`) | Complete | Full UNO rules, legal actions, game state |
| UNO perception adapter | Complete | DOM/screenshot → UNO game state extraction |
| UNO heuristic strategy | Complete | Card power scoring, play优先 matching |
| Svintus game plugin | Complete | Second game — proves multi-game architecture |
| DOM profiles | Complete | `real-unoh-web` (Pizzuno), `local-mock-uno`, `scuffed-uno-web` |

### Test Infrastructure (DONE)

| Test type | Count | Status |
|-----------|-------|--------|
| Unit + integration | 274+ | All pass |
| CDP connect tests | 20 | All pass |
| Vertical slice tests | 8 | All pass |

---

## What Is In Progress

| Item | Status | Details |
|------|--------|---------|
| **scuffed-uno-web playability** | Active sprint | Screenshot hand detection + dynamic action grounding |
| **CI/CD pipeline** | Partially implemented | GitHub Actions workflow TBD |
| **Canvas game CV pipeline** | Planned | Template matching, VLM integration for WebGL games |

## What Is Planned

| Item | Phase | Dependencies |
|------|-------|-------------|
| CV-based hand detection (template matching) | P1 | Fixture card templates, viewport calibration |
| VLM integration for canvas games | P2 | Vision model provider, prompt engineering |
| Second non-UNO game plugin | P2 | Perception + rules plugin for new game |
| Docker production deployment | P2 | Dockerfiles, health checks |
| Observability stack | P4 | Prometheus, Grafana, alerting |

---

## Key Files

| File | Purpose |
|------|---------|
| `docs/architecture/overview.md` | Canonical platform architecture |
| `docs/architecture/intermediate-contract.md` | Pipeline contract: ObservedState → InferredState → LegalActions |
| `docs/architecture/plugin-interfaces.md` | Plugin protocols: Perception, Rules, Strategy, Execution |
| `docs/USAGE.md` | Operator workflows and runbook |
| `services/session-orchestrator/` | Core orchestration logic |
| `services/perception-service/` | Evidence merge + game plugins |
| `services/adapter-web/` | Browser automation |
| `services/adapter-windows/` | Desktop automation |
| `apps/control-center/` | Operator UI |

---

## Glossary

| Term | Meaning |
|------|---------|
| **Adapter** | Generic eyes/hands — interfaces with browser or desktop environment |
| **Profile** | Configuration for a specific game site: selectors, URLs, canvas coordinates |
| **PerceptionPlugin** | Converts raw UI observations into game-specific state |
| **RulesPlugin** | Game rules: legal actions, turn detection, state transitions |
| **StrategyPlugin** | Action selection: heuristic, model-assist, or custom |
| **ExecutionPlugin** | Converts game intent into multi-step UI interaction plans |
| **ObservedState** | Raw detection from DOM/UIA/OCR/VLM — no game interpretation |
| **InferredState** | Game-specific interpretation of observations |
| **Affordances** | What the UI allows the agent to do right now |
| **LegalActions** | What the rules allow, filtered by UI affordances |
| **Orchestrator** | Central coordinator: session lifecycle, tick loop, recovery |
