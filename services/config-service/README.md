# config-service

## Role
Feature flags and config

## API Summary
GET /config, GET /features

## Config
- Port: `8113`
- Health: `GET /health`

## Dependencies
none

## Local Dev
```bash
uvicorn uno_config.api:app:app --host 127.0.0.1 --port 8113
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
