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

### B2 — Direction for real gameplay: CV desktop vs web adapter
- **What's missing:** A decision on HOW UNO should actually be played, before building the large
  perception→execution wiring (task #9). See Decision D5.
- **Already checked:** `real-uno-desktop.json` declares `match_automation:"web_only"` and
  "match play must use web adapter scuffed-uno-web". Perception already detects cards from
  screenshots but nothing consumes the coords for clicks; legal actions come from a simulated engine.
- **Questions for human (max 3):**
  1. Is `UNO.exe` a native desktop app, or a browser/Electron wrapper around the web UNO? (Decides
     whether we do CV-on-desktop or use the existing web adapter.)
  2. Target for real play: keep pushing the **desktop windows adapter** (CV card detection → click
     coords), or switch to the **web adapter** (`scuffed-uno-web`, the active sprint)?
  3. If desktop: can you share one screenshot of the UNO.exe game screen (hand + discard pile) so the
     CV heuristic can be calibrated to real layout?
- **Workaround in place:** blind fixed-point clicking is now suppressed for `web_only` profiles, so the
  agent reports "uncertain" instead of hammering a wrong point; Pause/New fixed.

## Resolved
_(none yet)_
