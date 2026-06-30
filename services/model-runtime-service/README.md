# model-runtime-service

## Role
Provider abstraction (mock, llama.cpp OpenAI, vLLM OpenAI), prompt registry, benchmarks.

## API
- `POST /invoke` — primary advisory invocation
- `POST /benchmark/run` — reproducible JSONL benchmarks
- `GET /prompts` — versioned prompt assets
- `GET /providers/{provider}/health`

## Config
- Port: `8111`
- `UNO_MODEL_PROFILES_PATH` — profile JSON dir
- `UNO_MODEL_REGISTRY_URL` — registry for auto-routing

## Local Dev
```powershell
uvicorn uno_model_runtime.api:app --host 127.0.0.1 --port 8111
python scripts/benchmark-run.py --dataset chat_intent
python scripts/model-health.py
```

See `docs/architecture/model-runtime.md`.
