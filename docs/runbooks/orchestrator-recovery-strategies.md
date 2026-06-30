# Recovery Strategies

| Error class | Default action |
|-------------|----------------|
| transient | retry with backoff |
| perception_low_confidence | retry |
| policy_blocked | pause loop |
| permanent | fallback mock → manual → stop |

Configure via `SessionSpec.recovery`:

```json
{"max_retries": 3, "backoff_ms": 500, "fallback_to_mock": true, "fallback_to_manual": true}
```

Scenarios: `orchestrator/scenarios/benchmark.jsonl`
