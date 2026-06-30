# Local Development Runbook

## Prerequisites

- Python **3.11+**
- Node.js **20+** (Control Center)
- [uv](https://docs.astral.sh/uv/)
- Docker (optional — Postgres/Redis)

## Setup

```powershell
.\scripts\setup-windows.ps1
```

See [USAGE.md](../USAGE.md) for manual setup if the script fails.

## Start stack

```powershell
docker compose up -d          # optional: postgres + redis
.\scripts\dev-backend.ps1     # FastAPI services :8100–8113
.\scripts\dev-desktop.ps1     # Control Center
```

## Health check

```powershell
.\scripts\smoke-check.ps1
```

## Common issues

| Symptom | Fix |
|---------|-----|
| Port in use | Kill process on 8100–8113 |
| Import errors | `uv sync --all-packages` from repo root |
| Model registry empty | Check `models/registry/` exists |
| setup-windows.ps1 fails | Ensure it is PowerShell, not batch — see [USAGE.md](../USAGE.md) |

## Logs

- Service stdout from `dev-backend.ps1` windows
- Observability API: `http://127.0.0.1:8112/logs`

## More

Full workflows: [USAGE.md](../USAGE.md)
