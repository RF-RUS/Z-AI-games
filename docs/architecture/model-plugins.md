# Model Plugin Architecture

## ModelManifest

All models registered via `ModelManifest` schema (`packages/schemas`).

## Registry Layout

```
models/
  registry/           # JSON manifests
  cache/              # Downloaded weights
  benchmarks/         # Benchmark datasets
```

## Adding a Model

1. Create manifest JSON in `models/registry/{model_id}.json`
2. Set `runtime`: `llama_cpp` | `vllm` | `mock`
3. Set `capabilities` and `modality`
4. POST `/models/install` to register
5. POST `/models/{id}/activate` to enable

## Experimental Profile

`waltgrace/poker-gemma4-26b-a4b-lora` — card-game tuned LoRA, disabled by default.

## Runtime Adapters

| Adapter | File | Status |
|---------|------|--------|
| mock | `model-runtime-service/adapters.py` | Ready |
| llama_cpp | same | Stub — wire llama-server |
| vllm | same | Stub — wire OpenAI-compatible API |

## Benchmark

```powershell
# Dataset: models/benchmarks/default.json
curl -X POST http://127.0.0.1:8111/infer -H "Content-Type: application/json" -d '{"model_id":"mock/uno-assistant","prompt":"test","correlation_id":"b1"}'
```

## Safety

Model outputs are normalized to `InferenceResponse`. Never applied to game state without `policy-guard` + `uno-core` validation.
