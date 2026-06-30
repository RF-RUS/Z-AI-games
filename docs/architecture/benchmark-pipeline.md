# Benchmark Pipeline

## Datasets

`models/benchmarks/datasets/*.jsonl` — JSONL `BenchmarkCase` rows.

## Run

```powershell
python scripts/benchmark-run.py --dataset chat_intent --profile mock/uno-assistant
curl -X POST http://127.0.0.1:8111/benchmark/run -H "Content-Type: application/json" -d "{\"dataset\":\"chat_intent\"}"
```

## Metrics

- success_rate, parse_success_rate
- latency p50/p95
- per-case exact_match for chat_intent

Results: `models/benchmarks/results/{run_id}.json`

## Prompt traceability

Each run records `prompt_id` + `prompt_version`.
