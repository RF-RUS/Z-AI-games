# Platform Architecture

## System Type

Plugin-based microservices: 14 FastAPI backend services + React/Electron Control Center frontend.
All inter-service communication is synchronous HTTP REST. No message queues.

## Bounded Contexts

| Context | Services | Owns | Generic? |
|---------|----------|------|----------|
| **Automation** | adapter-web, adapter-windows | UI/DOM interaction, evidence capture, action execution | Yes |
| **Perception** | perception-service | Evidence merge, plugin dispatch, confidence scoring | Yes (hosts per-game plugins) |
| **Game Rules** | uno-core, svintus-core | Game-specific rules, legal actions, state transitions | No — per-game |
| **Intelligence** | decision-service | Strategy dispatch, action selection | Yes (hosts per-game strategies) |
| **Execution** | (embedded in adapters + ExecutionPlugin) | Multi-step action planning, verification | Yes |
| **Safety** | policy-guard | Blocks illegal/low-confidence/unsafe actions | Yes |
| **Orchestration** | session-orchestrator | Session lifecycle, tick loop, recovery | Yes |
| **Replay** | state-replay-service | Event recording + replay storage | Yes |
| **Communication** | chat-intent, chat-response | Operator chat, chat policy | Yes |
| **Model Integration** | model-registry, model-runtime | Model routing, inference, observability | Yes |
| **Platform** | config-service, observability | Cross-cutting infrastructure | Yes |
| **UI** | control-center | Operator dashboard, evidence viewer | Yes |

## Ownership Boundaries — Strict Rules

| Rule | Enforcement |
|------|-------------|
| **Adapters NEVER infer game state** | They return `ObservedState` + `RawAffordances`. Zero game knowledge. |
| **Orchestrator NEVER interprets observations** | It calls plugins and coordinates. Never reads entity state. |
| **RulesPlugin NEVER touches UI** | It receives `InferredState`, returns `LegalActions`. No DOM/UIA awareness. |
| **StrategyPlugin NEVER knows about UI** | It receives `LegalActions`, returns `DecisionResult`. No element IDs, no coordinates. |
| **ExecutionPlugin is the ONLY bridge** | It converts game intent into UI interaction plans with concrete coordinates/clicks. |
| **Models are OPTIONAL** | Every model-backed path has a heuristic/template/rule fallback. Pipeline never blocks on model availability. |
| **ChatPolicy gates ALL responses** | Model output passes through `ChatPolicy.evaluate()` before sending. Safety is not model-dependent. |
| **ModelUsageTracker records ALL calls** | Every model invocation logs task, provider, latency, fallback reason. No silent failures. |
| **Uncertainty flows UP** | Every layer appends to `Uncertainty`. Orchestrator reads it at the end. |

## Canonical Pipeline (per tick)

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. OBSERVE                                                          │
│    adapter-web / adapter-windows                                    │
│    → capture_evidence()                                             │
│    → ObservedState (UI elements, text, screenshot)                  │
│    → RawAffordances (clickable elements, modals, selection mode)    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ 2. INFER                                                            │
│    PerceptionPlugin (per-game)                                      │
│    → infer_state(observed, raw_affordances)                         │
│    → InferredState (entities, turn, screen, summary)                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ 3. LEGALIZE                                                         │
│    RulesPlugin (per-game)                                           │
│    → get_legal_actions(state)                                       │
│    → reconcile_with_affordances(actions, raw_affordances)           │
│    → LegalActions (rules ∩ affordances)                             │
│    → Affordances (reconciled runtime interaction state)             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ 4. DECIDE                                                           │
│    StrategyPlugin (per-game)                                        │
│    → decide(state, legal_actions, affordances)                      │
│    → DecisionResult (chosen action, confidence, explanation)        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ 5. PLAN                                                             │
│    ExecutionPlugin (per-game)                                       │
│    → plan_execution(decision, state, affordances)                   │
│    → ExecutionPlan (ordered UI interaction steps)                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ 6. EXECUTE                                                          │
│    adapter-web / adapter-windows                                    │
│    → execute_action(plan.steps)                                     │
│    → ExecutionResult (success, latency)                             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ 7. VERIFY                                                           │
│    RulesPlugin                                                      │
│    → verify_action(before_state, after_state, action)               │
│    → VerifiedResult (confirmed / not_confirmed / unknown)           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ 8. RECORD                                                           │
│    state-replay-service                                             │
│    → DomainEvent + Observation stored                               │
└─────────────────────────────────────────────────────────────────────┘
```

## Service Details

### session-orchestrator (port 8100)
**Role**: Central coordinator. Manages session lifecycle, runs the autonomous tick loop, handles recovery, builds strategy snapshots for the UI.
**Key classes**: `SessionOrchestrator`, `FlowController`, `RuntimeSession`
**Dependencies**: All other services via HTTP. Registry-based adapter dispatch.
**Never**: Interprets observations, reads entity state, or makes game decisions.

### adapter-web (port 8104)
**Role**: Browser automation via Playwright. Profile-driven DOM extraction, screenshot capture, CDP connect, canvas coordinate clicking.

**Ownership boundaries:**
| Capability | Owner | Method |
|-----------|-------|--------|
| Window/tab discovery | `startup.py` | CDP `/json` endpoint, profile domain matching |
| Screenshot capture | `runtime.py:PlaywrightSession.capture_evidence()` | `page.screenshot()` |
| DOM extraction | `extraction.py` | Profile-driven CSS selectors |
| Vision/state extraction | `perception-service` | Receives DOM + screenshots, extracts game state |
| Mouse/keyboard execution | `runtime.py:PlaywrightSession.execute()` | `page.click()`, `page.keyboard.press()` |
| Canvas coordinate clicking | `canvas_coords.py` | Profile `layout_targets` → `page.mouse.click(x, y)` |

**Key classes**: `PlaywrightSession`, `MockWebAdapter`, `PlaywrightWebAdapter`
**Produces**: `ObservedState` (DOM + screenshot) + `RawAffordances`
**Never**: Infers game state — that's the perception-service's job.

**This is the primary path for browser-based games** (DOM and canvas/WebGL).

### adapter-windows (port 8105)
**Role**: Windows desktop automation via screenshot/vision/coordinate path. This is the **primary automation method** for desktop games and applications.

**Ownership boundaries:**
| Capability | Owner | Method |
|-----------|-------|--------|
| Window discovery | `runtime.py:list_window_candidates()` | Win32 `EnumWindows` API |
| Screenshot capture | `rpa/executor/visual_executor.py:capture_live_frame()` | `capture_window_screenshot()` |
| Vision/state extraction | `perception-service` | Receives screenshots, extracts game state via plugins |
| Mouse/keyboard execution | `rpa/driver/input_driver.py` | `pywinauto.mouse.click()`, `pywinauto.keyboard.send_keys()` |
| Post-action verification | `rpa/executor/visual_executor.py:verify_screenshot_transition()` | Before/after screenshot comparison |

**Key classes**: `PywinautoAdapter`, `MockWindowsAdapter`, `VisualExecutor`, `InputDriver`
**Produces**: `ObservedState` (screenshot + UIA tree if available) + `RawAffordances`
**Never**: Infers game state — that's the perception-service's job.

**Why screenshot/vision/coordinate is the primary path:**
- Most desktop games render via DirectX/OpenGL/canvas, not Windows UIA controls
- UIA tree extraction only works for Win32/WPF/apps that expose accessibility controls
- Screenshot capture works for ANY visible window, regardless of rendering technology
- Coordinate-based clicking works for any clickable element, even without UIA handles

**When to use this path:**
- Canvas/WebGL/DirectX games (UNO.exe, browser games via CDP)
- Any desktop app where UIA controls are not exposed
- Preview/monitoring of any visible window

**Known limitations:**
- Coordinate clicks require precise calibration (profile `layout_targets`)
- No semantic understanding of UI elements (just pixel positions)
- Post-action verification uses screenshot comparison, not UIA state
- Cannot detect UI element state changes without re-capturing screenshot

**UIA/DOM automation is secondary** — only used when the app exposes Windows UIA controls (tkinter, WPF, Win32 forms). For canvas games, UIA extraction returns empty trees.

### perception-service (port 8103)
**Role**: Evidence merge, plugin dispatch, confidence scoring. Hosts per-game `PerceptionPlugin` implementations.

**Screenshot perception pipeline:**
1. Receives `ScreenshotFrame` from adapter via orchestrator
2. If DOM/UIA evidence is empty → uses `HeuristicCanvasUNOPlugin` for canvas games
3. Plugin analyzes screenshot: detects screen validity, regions, actionable targets
4. Returns structured `InferredState` with detected regions and confidence

**Key classes**: `UnuPerceptionAdapter` (DOM/UIA), `HeuristicCanvasUNOPlugin` (screenshot), merger functions
**Consumes**: `ObservedState` + `RawAffordances` + `ScreenshotFrame`
**Produces**: `InferredState` (game-specific entities, turn, screen state)
**Never**: Accesses UI directly, executes actions.

### decision-service (port 8106)
**Role**: Strategy dispatch, action selection. Hosts per-game `StrategyPlugin` implementations.
**Key functions**: `decide_heuristic()`, `decide_random()`
**Consumes**: `InferredState` + `LegalActions` + `Affordances`
**Produces**: `DecisionResult` (chosen action, confidence, explanation)
**Never**: Knows about UI elements, coordinates, or DOM structure.

### policy-guard (port 8107)
**Role**: Hard safety validation. Blocks illegal actions, low-confidence decisions, policy violations.
**Consumes**: `LegalActions` + `DecisionResult`
**Produces**: `{allowed: bool, violation: ...}`

### uno-core (port 8101)
**Role**: UNO rules engine — first game plugin implementation.
**Consumes**: `InferredState`
**Produces**: `LegalActions`, turn detection, state transitions
**Note**: This is a UNO-specific service. New games implement their own rules plugin.

### svintus-core (port 8113)
**Role**: Svintus rules engine — second game plugin proving multi-game architecture.

### Control Center (port 5173)
**Role**: Electron + React operator UI. Session setup, live dashboard, evidence viewer, manual takeover.
**Key components**: `OperatorWorkspace`, `HeroFrame`, `TraceTimeline`, `GameStateCard`
**Depends on**: All backend services via HTTP polling.

### model-registry-service (port 8110)
**Role**: Model profile CRUD, route selection by use_case + priority.
**Key functions**: `route(use_case, profile_id)`, `list_profiles()`
**Depends on**: None (file-based + in-memory).

### model-runtime-service (port 8111)
**Role**: Model inference execution. OpenAI-compatible provider, mock provider, prompt registry, benchmarks.
**Key functions**: `invoke_with_fallback()`, prompt template rendering
**Depends on**: model-registry-service (for profile resolution).
**Never**: Makes game decisions — it only executes inference requests.

## Model-Aware Platform Behavior

Models are **optional but first-class**. The platform works without models (heuristics/templates/rules) and enhances with models when available.

| Concern | Model-optional path | Model-enhanced path |
|---------|--------------------|--------------------|
| **Strategy** | `decide_heuristic()` | `decide_model()` → model-runtime → policy_advice |
| **Chat intent** | `detect_intent_rules()` | `detect_intent_model()` → model-runtime → chat_intent |
| **Chat reply** | `generate_reply_template()` | `generate_reply_model()` → model-runtime → chat_reply_generate |
| **Perception** | DOM/UIA parsing | VLM inference → structured extraction |
| **Chat safety** | `ChatPolicy.evaluate()` gates ALL paths | Same policy, model output passes through |

**GameModelConfig** (`game_plugin.py`) lets each game declare preferred models. The platform resolves routes and handles fallbacks automatically.

**ModelUsageTracker** (`model_observability.py`) records every model invocation: task, provider, latency, fallback reason. Structured logs make model behavior transparent.

See [model-integration.md](model-integration.md) for full model architecture.

## Why UNO Is a Plugin, Not the Core Architecture

The platform is designed so that **adding a new game requires only implementing 3-4 plugin interfaces**:

1. `PerceptionPlugin` — how to read game state from UI
2. `RulesPlugin` — what moves are legal
3. `StrategyPlugin` — how to choose among legal moves
4. `ExecutionPlugin` (optional) — multi-step interaction planning

The adapters, orchestrator, guard, operator UI, and trace system are **fully generic**. They know nothing about UNO, cards, colors, or game rules.

UNO was the first implementation because:
- It has clear visual elements (cards, colors, numbers)
- It has simple rules (match color/value, draw, pass)
- It runs in browser (DOM) and on canvas (WebGL) — testing both adapter paths
- It has a public web version (Pizzuno) for real-world testing

But the architecture is not UNO-shaped. A chess plugin, poker plugin, or any turn-based game plugin would use the exact same interfaces.

## AdapterProtocol Architecture

All adapters implement a common protocol dispatched through `AdapterRegistry`:

```python
class AdapterProtocol(Protocol):
    async def attach(request) -> GenericAttachResponse
    async def detach(adapter_id) -> None
    async def capture_evidence(adapter_id) -> GenericEvidenceBundle
    async def execute_action(adapter_id, action) -> GenericActionResult
    def list_profiles() -> list[dict]
    def load_profile(profile_id) -> dict
```

Orchestrator dispatches through registry — zero adapter-type branching in core logic.

## Verification Architecture

Action-aware, family-based verification:

| Family | Unchanged coarse state → | Example actions |
|--------|-------------------------|-----------------|
| `state_advance` | `not_confirmed` | click_play, start_match |
| `state_may_advance` | `unknown` | click_ready, wait |
| `observability` | `unknown` | inspect_screen, focus_game_window |
| `in_game_effect` | `unknown` | play_card, draw_card |

## Failure Handling

- **Service unavailable** → orchestrator marks session `ERROR`, retry with backoff
- **Illegal action** → policy-guard rejects, no execution
- **Low confidence** → hold action, re-observe
- **Attach failure** → recovery policy (retry / fallback to mock / fallback to manual / stop)
- **CDP connection lost** → session error, operator notification
- **Domain mismatch** → 4-layer defense catches before execution
- **Execution step fails** → `ExecutionPlugin.handle_failure()` → retry / replan / escalate
