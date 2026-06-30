# Test Strategy

## Layers

| Layer | Path | Purpose |
|-------|------|---------|
| Unit | `tests/unit/` | Rules, merger, policies |
| Contract | `tests/contracts/` | Schema roundtrips |
| Integration | `tests/integration/` | Multi-service pipeline |
| Smoke | `tests/smoke/` | Health, boot |
| E2E | `tests/e2e/` | Mock adapter simulations |

## Fixtures

`tests/fixtures/` — replays, DOM snapshots, UI trees

## Markers

```bash
pytest -m smoke
pytest -m contract
pytest -m integration
pytest -m e2e
```

## CI Recommendation

1. `pytest tests/unit tests/contracts` — always
2. `pytest tests/smoke tests/integration` — on PR
3. `pytest -m e2e` — nightly
