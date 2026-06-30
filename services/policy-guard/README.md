# policy-guard

## Role
Safety validation

## API Summary
POST /guard/decision, POST /guard/chat

## Config
- Port: `8107`
- Health: `GET /health`

## Dependencies
none

## Local Dev
```bash
uvicorn uno_policy.api:app:app --host 127.0.0.1 --port 8107
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
