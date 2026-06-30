# Full-Operator Evaluation

## Dataset format

`orchestrator/evaluation/datasets/*.jsonl` — one `OperatorScenario` per line.

Fields: `scenario_id`, `description`, `adapter_type`, `max_ticks`, `min_confidence`, `expected`, `scoring_weights`, `tags`.

## Run

```powershell
python scripts/evaluate-full-operator.py --dataset full_operator
```

Results: `models/benchmarks/results/{run_id}_full_operator.json`

## Metrics

- `success_rate`, `avg_score`, `policy_accept_rate`, `avg_ticks`
- Per scenario: `legal_action_ok`, `policy_pass_ok`, `flow_complete_ok`

## Compare configs

Run twice with different `SessionSpec` / strategy and diff JSON result files.

## Create scenarios

Add a JSONL row, set `expected` flags (`policy_allowed`, `min_ticks`, `no_fatal_error`).
