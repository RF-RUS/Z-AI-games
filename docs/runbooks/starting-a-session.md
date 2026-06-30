# Starting a Session

## Web (local mock)

```powershell
# Terminal 1
python scripts/serve-test-target.py

# Terminal 2
.\scripts\dev-backend.ps1

# Terminal 3
python scripts/start-orchestrator-session-web.py --profile local-mock-uno --url http://127.0.0.1:8765/ --tick
```

## Web (real Pizzuno)

Requires network + Playwright.

```powershell
.\scripts\dev-backend.ps1
python scripts/start-orchestrator-session-web.py --profile real-unoh-web --tick
```

Profile: `services/adapter-web/profiles/real-unoh-web.json`  
Runbook: [real-unoh-web-profile.md](real-unoh-web-profile.md)

## Windows (mock)

```powershell
.\scripts\dev-backend.ps1
python scripts/start-orchestrator-session-windows.py --tick
```

## Control Center

1. `.\scripts\dev-backend.ps1`
2. `.\scripts\dev-desktop.ps1`
3. **Operator** tab → New Session → Tick  
   Or **Dashboard** → Start Session

## API

```powershell
curl -X POST http://127.0.0.1:8100/sessions -H "Content-Type: application/json" -d "{\"config\":{\"adapter_type\":\"mock\",\"adapter_id\":\"pending\"}}"
```

## Evaluation (no backend)

```powershell
python scripts/evaluate-full-operator.py --dataset full_operator_smoke
```

See [USAGE.md](../USAGE.md) for full workflows.
