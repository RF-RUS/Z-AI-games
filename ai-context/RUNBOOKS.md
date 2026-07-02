# RUNBOOKS

Index + gap-fillers only. Existing `docs/runbooks/*` are canonical; do not duplicate them here.

## Existing (load the named file on demand)
| Need | Runbook |
|------|---------|
| Setup (Windows) | `scripts/setup-windows.ps1`; `docs/runbooks/local-dev.md` |
| Local run | `scripts/dev-backend.ps1` (8100–8113), `scripts/dev-desktop.ps1` (5173); `docs/runbooks/starting-a-session.md` |
| Tests | `scripts/run-tests.ps1`; markers in root `pyproject.toml`; `docs/architecture/test-strategy.md` |
| Health check | `scripts/smoke-check.ps1` |
| Session debug | `docs/runbooks/operator-debug-checkpoint.md`, `orchestrator-debugging.md`, `orchestrator-recovery-strategies.md` |
| Web automation | `docs/runbooks/playwright-debugging.md`, `real-unoh-web-profile.md`, `web-profiles.md`, `screenshot-trace.md` |
| Windows automation | `docs/runbooks/windows-uia-debugging.md`, `windows-target-profiles.md` |
| Model provider | `docs/runbooks/model-provider-setup.md`, `prompt-versioning.md` |
| Fixtures | `docs/runbooks/fixture-capture.md` |

## Quick commands
```
# backend + UI
.\scripts\dev-backend.ps1 ;  .\scripts\dev-desktop.ps1
.\scripts\smoke-check.ps1
# tests
python -m pytest tests/unit -x
python -m pytest tests/smoke -m smoke -k "not pizzuno"
python -m pytest tests/integration
# lint / security / coverage gate (60)
ruff check . ;  bandit -r services/ packages/ -ll --skip B101
# session
python scripts/serve-test-target.py
python scripts/start-orchestrator-session-web.py --profile local-mock-uno --url http://127.0.0.1:8765/ --tick
```

## Gaps (no runbook yet — write when first needed)
- **Migrations:** none required in normal dev (Postgres/Redis are optional via `docker-compose.yml`, event bus defaults to `memory`). If a service adds persistent schema, add a runbook then.
- **Deploy:** no Docker prod deploy yet (roadmap). Ship = merge to `main`, CI must be green.
- **Rollback:** git revert the PR/commit + redeploy; no stateful migration to unwind today.
- **Incident (live game session):** capture trace under `artifacts/`, note profile + service ports, follow `operator-debug-checkpoint.md`; escalate to human operator (platform is human-in-the-loop by design).
