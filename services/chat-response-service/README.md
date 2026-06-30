# chat-response-service

## Role
Safe chat replies

## API Summary
POST /reply

## Config
- Port: `8109`
- Health: `GET /health`

## Dependencies
model-runtime (optional)

## Local Dev
```bash
uvicorn uno_chat_response.api:app:app --host 127.0.0.1 --port 8109
```

## Tests
See `tests/` — unit, contract, integration coverage.

## Integration
Reusable standalone via HTTP. See `docs/integration/`.
