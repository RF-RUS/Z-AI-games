# Operator Scenario Format

```json
{
  "scenario_id": "unique-id",
  "description": "human readable",
  "adapter_type": "mock",
  "max_ticks": 1,
  "min_confidence": 0.3,
  "model_assist": false,
  "initial_state": {},
  "expected": {
    "policy_allowed": true,
    "min_steps": 5,
    "no_fatal_error": true,
    "allow_guard_block": false
  },
  "scoring_weights": {
    "legal_action": 0.4,
    "policy_pass": 0.3,
    "flow_complete": 0.2,
    "no_error": 0.1
  },
  "tags": ["normal"]
}
```

`initial_state` is metadata for documentation; game state comes from uno-core seed.
