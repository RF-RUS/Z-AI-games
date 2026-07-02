# PROJECT_MEMORY

Always-loaded. Keep < ~120 lines. Facts only.

## Identity
- Game Agent Platform (repo `RF-RUS/Z-AI-games`, pkg name `uno-operator`). Human-in-the-loop, plugin-based, universal turn-based game agent.
- UNO is the first plugin, **not** the architecture center. Svintus is the second (proves multi-game).
- Model-capable, model-optional: heuristic / template / rule paths are always valid fallbacks.

## Stack
- Backend: Python 3.11+ (CI runs 3.12), FastAPI, Pydantic, `uv` workspace.
- Frontend: TypeScript, React 18, Vite 5, Electron 31 (Control Center).
- Automation: Playwright (Chromium) for web, pywinauto/UIA for Windows.
- Tests: pytest (Python), vitest (control-center TS).

## Repo shape
- `services/*` — 14 FastAPI microservices, each `src/<pkg>/` + `pyproject.toml` + `README.md`.
- `packages/schemas` — shared Pydantic contracts (`uno_schemas`). **Contract source of truth.**
- `packages/shared-utils` — logging + HTTP helpers. `packages/client-sdk-{python,ts}`.
- `apps/control-center` — Electron + React operator UI.
- `docs/**` — architecture, integration, runbooks. `scripts/*` — setup/dev/eval (`.ps1` + `.py`).
- `tests/{unit,integration,contracts,smoke,e2e}`.

## Pipeline (canonical data flow)
Adapters → `ObservedState`/`RawAffordances` → PerceptionPlugin → `InferredState`
→ RulesPlugin → `LegalActions` (rules ∩ affordances) + reconciled `Affordances`
→ StrategyPlugin → `DecisionResult` → ExecutionPlugin → `ExecutionPlan` → adapters.
`Uncertainty` + `VerifiedResult` flow back to orchestrator/UI.
Full spec: `docs/architecture/intermediate-contract.md`.

## INVARIANTS — do not break casually
1. **Contracts live in `packages/schemas`.** Change a pipeline model there, not inline in a service. Contract changes ripple to all plugins — treat as breaking.
2. **Plugin boundaries are hard** (`docs/architecture/plugin-interfaces.md`):
   - PerceptionPlugin: sees UI, never rules/strategy/execution.
   - RulesPlugin: sees `InferredState`+`RawAffordances`, **never DOM/selectors/coords**.
   - StrategyPlugin: sees state/legal/affordances, **never raw UI**.
   - ExecutionPlugin: sees decision/affordances, **never rules/strategy logic**.
   - `GameModelConfig` is declarative; plugins never call models directly — platform resolves/routes.
3. **Generic vs per-game:** orchestrator, adapters, policy-guard, replay, perception dispatch, operator UI, trace are game-agnostic. Game logic lives in `uno-core`, `svintus-core`, and per-game plugins. Do not leak game specifics into generic services.
4. **Adding a game = plugins + adapter profile, no core edits.** New DOM target = new profile JSON in `adapter-web/profiles/`, not adapter code changes.
5. **Env var prefix is `UNO_`** and many Python packages are `uno_*` — legacy naming from before the platform rename. Keep it; do not mass-rename.

## Conventions
- Python: ruff (`line-length=100`, select `E,F,I,UP`), `target-version=py312`. bandit clean (`-ll`, skip B101).
- Coverage gate: `fail_under=60`.
- pytest markers: `smoke` (no network/live), `contract`, `integration` (may need live services), `e2e` (network/browser/real windows). `asyncio_mode=auto`.
- pytest `pythonpath` is set in root `pyproject.toml` — services import by package name, not relative paths.
- Model calls are logged via `ModelUsageTracker`; chat gated by `ChatPolicy`.

## Service ports
8100 orchestrator · 8101 uno-core · 8102 state-replay · 8103 perception · 8104 adapter-web · 8105 adapter-windows · 8106 decision · 8107 policy-guard · 8108 chat-intent · 8109 chat-response · 8110 model-registry · 8111 model-runtime · 8112 observability (planned) · 8113 config-service. Control Center 5173.

## Drift / failure risks
- **Port 8113 collision:** README/config-service and STATE.md/svintus-core both claim 8113. Verify before binding.
- **CI is Ubuntu-only:** `adapter-windows` (pywinauto/UIA) is untested in CI; validate Windows changes locally.
- Dev scripts are PowerShell (`.ps1`, Windows-first). No Docker prod deploy yet; observability = structured logs only.
- `scuffed-uno-web` (canvas/CV) is the active sprint; E2E canvas gameplay **not confirmed**. Don't assume it works.
- Contract edits without updating all consuming plugins → silent pipeline breakage (caught by `tests/contracts`).
- Requires-python is 3.11+ but ruff/CI target 3.12 — avoid 3.12-only syntax if 3.11 support matters.

## Status
Beta (~85%). CI designed (lint→unit→smoke-mock→integration) + nightly-e2e; treat as needs-validation.
