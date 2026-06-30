# session-orchestrator

## Role
End-to-end operator session lifecycle and flow control.

## API
- `POST /sessions` — create with game + replay id
- `POST /sessions/{id}/attach-adapter`
- `POST /sessions/{id}/start|pause|resume|stop`
- `POST /sessions/{id}/tick` — manual step
- `GET /sessions/{id}/status|steps`

## Port
8100

## Dev
```powershell
python scripts/start-orchestrator-session-web.py --tick
python scripts/orchestrator-status.py
```

See `docs/architecture/orchestrator.md`.
