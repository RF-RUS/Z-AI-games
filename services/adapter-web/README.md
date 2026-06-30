# adapter-web

Browser observation and execution service — reusable outside UNO.

## Modes

| Mode | API `mode` value | Browser required |
|------|------------------|------------------|
| Mock | `mock` | No |
| Playwright | `playwright` | Yes (`playwright install chromium`) |

## API Summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/profiles` | List `WebAdapterProfile` |
| GET | `/profiles/{id}` | Get profile |
| POST | `/attach` | `AttachWebAdapterRequest` → session |
| GET | `/adapters/{id}/dom` | Extracted dict (legacy) |
| GET | `/adapters/{id}/evidence` | `AdapterEvidenceBundle` |
| POST | `/adapters/{id}/actions` | `ActionExecutionRequest` |
| GET | `/adapters/{id}/screenshot` | PNG file |
| POST | `/adapters/{id}/capture-fixture` | Export test fixtures |
| POST | `/adapters/{id}/detach` | Close session |
| GET | `/playwright/check` | Dependency check |

## Config

- Port: `8104`
- Profiles: `services/adapter-web/profiles/`
- Test target: `services/adapter-web/test-target/`
- Artifacts: `services/adapter-web/artifacts/`

## Local Dev

```powershell
python scripts/serve-test-target.py
uvicorn uno_adapter_web.api:app --host 127.0.0.1 --port 8104
```

## Tests

```powershell
python -m pytest tests/unit/test_adapter_web_profiles.py -v
python -m pytest tests/contracts/test_adapter_web.py -v
python -m pytest tests/e2e/test_web_playwright.py -v
```

## Integration

- [Web adapter architecture](../../docs/architecture/web-adapter.md)
- [Reuse in other projects](../../docs/integration/using-adapter-web-in-other-projects.md)
- [Profile authoring](../../docs/integration/web-profiles.md)

**Invariant:** outputs are evidence with confidence — never canonical game state.
