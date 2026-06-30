# state-replay-service

## Role
Event store and replay

## API Summary
POST /replays/{id}/events, GET /replays/{id}

## Config
- Port: `8102`
- Health: `GET /health`

## Dependencies
none

## Local Dev
```bash
uvicorn uno_replay.api:app:app --host 127.0.0.1 --port 8102
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
