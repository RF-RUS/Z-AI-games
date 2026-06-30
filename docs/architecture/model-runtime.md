# Model Runtime

## Providers

| Provider | Config |
|----------|--------|
| `mock` | No external deps |
| `llama_cpp_openai` | `base_url` → llama-server OpenAI API |
| `vllm_openai` | `base_url` → vLLM OpenAI API |

## Flow

```
ModelProfile → Provider → ModelInvocationResponse (advisory)
                              ↓
                    decision/chat/perception (never uno-core truth)
```

## API

- `POST /invoke` — primary invocation with prompt registry
- `POST /benchmark/run` — reproducible benchmarks
- `GET /providers/{provider}/health`

## Stubbed

- Streaming responses
- Multimodal image input via OpenAI providers (flag only)
- GPU auto-discovery
