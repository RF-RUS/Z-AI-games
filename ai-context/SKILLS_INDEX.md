# SKILLS_INDEX

Project-specific skills. Each: when to load · files it concerns · tasks it handles · keep out.

## contract-editing
- **Load when:** changing any pipeline data model or adding a field consumed across services.
- **Concerns:** `packages/schemas/src/uno_schemas/*`; `docs/architecture/intermediate-contract.md`; `tests/contracts/`.
- **Handles:** add/modify `ObservedState`, `InferredState`, `LegalActions`, `Affordances`, `DecisionResult`, `ExecutionPlan`, `Uncertainty`, `VerifiedResult`; keep producers/consumers in sync.
- **Keep out:** UI, adapter internals, model runtime unless the field touches them.

## game-plugin-authoring
- **Load when:** adding/editing a game (UNO, Svintus, new game) or its perception/rules/strategy/execution plugin.
- **Concerns:** `services/perception-service/src/`, `services/decision-service/src/strategies/`, `services/{uno,svintus}-core/src/`, `services/adapter-web/profiles/`; `docs/architecture/plugin-interfaces.md`; `docs/integration/adding-adapters.md`.
- **Handles:** implement plugin protocols, register at service startup, add DOM profile JSON, wire heuristic + optional model path.
- **Keep out:** orchestrator, policy-guard, replay, operator UI (must stay game-agnostic).

## adapter-web-debug
- **Load when:** browser automation, selectors, CDP connect, profile capture, or canvas/CV (`scuffed-uno-web`) issues.
- **Concerns:** `services/adapter-web/`, `profiles/*.json`; `scripts/{capture-web-fixture,find-selectors,inspect-*,check_cdp}.py`; `docs/runbooks/{playwright-debugging,real-unoh-web-profile,web-profiles,screenshot-trace}.md`.
- **Handles:** flaky selectors, profile mismatch, screenshot trace, coordinate grounding.
- **Keep out:** rules/strategy logic; Windows adapter.

## adapter-windows-debug
- **Load when:** pywinauto/UIA desktop automation issues (Windows-only, not covered by CI).
- **Concerns:** `services/adapter-windows/`; `scripts/capture-windows-fixture.py`; `docs/runbooks/{windows-uia-debugging,windows-target-profiles}.md`.
- **Handles:** UIA tree inspection, window attach, desktop profiles. Verify locally on Windows.
- **Keep out:** web adapter; browser tooling.

## orchestrator-flow
- **Load when:** session lifecycle, tick loop, state machine, recovery, or flow-controller work.
- **Concerns:** `services/session-orchestrator/src/uno_orchestrator/{orchestrator,flow_controller,state_machine,recovery,clients}.py`; `docs/architecture/orchestrator.md`; `docs/runbooks/{orchestrator-debugging,orchestrator-recovery-strategies,starting-a-session}.md`.
- **Handles:** session start/stop, tick cadence, recovery strategy, in-process vs HTTP clients.
- **Keep out:** per-game logic; UI rendering.

## model-layer
- **Load when:** model routing, `GameModelConfig`, registry/runtime, chat intent/response, usage tracking, chat policy.
- **Concerns:** `services/{model-registry,model-runtime,chat-intent,chat-response}-service/`; `docs/architecture/{model-integration,model-plugins,model-runtime}.md`; `docs/runbooks/{model-provider-setup,prompt-versioning}.md`.
- **Handles:** provider setup (OpenAI-compatible/mock), model resolution, fallback paths, `ChatPolicy`, `ModelUsageTracker`.
- **Keep out:** adapters; game rules.

## operator-ui
- **Load when:** Control Center React/Electron changes.
- **Concerns:** `apps/control-center/src/**` (esp. `operator/`), `electron/`; `docs/runbooks/control-center-ui.md`; vitest specs.
- **Handles:** panels, polling hooks, trace/replay views, session setup, keyboard shortcuts.
- **Keep out:** Python services (interact only via SDK/HTTP contracts).

## ci-and-quality
- **Load when:** test/lint/coverage/CI pipeline work.
- **Concerns:** `.github/workflows/{ci,nightly-e2e}.yml`; root `pyproject.toml` (ruff/pytest/coverage); `scripts/{run-tests.ps1,smoke-check.ps1}`; `docs/architecture/test-strategy.md`.
- **Handles:** marker selection, coverage gate (60), Ubuntu-only limitation, adding jobs.
- **Keep out:** feature source unless fixing a specific failing test.
