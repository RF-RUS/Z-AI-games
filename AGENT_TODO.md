# AGENT_TODO

_Updated: 2026-07-12_

## In Progress
- _(idle — awaiting user backend-restart confirmation, then #10 VLM perception)_

## Next
- [#10] **VLM perception producer (D6) — primary path to "any card game".** Feed the observation
  screenshot to a multimodal model; return structured `{screen_type, whose_turn, top_card,
  hand_cards[] with bounds+center}` into the EXISTING `vlm: VisionInference` slot (`api.py:27`, already
  consumed by `merger.py:195/239`). Demote `canvas_plugin` heuristic to a fallback (no-VLM/offline/cost).
  Breakdown:
  - [10a] VLM client in `model-runtime-service` (multimodal call; screenshot in → JSON out).
  - [10b] Producer in perception observe→perceive path that fills `req.vlm` (currently always None).
  - [10c] Map VLM `hand_cards` → same dict shape the 9c grounding path already clicks (bounds+center).
  - [10d] Fixture test on the real frames (`tests/fixtures/uno_desktop/*`, + the 2026-07-12 Ubisoft
    frame) asserting a fanned hand yields the right count + per-card coords where the heuristic fails.
- [#0] **User action:** `stop-backend.ps1` then `dev-backend.ps1`, rerun once. Confirm `pcv=v3`
  (proves perception is live) before investing in #10. If heuristic still reads 0 cards → confirms D6.

## Blocked
- [#9] **Real gameplay: CV → windows execution.** Direction decided = CV desktop (Electron). Breakdown:
  - [9a] ✅ Coordinate plumbing — detected hand_cards carry absolute bounds+center; recognition runs
    in-memory. (2026-07-04)
  - [9b] ✅ Per-card hand segmentation — `hand_segmentation.py`, calibrated + tested vs 3 real frames
    (count ±1, per-slot bounds/center/colour). Integrated into perception. (2026-07-04)
  - [9c] ✅ Execution grounding — detected card coordinate threaded flow→map_action→schema→executor
    (`_execute_grounded_click`, screenshot→screen transform). Clicks the real card. (2026-07-04)
  - [9-crit] ✅ CRITICAL: `_observe` never surfaced the screenshot → CV never ran on real Windows →
    everything was `not_in_game`. Fixed. (2026-07-04)
  - [9d] **NEXT** — Legal actions / turn derived from the DETECTED state (hand + top card via uno-core
    rules) instead of the simulated engine. Also detect whose_turn (self-avatar glow).
  - [9e] Card VALUE (number/action) recognition per card + real-hardware tuning: coordinate transform
    (DPI), exact count, real clicks (needs Windows host, #B1).
  - [9-BLOCKED 2026-07-12] Heuristic CV reads 0 cards from real Ubisoft UNO (fanned/rotated hand).
    Superseded by #10 (VLM). 9d/9e resume once perception returns a real hand. 9e VALUE recognition
    largely subsumed by the VLM producer.
- [#7] Real Windows validation — needs Windows host.

## Backlog
### Phase B — Perception/decision/execution hardening (unblocked, but touches real-Windows paths)
- [#6] Harden verification: region-aware/structural check tied to expected outcome (replace global pixel ratio).
  Note: `verify_screenshot_transition` is unit-testable; the "expected region" design needs profile
  region metadata — do as a focused follow-up, not blind edits to the perception core.
- Review confidence/uncertainty thresholds (0.7 gate) against real fragility.

## Blocked
- [#7] Real Windows validation — needs Windows host + pywinauto + real UNO target (macOS host here).

## Done
- Full audit of screenshot-driven Windows agent architecture.
- Created AGENT_STATUS / TODO / LOG / DECISIONS / BLOCKERS.
- Confirmed baseline: default orchestrator needs HTTP services; in-process path is the route for mock runs.
- [#1] In-process windows adapter registry (`setup_in_process_windows_registry`) via ASGI transport.
- [#2] `scripts/run-windows-agent.py` autonomous continuous runner (limits, logging, graceful stop).
- [#3] Atomic per-tick checkpoint + `--resume` (validated: ticks 6→8 across restart).
- [#4] `scripts/watchdog-windows-agent.py` process supervisor (auto-restart, backoff, giveup — validated).
- [#5] Long-run (100 ticks, 0 crashes) + adaptive backoff self-heal + `kill -9`→resume fault injection.
- Real-run bugfixes: Pause now holds (loop); New button wired (reset); blind fixed-point click
  suppressed for `web_only` profiles. +3 regression tests. (2026-07-04)
