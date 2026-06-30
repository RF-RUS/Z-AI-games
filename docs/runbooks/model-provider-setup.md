# Model Provider Setup

## Mock (default)

No setup. Profile: `mock/uno-assistant`.

## llama.cpp server

```bash
# Example — see llama.cpp docs
llama-server -m model.gguf --port 8080
```

Enable profile `local/llama-cpp` in `models/profiles/local__llama-cpp.json`.

## vLLM

```bash
vllm serve <model> --port 8000
```

Enable profile `local/vllm`.

## Health check

```powershell
curl http://127.0.0.1:8111/providers/mock/health?profile_id=mock/uno-assistant
curl http://127.0.0.1:8111/providers/llama_cpp_openai/health?profile_id=local/llama-cpp
```

## Env

- `OPENAI_API_KEY` — placeholder for local servers (often `not-needed`)
- `UNO_MODEL_PROFILES_PATH` — profile JSON directory
