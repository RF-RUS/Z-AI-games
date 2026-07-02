# LOAD_RULES

Always load `PROJECT_MEMORY.md`. Then load ONLY the rows matching the task. Pull service source last, on demand.

| Task | Load (in addition to PROJECT_MEMORY) | Do NOT load |
|------|--------------------------------------|-------------|
| **Bugfix** | failing test(s); the one service `src/`; relevant `docs/runbooks/*` | other services; full `docs/architecture/*` |
| **Feature (new game)** | `docs/architecture/plugin-interfaces.md`; `packages/schemas`; `docs/integration/adding-adapters.md`; a sibling plugin as template | unrelated services; UI |
| **Feature (pipeline/contract)** | `docs/architecture/intermediate-contract.md`; `packages/schemas`; each consuming plugin | UI, scripts |
| **Refactor** | target module + its tests + direct callers; `SKILLS_INDEX.md` | unrelated services; docs prose |
| **UI work** | `apps/control-center/src/**` (relevant view); `docs/runbooks/control-center-ui.md` | backend services |
| **Deployment** | `docker-compose.yml`; `.env.example`; `.github/workflows/*`; `scripts/*.ps1` | service internals |
| **Debug prod/live issue** | `docs/runbooks/operator-debug-checkpoint.md` + relevant `orchestrator-*`/`playwright-*`/`windows-uia-*` runbook; trace under `artifacts/` | schemas, UI |
| **Docs update** | only the specific `docs/**` file being edited | source code |
| **Onboarding / audit** | `README.md`; `docs/PROJECT_OVERVIEW.md`; `docs/architecture/overview.md`; `docs/ROADMAP.md`; `.mimocode/STATE.md` | service source |

## Guardrails
- Touching a pipeline model? Load `intermediate-contract.md` + all consumers first. Never edit a contract inline in a service.
- Crossing a plugin boundary? Re-read `plugin-interfaces.md` boundary table before writing.
- Unsure which service? Use `README.md` port/service table, then open one service only.
