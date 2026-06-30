# chat-intent-service

## Role
Chat intent detection

## API Summary
POST /detect

## Config
- Port: `8108`
- Health: `GET /health`

## Dependencies
none

## Local Dev
```bash
uvicorn uno_chat_intent.api:app:app --host 127.0.0.1 --port 8108
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
