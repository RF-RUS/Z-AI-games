# AGENT_BLOCKERS

Real blockers only. Move to Resolved when cleared.

## Open

### B4 — Perception service running stale code on the user's Windows host (2026-07-12)
- **What's missing:** confirmation that perception (:8103) is running current code. The 2026-07-12 run
  shows `pcv=MISSING(restart-perception-8103)` while the screenshot reaches the orchestrator fine
  (1296x759, avg_brightness=101). `cv_build="v3"` is set in the perception service (`merger.py:93`), so
  MISSING = that process wasn't restarted after pull.
- **Already checked (code):** capture is fine (07-05 black-frame fix holds); the orchestrator prints
  `[CVv3]`; the marker gap is purely the perception process being stale.
- **Action for user (not a code blocker):** run `scripts/stop-backend.ps1` then `scripts/dev-backend.ps1`
  (the 07-05 fix kills stale port listeners), rerun ONE session, report the `[CVv3]` line. Expect
  `pcv=v3`. If it appears but `hand_cards=0` on the fanned hand → the heuristic can't read real UNO,
  which greenlights #10 (VLM perception, D6).

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
