# Playwright Debugging Runbook

## Prerequisites

```powershell
pip install playwright
python -m playwright install chromium
```

## Health check

```powershell
curl http://127.0.0.1:8104/playwright/check
curl "http://127.0.0.1:8104/network/check?url=https://scuffeduno.online/"
```

## Scuffed Uno (`scuffed-uno-web`)

| Topic | Detail |
|-------|--------|
| Profile | `services/adapter-web/profiles/scuffed-uno-web.json` |
| Navigation | `goto_wait_until=commit` (not `domcontentloaded`) |
| Readiness | Optional soft wait (`readiness_required=false`) |
| In-match | Canvas coordinates via `layout_targets` + `CLICK_COORDINATE` |
| Attach timeout | 120s HTTP (orchestrator → adapter-web) |
| Evidence timeout | 120s (`web_evidence` after attach) |

### Root cause pattern (2026-06-15)

- Plain HTTP to site: **OK**
- Playwright `page.goto(domcontentloaded)`: **hang ~60s**
- Fix: `commit` wait + separate readiness; full diagnostics in `startup_diagnostics.page_goto`

### Browser variants

```powershell
$env:UNO_PLAYWRIGHT_CHANNEL = "chrome"
# or
$env:UNO_PLAYWRIGHT_EXECUTABLE = "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

### Attach diagnostics in UI

Control Center attach failure panel shows:

- Failed stage (`browser_launch`, `context_page`, `page_goto`, `readiness_wait`, …)
- Stage timings, screenshot/trace/log paths
- `page_goto`: final URL, title, readyState, response chain, request failures, console errors, reachability

Trace propagation:

```powershell
python scripts/trace-web-attach-diagnostics.py
```

Orchestrator checkpoints: `web_attach_diagnostics_checkpoint_1..4`

## Common failures

| Symptom | Fix |
|---------|-----|
| `Playwright not installed` | `pip install playwright && python -m playwright install chromium` |
| Readiness timeout | Increase `readiness_timeout_ms`; for scuffed profile readiness is optional |
| `page_goto` timeout (60s) | Check `page_goto` diagnostics; try `goto_wait_until=commit`; try Chrome channel |
| Attach OK but cycle fails on observe | `capture_evidence` slow (~20s+); test `GET /adapters/{id}/evidence`; see [orchestrator-debugging.md](orchestrator-debugging.md) |
| Empty error in UI after attach | Restart backend after ReadTimeout formatting fix |
| UI attach timeout 3s | Client must use 120s for playwright attach — Control Center uses structured 502 parse |
| Empty `extracted` | Update profile selectors; use `capture-fixture` to inspect DOM |
| Screenshot fails in TestClient | Use async httpx tests for Playwright (see `tests/e2e/test_web_playwright.py`) |

## Debug artifacts

Enable trace on attach:

```json
{"session_id": "debug", "mode": "playwright", "record_trace": true}
```

Artifacts: `services/adapter-web/artifacts/{session_id}/`

Startup failure JSON: `startup-failure-{stage}.json` with nested `page_goto`.

## Headed mode

```json
{"headless": false}
```

## Local reproduction

```powershell
python scripts/serve-test-target.py
python scripts/capture-web-fixture.py --mode playwright --url http://127.0.0.1:8765/
```

## Resume checklist

See **[operator-debug-checkpoint.md](operator-debug-checkpoint.md)** — attach → warmup → first tick → perceive/decide steps.
