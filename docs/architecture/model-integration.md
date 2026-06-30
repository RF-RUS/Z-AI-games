# Model Integration Architecture

> **Canonical source** for model-related architecture. All model routing, provider abstraction, observability, and policy gating is documented here.

## Overview

The platform is **model-capable but model-optional**. Heuristics, templates, and rule-based logic remain valid fallback paths. Models enhance capability when available but never block the pipeline.

**Four model task types:**
- **Strategy** — action selection (heuristic → model-assisted → custom)
- **Vision** — screenshot-based perception for canvas/WebGL games
- **Chat** — in-game and operator-facing conversation
- **Intent** — chat message classification

**Core principle:** Models are selected by task + game + environment. The platform resolves routes, handles fallbacks, and tracks usage automatically.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GAME PLUGIN LAYER                             │
│  GamePlugin.model_config: GameModelConfig                       │
│  Declares preferred models per task: strategy, vision, chat     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                 MODEL CONFIG REGISTRY                            │
│  model_config.py: get_game_config(game_type)                    │
│  resolve_model_profile(game_type, task, available_profiles)     │
│  Returns preferred profile_id or None (use fallback)            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                 MODEL ROUTING LAYER                              │
│  model-registry-service: route(use_case, profile_id)            │
│  Selects provider by: task_type + game_type + env + priority    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                 MODEL PROVIDER LAYER                             │
│  model-runtime-service: invoke_with_fallback()                  │
│  ┌────────────────┐ ┌────────────┐ ┌────────────────┐          │
│  │ OpenAI-compat   │ │ Mock       │ │ Custom provider │          │
│  │ (default)       │ │ (fallback) │ │ (per-game)      │          │
│  └────────────────┘ └────────────┘ └────────────────┘          │
│  Supports: OpenAI API, vLLM, llama.cpp, any compatible          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                 OBSERVABILITY LAYER                              │
│  ModelUsageTracker: records task, provider, latency, fallback   │
│  Structured logging: model_usage task=... provider=...          │
└─────────────────────────────────────────────────────────────────┘
```

## GameModelConfig

Each game plugin declares preferred models via `GameModelConfig`:

```python
class GameModelConfig(BaseModel):
    game_type: str
    strategy_models: list[str]    # ["heuristic", "remote-vllm-poker"]
    vision_models: list[str]      # ["gpt-4-vision", "local-llava"]
    chat_models: list[str]        # ["gpt-3.5-turbo"]
    intent_models: list[str]      # ["gpt-3.5-turbo"]
    fallback_to_heuristic: bool = True
    fallback_to_template: bool = True
    chat_enabled: bool = True
    model_chat_enabled: bool = False
    max_chat_length: int = 200
```

**Resolution:** `resolve_model_profile(game_type, task, available_profiles)` picks the first preferred model that's available, or returns `None` (use fallback).

### Default Configs

| Game | Strategy | Vision | Chat | Intent |
|------|----------|--------|------|--------|
| UNO | heuristic | (none) | mock/uno-assistant | (none) |
| Svintus | heuristic | (none) | (none) | (none) |
| Unknown games | heuristic | (none) | (none) | (none) |

## Task-Specific Model Use

### Strategy (decision-service)

```
DecisionRequest
  │
  ├── strategy_id = "heuristic"
  │   └── decide_heuristic() → DecisionResult
  │
  ├── strategy_id = "model_assist"
  │   ├── resolve_model_profile(game_type, "strategy")
  │   ├── model-runtime → policy_advice prompt → parse JSON
  │   ├── Validate action_index from model
  │   └── On any failure → fallback to decide_heuristic()
  │
  └── use_model_assist = true (hybrid)
      ├── decide_heuristic() → primary
      ├── model-runtime → secondary opinion
      ├── If agree → use model confidence
      └── If disagree → use heuristic, note disagreement
```

**Prompt:** `prompts/policy_advice/v1.json`
**Fallback:** heuristic → mock

### Chat Intent (chat-intent-service)

```
ChatMessage[]
  │
  ├── use_model = false (default)
  │   └── detect_intent_rules() → ChatIntent (regex + keywords)
  │
  └── use_model = true
      ├── resolve_model_profile(game_type, "intent")
      ├── model-runtime → chat_intent prompt → parse JSON
      └── On failure → fallback to detect_intent_rules()
```

**Prompt:** `prompts/chat_intent/v1.json`
**Fallback:** rule-based detection

### Chat Reply (chat-response-service)

```
ChatReplyRequest
  │
  ├── ChatPolicy.evaluate() → allowed? rate limit? safety?
  │   └── If not allowed → return ChatPolicyResult(allowed=False)
  │
  ├── use_model = false (default)
  │   └── generate_reply_template() → ChatReply (static templates)
  │
  └── use_model = true
      ├── resolve_model_profile(game_type, "chat")
      ├── model-runtime → chat_reply_generate prompt → parse JSON
      ├── Safety check: _check_safety(reply_text)
      └── On failure or unsafe → fallback to generate_reply_template()
```

**Prompt:** `prompts/chat_reply_generate/v1.json`
**Fallback:** template

### Vision (perception-service)

```
Screenshot (from adapter)
  │
  ├── PerceptionPlugin.infer_state()
  │   ├── If DOM/UIA available → parse elements (no model needed)
  │   └── If canvas-only → vlm_provider.infer_from_screenshot()
  │       ├── resolve_model_profile(game_type, "vision")
  │       ├── model-runtime → VLM inference → structured extraction
  │       ├── Normalize into InferredState format
  │       └── On failure → return empty state with uncertainty
  │
  └── RulesPlugin.get_legal_actions()
      └── Uses InferredState (regardless of source)
```

**Prompt:** `prompts/perception_dispute/v1.json`
**Fallback:** DOM-only (no VLM)

## ChatPolicy

Explicit response gating — the bot does not respond blindly to every message.

```python
class ChatPolicy:
    def evaluate(intent, recent_replies) -> ChatPolicyResult:
        # Checks:
        # 1. chat_enabled (master kill switch)
        # 2. operator_override (bypass all rules)
        # 3. directed_at_bot (was bot addressed?)
        # 4. context gating (gameplay? social? help?)
        # 5. rate limiting (min_interval, max_per_minute)
        # 6. cooldown (after spam detection)
    
    def check_reply_safety(reply) -> ChatPolicyResult:
        # Checks:
        # 1. blocked_words (strategy leakage, toxic content)
        # 2. max_reply_length
```

**Config:**
```python
ChatPolicyConfig(
    respond_to_directed=True,
    respond_to_questions=True,
    respond_to_social=True,
    respond_to_gameplay=False,
    min_interval_ms=3000,
    max_responses_per_minute=10,
    cooldown_after_spam_ms=30000,
    blocked_words=["my hand", "my cards", "strategy is", ...],
    chat_enabled=True,
    operator_override=False,
)
```

## Model Observability

Every model-backed path records usage via `ModelUsageTracker`:

```python
tracker = get_usage_tracker()
record = tracker.start(
    task="strategy",
    game_type="uno",
    provider="openai_compat",
    profile_id="remote-gpt4",
    session_id="...",
)
# ... model call ...
tracker.complete(record, success=True, confidence=0.85)
```

**Logged per invocation:**
- task (strategy/intent/chat/vision)
- game_type
- provider (openai_compat/mock/heuristic/template)
- model_id, profile_id
- latency_ms
- success/fallback_used/fallback_reason
- confidence
- parse_success

**Query:** `tracker.get_summary()` returns totals, by_task, by_provider, fallback_rate, avg_latency.

## Fallback Chain

```
1. Try preferred model (from GameModelConfig.resolve_model_profile)
2. Try any model with matching use_case (from model-registry)
3. Try heuristic (strategy) / template (chat) / rule-based (intent)
4. Try mock (last resort)
```

Every fallback is logged with reason.

## OpenAI-Compatible Serving

Any model behind an OpenAI-compatible `/chat/completions` endpoint works:

| Endpoint | Example |
|----------|---------|
| OpenAI hosted | `https://api.openai.com/v1` |
| vLLM server | `http://localhost:8000/v1` |
| llama.cpp server | `http://localhost:8080/v1` |
| Any compatible | Custom endpoint |

**Profile configuration:**
```json
{
  "profile_id": "local-vllm-poker",
  "provider": "vllm_openai",
  "base_url": "http://localhost:8000/v1",
  "model_name": "waltgrace/poker-gemma4-26b-a4b-lora",
  "api_key_env": "VLLM_API_KEY",
  "priority": 20,
  "use_cases": ["policy_advice", "chat_reply"],
  "safety_limits": {"max_tokens": 512, "temperature": 0.7}
}
```

## Implementation Status

| Component | Status | Wired? | Notes |
|-----------|--------|--------|-------|
| Model registry (CRUD + routing) | Implemented | Yes | model-registry-service |
| Model runtime (OpenAI-compat) | Implemented | Yes | model-runtime-service |
| Model runtime (mock) | Implemented | Yes | Deterministic fallback |
| GameModelConfig | Implemented | Yes | `game_plugin.py` + `model_config.py` |
| ModelUsageTracker | Implemented | Yes | All model paths record usage |
| ChatPolicy | Implemented | Yes | Rate limiting, safety, operator override |
| Strategy model-assist | Implemented | **Wired** | decision-service calls model-runtime |
| Chat intent (model) | Implemented | **Wired** | chat-intent-service calls model-runtime |
| Chat reply (model) | Implemented | **Wired** | chat-response-service calls model-runtime |
| VLM perception | Implemented | **Wired** | perception-service vlm_provider.py |
| Orchestrator reads GameModelConfig | Implemented | **Wired** | `flow_controller._decide()` resolves model profile via `resolve_model_profile()` |
| Perception auto-routing VLM | Designed | **Not yet** | Provider exists; routing logic needed |
| Operator UI model telemetry | Designed | **Not yet** | Logs have data; UI exposure needed |
| Per-game config from config-service | Designed | **Not yet** | Config files exist; service integration needed |
