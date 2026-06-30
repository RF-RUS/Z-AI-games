# Screenshot Trace Pipeline

Visual trace captures screenshots at each pipeline step (observe, execute before/after) for debugging and the TracePanel UI.

**This pipeline is game-agnostic.** It traces adapter execution for any game — UNO, chess, poker, or custom. The `meta.json` fields are game-specific (populated by the perception plugin), but the trace capture mechanism is generic.

## Feature flag

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_SCREENSHOT_TRACE` | `0` | `1` to enable tracing |
| `AGENT_SCREENSHOT_TRACE_DIR` | `artifacts/agent_trace` | Root directory for trace files |

Must be set in **every process** that runs trace code. The adapter-web process on port 8104 and the session-orchestrator process on port 8100 both need these env vars.

## How to enable

Set in `scripts/dev-backend.ps1` before starting services:

```powershell
$env:AGENT_SCREENSHOT_TRACE = "1"
$env:AGENT_SCREENSHOT_TRACE_DIR = "services\artifacts"
```

Verify with:

```powershell
curl http://127.0.0.1:8104/trace/debug
# {"env_trace_enabled":"1","trace_enabled":true,"base_dir":"services\\artifacts",...}
```

## Architecture

```
flow_controller._observe()
  → adapter_client.capture_evidence()
    → playwright_adapter.capture_evidence()
      → runtime.py PlaywrightSession.capture_evidence()
        → TraceManager.capture_observe()        # saves 001_observe/
        → (CV pipeline for canvas profiles)

flow_controller._execute()
  → adapter_client.execute_action()
    → runtime.py PlaywrightSession.execute()
      → TraceManager.capture_execute_before()   # saves 002_execute/
      → (mouse click / keyboard action)
      → TraceManager.capture_execute_after()    # saves 002_execute/
```

## Directory layout

```
services/artifacts/{session_id}/
├── screenshot-{timestamp}.png          # PlaywrightSession legacy screenshots
├── failure-{timestamp}.png             # PlaywrightSession failure captures
├── 001_observe/
│   ├── frame.png                       # Exact screenshot used for evidence
│   └── meta.json                       # timestamp, session_id, phase, url, viewport, game-specific fields
├── 002_execute/
│   ├── before.png                      # Screenshot before action
│   ├── after.png                       # Screenshot after action
│   └── meta.json                       # action details, grounding (game-specific)
└── ...
```

**Note**: `meta.json` contains game-specific fields (e.g., UNO: `screen`, `cv.hand_cards`, `cv.top_card`). These are populated by the perception plugin, not the trace pipeline.

## Key files

| File | Role |
|------|------|
| `services/adapter-web/src/uno_adapter_web/agent_trace.py` | `TraceManager` — writes step dirs, frame.png, meta.json |
| `services/adapter-web/src/uno_adapter_web/runtime.py` | `PlaywrightSession.capture_evidence()` — calls TraceManager |
| `services/adapter-web/src/uno_adapter_web/api.py` | `/trace/debug`, `/trace/{id}/steps`, `/trace/{id}/latest-frame` endpoints |

## API endpoints (adapter-web :8104)

| Endpoint | Purpose |
|----------|---------|
| `GET /trace/debug` | Shows env vars, base_dir, session count |
| `GET /trace/sessions` | Lists all sessions with step counts |
| `GET /trace/{session_id}/steps` | Lists step directories with metadata |
| `GET /trace/{session_id}/latest-frame` | Serves latest frame.png |
| `GET /trace/{session_id}/latest-meta` | Serves latest meta.json |

## Logging

When tracing is enabled, the adapter-web logs contain these structured messages per cycle:

| Log message | Meaning |
|-------------|---------|
| `trace_observe_calling` | runtime.py about to call capture_observe |
| `trace_observe_entered` | capture_observe entered, checks enabled/base_dir |
| `trace_observe_frame_written` | frame.png written successfully |
| `trace_observe_meta_written` | meta.json written successfully |
| `trace_observe_skipped` | capture_observe skipped (env not set) |
| `trace_observe_failed` | capture_observe threw an exception |
| `capture_evidence_screenshot_failed` | Outer screenshot capture failed |
| `trace_execute_before_failed` | capture_execute_before failed |
| `trace_execute_after_failed` | capture_execute_after failed |

## Known bug fix (2026-06-22)

### Root cause

In `runtime.py`, the call to `capture_observe` included `Image.open(screenshot_path)` as a function argument for DOM profiles:

```python
# BEFORE (broken)
await TraceManager.capture_observe(
    session_id, step, page, raw_screenshot,
    img if match_automation == "canvas_coordinate" else Image.open(screenshot_path),
    extracted, grounding,
)
```

If `Image.open(screenshot_path)` raised an exception (file lock, PNG encoding issue, Windows timing), the exception occurred **in the caller scope** — before `capture_observe` was invoked. The outer `except Exception:` silently caught it, so:

1. `capture_observe()` was **never called**
2. No step directories were created
3. No error was logged

### Fix

1. Removed `Image.open(screenshot_path)` from `capture_observe` arguments — the function never used the PIL Image, it wrote `screenshot_bytes` directly
2. Removed the unused `img: Image.Image` parameter from `capture_observe` signature
3. Wrapped all trace calls in their own `try/except` with logging
4. Added logging to the outer `except Exception:` in `capture_evidence`

```python
# AFTER (fixed)
try:
    await TraceManager.capture_observe(
        session_id, step, page, raw_screenshot,
        extracted, grounding,
    )
except Exception as trace_exc:
    logger.warning("trace_observe_failed session=%s error=%s", session_id, trace_exc)
```

## Known bug fix (2026-06-23) — Hero image 404 on Windows

### Root cause

Backend API `/trace/{session_id}/steps` returned `step.path` as full filesystem path (e.g., `E:\dev\AI-games\services\artifacts\session123\001_observe`). Frontend `TracePanel.tsx` did `step.path.split("/").pop()` to extract the step directory name.

On Windows, paths use backslashes (`\`), so `split("/")` didn't split anything. `.pop()` returned the **entire path** instead of just `001_observe`.

This caused the image URL to become:
```
http://127.0.0.1:8104/trace/{id}/E:\dev\AI-games\...\001_observe/frame.png
```

The API returned 404 → hero showed empty/dark container (black screen).

### Fix

1. **Backend**: Added `step_dir_name` field to `/trace/{session_id}/steps` response — contains just the directory name (e.g., `001_observe`)
2. **Frontend**: Uses `step.step_dir_name` directly instead of parsing `step.path`
3. **Frontend**: Updated `TraceStep` interface to include `step_dir_name`

### Files changed

- `services/adapter-web/src/uno_adapter_web/api.py` — added `step_dir_name` to steps response
- `apps/control-center/src/unoApiClient.ts` — added `step_dir_name` to `TraceStep` interface
- `apps/control-center/src/TracePanel.tsx` — uses `step_dir_name` instead of path parsing

### Regression tests

- `tests/unit/test_trace_step_dir_name.py` — verifies `step_dir_name` is returned correctly
- Tests cover: Windows backslash paths, Unix forward slash paths, mixed separators, single directory names

## Known bug fix (2026-06-23) — Hero flicker/black during polling

### Root cause

Even after the path fix, the hero image flickered black every 3 seconds. Backend returned 200 OK on all trace endpoints, but the UI still broke.

**200 OK does not prove correct UX.** The bug was in frontend state management:

1. Every 3s poll: `setSteps(newData)` creates new array → `setInternalSelected(data[last])` creates new object
2. React sees `selectedStep` changed (new object reference) → re-renders `<img>` with same `src`
3. React discards the loaded image, mounts new `<img>`, browser re-fetches the same URL
4. During load: hero is black/empty → load completes → visible → 3s later → repeat

### Why network 200 OK is insufficient

| Signal | What it proves | What it doesn't prove |
|--------|---------------|----------------------|
| `GET /trace/{id}/steps` → 200 | Backend returns step list | That frontend stable-selects a step |
| `GET /trace/{id}/022_observe/frame.png` → 200 | Image exists and serves | That `<img>` stays mounted across polls |
| Network tab shows image loaded | Image was fetched at least once | That it wasn't immediately re-fetched next poll |

**Correct verification requires checking console logs across multiple poll cycles**, not just a single network request.

### Fix

1. **Selection by step number** (`selectedStepNum: number`), not object reference
2. **Derived via `useMemo`**: `selectedStep = steps.find(s => s.step === selectedStepNum)` — only recomputes when `steps` or `selectedStepNum` changes
3. **Stable `<img key={heroSrc}>`** — React only remounts when URL actually changes
4. **Poll only updates `steps` array** — selection stays stable unless user clicks a different step

### Files changed

- `apps/control-center/src/TracePanel.tsx` — stable selection, memoized derivation, key on URL

### What to check in console (correct verification)

After cold restart + select step + wait for 3+ poll cycles:

```
[TracePanel] step selected: { step: 22, step_dir_name: "022_observe" }
[TracePanel] hero img src: ...022_observe/frame.png
[TracePanel] image loaded: ...022_observe/frame.png
[TracePanel] render: { stepsLen: 5, selectedStepNum: 22, imageLoaded: true }
[TracePanel] render: { stepsLen: 5, selectedStepNum: 22, imageLoaded: true }  ← stable
[TracePanel] render: { stepsLen: 6, selectedStepNum: 22, imageLoaded: true }  ← still stable
```

**Wrong** (old behavior):
```
[TracePanel] render: { selectedStepNum: 22, imageLoaded: true }
[TracePanel] image failed: ...022_observe/frame.png    ← re-fetch triggered
[TracePanel] render: { selectedStepNum: 22, imageLoaded: false }  ← flicker
[TracePanel] image loaded: ...022_observe/frame.png
[TracePanel] render: { selectedStepNum: 22, imageLoaded: true }
```

**Correct** (after fix):
```
[TracePanel] render: { selectedStepNum: 22, imageLoaded: true }
[TracePanel] render: { selectedStepNum: 22, imageLoaded: true }  ← no re-fetch
[TracePanel] render: { selectedStepNum: 22, imageLoaded: true }  ← no re-fetch
```

## Verification after restart

1. Start services: `.\scripts\dev-backend.ps1`
2. Check env: `curl http://127.0.0.1:8104/trace/debug`
3. Start a session, wait for observe cycle
4. Check disk: `services/artifacts/{session_id}/001_observe/` should contain `frame.png` + `meta.json`
5. Check API: `curl http://127.0.0.1:8104/trace/{session_id}/steps` should return non-empty array with `step_dir_name` field
6. Check UI: TracePanel should show hero screenshot that stays stable across polls
7. Check console: `imageLoaded: true` persists across multiple `[TracePanel] render:` logs
8. Check console: no `image failed` warnings after initial load
9. Check Network: `frame.png` request appears once, not repeated every 3s

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `/trace/debug` shows `env_trace_enabled: "NOT_SET"` | Env var not set in this process. Restart with dev-backend.ps1 |
| `/trace/{id}/steps` returns `[]` | No step dirs on disk. Check logs for `trace_observe_skipped` or `trace_observe_failed` |
| `frame.png` exists but no `meta.json` | `write_meta` failed. Check logs for `write_meta_failed` |
| Step dirs exist but TracePanel shows nothing | Reader path mismatch. Verify `TraceManager.base_dir()` matches `/trace/debug` base_dir |
| `latest-frame` returns 404 | No step dirs for this session. Same root cause as empty steps |
| Hero image flickers black every 3s | Object reference instability — check console for repeated `image failed` + `image loaded` cycles. Fix: selection by step number, not object ref |
| Hero shows black despite 200 OK in Network | Check console `[TracePanel] render` logs — if `imageLoaded` toggles true/false, selection is unstable |
| `step_dir_name` is `undefined` in console | Backend not restarted after API change. Restart `dev-backend.ps1` |
