# observability-service

## Role
Logs and metrics

## API Summary
POST /logs, GET /metrics

## Config
- Port: `8112`
- Health: `GET /health`

## Dependencies
none

## Local Dev
```bash
uvicorn uno_observability.api:app:app --host 127.0.0.1 --port 8112
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
