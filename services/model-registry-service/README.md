# model-registry-service

## Role
Model profiles, routing by use case, manifest catalog.

## API
- `GET /models` — legacy manifests
- `GET /profiles` — routable profiles
- `POST /route` — `{"use_case": "chat_intent"}` → profile selection
- `POST /defaults` — set default profile per use case
- `POST /profiles/{id}/disable` — quick disable misbehaving runtime

## Config
- Port: `8110`
- Profiles: `models/profiles/*.json`

## Local Dev
```powershell
uvicorn uno_model_registry.api:app --host 127.0.0.1 --port 8110
python scripts/registry-status.py
```

See `docs/runbooks/model-provider-setup.md`.
