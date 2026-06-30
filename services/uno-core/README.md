# uno-core

## Role
Canonical UNO rules engine

## API Summary
POST /games, GET /games/{id}/legal-actions

## Config
- Port: `8101`
- Health: `GET /health`

## Dependencies
none

## Local Dev
```bash
uvicorn uno_core.api:app:app --host 127.0.0.1 --port 8101
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
