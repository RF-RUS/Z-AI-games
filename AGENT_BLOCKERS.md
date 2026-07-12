# AGENT_BLOCKERS

Real blockers only. Move to Resolved when cleared.

## Open

### B4 — perception ran stale code: dev-backend.ps1 PYTHONPATH bug [FIX APPLIED 2026-07-12, awaiting host confirm]
- **Was:** real UNO run showed `pcv=MISSING` even after restarting the backend.
- **ROOT CAUSE FOUND:** `dev-backend.ps1` built each service src path as
  `services/$(Name -replace '-service','')/src`, but the dirs keep the suffix
  (`services/perception-service/src`). For all 8 `*-service` services the path didn't exist → uvicorn
  imported the **stale globally-installed package** → new CV code never loaded regardless of restarts.
  (Also overwrote `$env:PYTHONPATH` each loop iteration.) Tests missed it: `run-tests.ps1` globs real
  dirs (`services/*/src`), so tests imported repo code while the live backend didn't.
- **Fix applied:** `dev-backend.ps1` uses `$svc.Name` verbatim + warns on missing src dir + logs each
  resolved `src:` path. See AGENT_LOG 2026-07-12 (b).
- **To close:** user re-pulls, runs FIXED `dev-backend.ps1`, confirms startup prints real `src:` paths
  and the operator finally shows `pcv=v3`. Only THEN is a `hand_cards=0` result a real perception
  (heuristic) failure → proceed to #10.

### B1 — Real-Windows validation host unavailable
- **What's missing:** A Windows machine with pywinauto/UIA and a real UNO target (e.g. `real-uno-desktop`
  profile or a running `UNO.exe`) to confirm the DoD "autonomous cycle on a real run".
- **Already checked:** Host is macOS (`sys.platform=darwin`); `pywinauto_available()` returns False here;
  Win32 capture paths (`runtime.py`) are Windows-only. The mock adapter works cross-platform.
- **Question for human (max 3):**
  1. Is a Windows host (or CI Windows runner / RDP box) available for the real-hardware validation run?
  2. Which target should real validation use — the bundled tkinter mock (`uno_mock_app.py`) on Windows,
     or a real external UNO client? If external, what launches it?
  3. Any constraint on driving real mouse/keyboard input on that host (e.g. it's also your daily machine)?
- **Workaround in place:** Validate the full autonomous loop + checkpoint/resume + watchdog on the
  cross-platform mock adapter now; keep the real-Windows run as a final gated step (task #7).

## Resolved

### B3 — Per-card hand segmentation [RESOLVED 2026-07-04]
- **Answer:** User provided 3 real game screenshots (`tests/fixtures/uno_desktop/`). Built
  `hand_segmentation.py` calibrated + tested against them: detects hand extent, card count (±1),
  per-slot bounds + click center + dominant colour. hand7_a matches exactly (G,G,B,B,B,B,wild).
- **Remaining accuracy caveat:** card VALUE (number/action) not yet recognised — colour + coordinate
  only. Value recognition + count-exactness need live tuning on the Windows host (#B1).

### B2 — Direction for real gameplay [RESOLVED 2026-07-04]
- **Answer:** UNO.exe is a **native Electron app** that must recognize cards + coordinates from
  screenshots. Target = **Windows adapter (CV desktop)** = Path A (Decision D5). Proceeding with #9:
  wire screenshot CV card-detection → coordinate clicks in the windows executor.
- Electron = Chromium-rendered → UIA sparse → screenshot CV is the correct approach.
- Real-hardware validation still gated by #B1 (Windows host); CV pipeline + wiring is fixture-testable on macOS.
