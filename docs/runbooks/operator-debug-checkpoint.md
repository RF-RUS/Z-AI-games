# Web / Windows Operator Debug Checkpoint

Practical notes from the web attach + post-attach lifecycle + Windows mock operator debugging session. Use this to resume work without re-discovering root causes.

**Related:** [orchestrator-debugging.md](orchestrator-debugging.md) · [playwright-debugging.md](playwright-debugging.md) · [windows-uia-debugging.md](windows-uia-debugging.md)

---

## What was fixed today

### Web attach diagnostics

- Orchestrator no longer drops `startup_diagnostics` on failed web attach (`AttachWebAdapterResponse.adapter_id` nullable, registry cleanup on fail, retry path preserves diagnostics).
- Diagnostics propagate: `adapter-web /attach` → orchestrator `SessionDetail.attach_startup_diagnostics` → `GET /sessions`, `GET /sessions/{id}/status`.
- Non-2xx attach responses (502) can include `{ message, session }` with full diagnostics — UI parses body regardless of HTTP status (`AttachAdapterFailedError`, `parse_attach_web_http_response`).
- Control Center shows attach failure immediately after failed attach (no polling race); tick disabled while `flow_state=attaching`.
- Checkpoint logs in orchestrator stdout: `web_attach_diagnostics_checkpoint_1..4` (HTTP body, parsed stage, session state).

### Root cause: web attach (Playwright navigation)

- Plain HTTP reachability to `scuffeduno.online` was OK (~200, ~300ms) — problem was **inside Playwright navigation**, not network.
- `page.goto(wait_until=domcontentloaded)` could hang ~60s on scuffeduno.
- Profile `scuffed-uno-web` softened: `goto_wait_until=commit`, readiness wait separate and optional (`readiness_required=false`).
- Added `PageGotoDiagnostics`: final URL, title, `document.readyState`, response chain, `requestfailed`, console errors, HTTP reachability check, browser launch mode.
- Browser variants via env/profile: `UNO_PLAYWRIGHT_CHANNEL=chrome`, `UNO_PLAYWRIGHT_EXECUTABLE`, launch args.
- Trace script: `python scripts/trace-web-attach-diagnostics.py`; reachability: `GET /network/check` on adapter-web.

### Post-attach / flow lifecycle (findings)

- Attach could succeed while the session later failed in the **active cycle**.
- Failing step: **`observe`** — specifically `web_evidence()` HTTP call to adapter-web (`capture_evidence` ~20–22s on live page).
- Step marker `observe` was logged **before** the real HTTP work finished → `/steps` showed `success: true` with `latency_ms: 0` even on failure.
- **`perceive` never started** in the failing scenario (failure before PERCEIVE step marker).
- `httpx.ReadTimeout("")` / `TimeoutError()` produce **empty** `str(exc)` → `detail.error=""`, useless UI.
- `decide_recovery` returned generic `"transient failure"` without exception text; **RETRY still set `flow_state=error`**; retry counter keyed by per-cycle `cid` (always 0).

### Post-attach / flow lifecycle (fixes)

| Fix | Where |
|-----|--------|
| `format_exception_message()` — never empty error text | `recovery.py` |
| Recovery `reason` includes exception message | `decide_recovery()` |
| `failed_step` tracking + step marked `success=false` with error | `flow_controller.py` |
| RETRY keeps `flow_state=active` (not unconditional error) | `flow_controller.py` |
| Retry counter keyed by `error_class` | `flow_controller.py` |
| `web_evidence` timeout **120s** (same as attach) | `clients.py` |
| Web `start()` stays **`attaching`** until warmup observe succeeds | `orchestrator.py` |
| Separate **cycle failure panel** in UI (not attach panel) | `sessionAttachErrors.ts`, `OperatorPanel.tsx` |

### Windows operator work

- Tkinter mock app did not publish control names in UIA/win32 tree → empty extracted state.
- Added **`layout_targets`** fallback (relative window coordinates) in profiles (`local-mock-uno.json`).
- Selector aliases: `draw` → `draw_button`, `play_red_five` → `play_button` (`target_locator.py`).
- Locator distinguishes **target not found** vs **confidence below threshold** (`visual_executor.py`).
- Visual executor no longer marks UNCERTAIN solely from `no_visible_change` on static UI (post-click verification relaxed for mock).
- After fixes: target found, click succeeded; next blocker was **post-action verification / static UI validation**, not acquisition.

---

## Current status (end of day)

| Area | Status |
|------|--------|
| Web attach (scuffed-uno-web) | Generally succeeds; diagnostics pipeline works |
| Post-attach warmup | Progress to `active` after observe warmup |
| End-to-end gameplay (scuffed uno) | **Not confirmed** — observe/perceive/decide/act loop not fully validated |
| Windows mock (local-mock-uno) | Target acquisition + click improved; verification still fragile on static UI |

**Last observed risk:** long/fragile `observe` / warmup (`capture_evidence` ~20s+) or subsequent active-cycle steps (perceive, legal_actions, decide).

---

## Known remaining issues

1. **E2E scuffed uno gameplay** — full tick through decide/execute not proven on live site.
2. **Observe latency** — `capture_evidence` (DOM extract + screenshot + page diagnostics) can exceed old 15s client timeout; now 120s but still slow.
3. **Step timing visibility** — step markers still logged before work; latency only on failure path today; consider wrapping work inside step for accurate `/steps`.
4. **Windows mock verification** — `no_visible_change` on static tkinter UI may still fail post-action checks after click succeeds.
5. **Canvas coordinate actions** — scuffed uno in-match automation uses `CLICK_COORDINATE`; lobby bootstrap may still need manual step.

---

## How to resume tomorrow

### Prerequisites

```powershell
.\scripts\dev-backend.ps1
.\scripts\dev-desktop.ps1   # optional Control Center
```

### Next debugging steps

1. **Create fresh web session** — Control Center → Web → profile `scuffed-uno-web` → New Session → Attach.
2. **Wait for full warmup** — after Start, session stays `attaching` until warmup observe completes (~20s+). Do not tick until `flow_state=active`.
3. **First full tick after active** — click Tick once; watch Operator cycle failure panel (if error) or steps list.
4. **Inspect failure details:**
   - `GET /sessions/{id}` → `error`, `flow_state`, `last_recovery`
   - `GET /sessions/{id}/steps` → last step with `success: false`, `step_name`, `result.error`
   - Orchestrator logs: `flow_cycle_failed` with `failed_step`, `error`, `error_type`, `recovery_reason`
5. **Verify downstream steps start** — after successful observe, confirm steps for `perceive`, `legal_actions`, `decide` appear in `/steps`.
6. **If hang/timeout again** — measure duration per stage:
   - Direct: `curl "http://127.0.0.1:8104/adapters/{adapter_id}/evidence?correlation_id=probe"`
   - Perception: `POST http://127.0.0.1:8103/perceive`
   - Log each flow step latency (future: add timing to `_run_step` wrapper).

### Quick CLI checks

```powershell
python scripts/orchestrator-status.py
python scripts/orchestrator-status.py <session_id>
python scripts/trace-web-attach-diagnostics.py
curl http://127.0.0.1:8104/network/check?url=https://scuffeduno.online/
```

### Log search patterns

```
web_attach_diagnostics_checkpoint_
web_observe_warmup_ok
web_observe_warmup_failed
flow_cycle_failed
```

### Attach failure (still relevant)

- UI: attach failure panel — stage timings, `page_goto` block, artifact paths.
- Backend 502 body includes `session.attach_startup_diagnostics`.
- Checkpoints 1–4 in orchestrator logs trace propagation.

### Windows mock resume

```powershell
python services/adapter-windows/test-target/uno_mock_app.py
python scripts/start-orchestrator-session-windows.py --tick
```

If click works but action marked uncertain — inspect verification in `visual_executor.py` / `ui_verifier.py`.

---

## Key files touched

| Layer | Files |
|-------|--------|
| Orchestrator | `flow_controller.py`, `orchestrator.py`, `recovery.py`, `clients.py`, `web_attach_trace.py`, `api.py` |
| Adapter web | `startup.py`, `runtime.py`, `navigation_diagnostics.py`, `profiles/scuffed-uno-web.json` |
| Adapter windows | `target_locator.py`, `visual_executor.py`, `profiles/local-mock-uno.json` |
| UI | `OperatorPanel.tsx`, `sessionAttachErrors.ts`, `unoApiClient.ts` |
| Tests | `test_flow_cycle_failure.py`, `test_web_attach_diagnostics_trace.py`, `test_attach_adapter_api.py`, `sessionAttachErrors.test.ts` |
