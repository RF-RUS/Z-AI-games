# Fixture Capture Runbook

## Capture from mock (no browser)

```powershell
python scripts/capture-web-fixture.py --mode mock
```

Output: `tests/fixtures/web_adapter/local-mock-uno_*`

## Capture from Playwright + local test page

```powershell
# Terminal 1
python scripts/serve-test-target.py

# Terminal 2
python scripts/capture-web-fixture.py --mode playwright --url http://127.0.0.1:8765/
```

## Capture from real Pizzuno (network)

```powershell
python scripts/capture-web-fixture.py --mode playwright --profile real-unoh-web --output tests/fixtures/web_adapter/real-unoh
```

Requires Playwright + network. See [real-unoh-web-profile.md](real-unoh-web-profile.md).

## Files produced

| File | Content |
|------|---------|
| `*_dom_snapshot.json` | `DomSnapshot` with nodes + extracted |
| `*_dom_evidence.json` | `DomEvidence` for perception-service |
| `*_meta.json` | metadata summary |
| `*_screenshot.png` | viewport capture (playwright only) |

## Use in tests

`tests/integration/test_web_adapter_pipeline.py::test_fixture_file_perception_pipeline`

## Live capture via API

```powershell
# After attach
curl -X POST "http://127.0.0.1:8104/adapters/{id}/capture-fixture"
```
