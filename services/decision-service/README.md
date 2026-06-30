# decision-service

## Role
Legal-action-only policies

## API Summary
POST /decide

## Config
- Port: `8106`
- Health: `GET /health`

## Dependencies
model-runtime (optional)

## Local Dev
```bash
uvicorn uno_decision.api:app:app --host 127.0.0.1 --port 8106
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
