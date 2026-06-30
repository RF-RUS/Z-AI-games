# Web Adapter Architecture

## Modes

| Mode | Use case |
|------|----------|
| `mock` | CI, deterministic tests, no browser |
| `playwright` | Real browser automation |

## Data flow

```
WebAdapterProfile → PlaywrightSession → DomSnapshot + ScreenshotFrame
                                              ↓
                                        DomEvidence (confidence-scored)
                                              ↓
                                        perception-service → Observation
```

**Invariant:** `DomSnapshot.extracted` is adapter evidence, not canonical game state.

## Profile system

Profiles live in `services/adapter-web/profiles/*.json`. Schema: `WebAdapterProfile`.

Generic pieces (reusable):
- `runtime.py` — Playwright lifecycle
- `extraction.py` — profile-driven DOM normalization
- `profiles.py` — loader

UNO-specific interpretation happens in `perception-service` and `uno-core`.

## API surface

| Endpoint | Purpose |
|----------|---------|
| `GET /profiles` | List profiles |
| `POST /attach` | Start mock or Playwright session |
| `GET /adapters/{id}/evidence` | DomSnapshot + DomEvidence + screenshot |
| `POST /adapters/{id}/actions` | click/type/press |
| `POST /adapters/{id}/capture-fixture` | Export test fixtures |

## Local test target

`services/adapter-web/test-target/index.html` — deterministic UNO-like page for CI.

```powershell
python scripts/serve-test-target.py   # http://127.0.0.1:8765/
```

## Stubbed / planned

- External real UNO website profiles (not shipped — add your own profile JSON)
- PostgreSQL artifact storage (file-based in replay service for now)

## Screenshot trace

Visual trace captures screenshots at each pipeline step for debugging and the TracePanel UI.

See **[screenshot-trace.md](../runbooks/screenshot-trace.md)** for enable, architecture, logging, troubleshooting.
