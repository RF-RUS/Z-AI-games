# perception-service

## Role
Evidence merger with confidence

## API Summary
POST /perceive

## Config
- Port: `8103`
- Health: `GET /health`

## Dependencies
none

## Local Dev
```bash
uvicorn uno_perception.api:app:app --host 127.0.0.1 --port 8103
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
