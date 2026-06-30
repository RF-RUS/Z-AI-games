#!/usr/bin/env python3
"""Generate per-service README files."""

from pathlib import Path

SERVICES = {
  "uno-core": ("Canonical UNO rules engine", "8101", "none", "POST /games, GET /games/{id}/legal-actions"),
  "session-orchestrator": ("Session lifecycle orchestration", "8100", "perception, decision, policy", "POST /sessions, POST /sessions/{id}/tick"),
  "state-replay-service": ("Event store and replay", "8102", "none", "POST /replays/{id}/events, GET /replays/{id}"),
  "perception-service": ("Evidence merger with confidence", "8103", "none", "POST /perceive"),
  "adapter-web": ("Playwright web adapter", "8104", "playwright", "POST /attach, GET /adapters/{id}/dom"),
  "adapter-windows": ("Windows UI automation adapter", "8105", "pywinauto (optional)", "POST /attach, GET /adapters/{id}/ui-tree"),
  "decision-service": ("Legal-action-only policies", "8106", "model-runtime (optional)", "POST /decide"),
  "policy-guard": ("Safety validation", "8107", "none", "POST /guard/decision, POST /guard/chat"),
  "chat-intent-service": ("Chat intent detection", "8108", "none", "POST /detect"),
  "chat-response-service": ("Safe chat replies", "8109", "model-runtime (optional)", "POST /reply"),
  "model-registry-service": ("Model catalog", "8110", "none", "GET /models, POST /models/install"),
  "model-runtime-service": ("Unified inference", "8111", "llama.cpp/vLLM", "POST /infer, POST /load"),
  "observability-service": ("Logs and metrics", "8112", "none", "POST /logs, GET /metrics"),
  "config-service": ("Feature flags and config", "8113", "none", "GET /config, GET /features"),
}

TEMPLATE = """# {name}

## Role
{role}

## API Summary
{api}

## Config
- Port: `{port}`
- Health: `GET /health`

## Dependencies
{deps}

## Local Dev
```bash
uvicorn {module}:app --host 127.0.0.1 --port {port}
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
"""

MODULE_MAP = {
  "uno-core": "uno_core.api:app",
  "session-orchestrator": "uno_orchestrator.api:app",
  "state-replay-service": "uno_replay.api:app",
  "perception-service": "uno_perception.api:app",
  "adapter-web": "uno_adapter_web.api:app",
  "adapter-windows": "uno_adapter_windows.api:app",
  "decision-service": "uno_decision.api:app",
  "policy-guard": "uno_policy.api:app",
  "chat-intent-service": "uno_chat_intent.api:app",
  "chat-response-service": "uno_chat_response.api:app",
  "model-registry-service": "uno_model_registry.api:app",
  "model-runtime-service": "uno_model_runtime.api:app",
  "observability-service": "uno_observability.api:app",
  "config-service": "uno_config.api:app",
}

root = Path(__file__).parent.parent
for name, (role, port, deps, api) in SERVICES.items():
  readme = root / "services" / name / "README.md"
  readme.parent.mkdir(parents=True, exist_ok=True)
  readme.write_text(
    TEMPLATE.format(name=name, role=role, port=port, deps=deps, api=api, module=MODULE_MAP[name]),
    encoding="utf-8",
  )
  print(f"Wrote {readme}")
