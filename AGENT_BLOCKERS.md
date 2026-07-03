# AGENT_BLOCKERS

Real blockers only. Move to Resolved when cleared.

## Open

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
_(none yet)_
