# AGENT_TODO

_Updated: 2026-07-12_

## In Progress
- _(idle — awaiting user's next Windows run + optional local-VLM enablement)_

## Done (2026-07-12, Plans A + B)
- [A] Perceived game state → operator panel: `DetectedCard` + hand/top-card fields on `StrategySnapshot`;
  orchestrator fills them from `observation.game_state`; UI `extractGameState` renders real cards.
- [#10] VLM perception (env-gated `VLM_PERCEPTION`, D6): `image_base64` through model-runtime,
  `OpenAICompatibleProvider` vision content-parts, `vlm_provider.infer_vision` normalizes to the
  canonical board shape, merger treats VLM as primary + heuristic fallback. Mock board branch makes it
  fixture-testable; local Qwen2-VL drops in via `VLM_PROFILE_ID`.
- [9d] `perceived_actions.legal_actions_from_perception` — legal moves from the detected hand+top via
  `Card.matches`; `_legal_actions` prefers them → agent plays the RIGHT card, not the leftmost. Engine
  stays fallback.
- 11 new unit tests; suite 324 passed / 7 skipped; ruff clean; VLM off by default (no regression).

## Next
- [#10-real] User: register a vision profile + `VLM_PERCEPTION=1`/`VLM_PROFILE_ID`, point at a local
  vLLM (Qwen2-VL) or **Ollama** (see `docs/runbooks/vlm-ollama-setup.md`). Verify `[CVv3] pcv=v3`, panel
  shows the hand, agent plays a matching card.
- [#11] **Perceive opponents.** Neither heuristic nor VLM emit opponent state today. Extract per-seat
  `hand_count` + last discard (VLM prompt already sees the table — add fields to the board schema +
  `_normalize_board`). ALSO have the VLM board emit a `draw_pile`/deck coordinate so the draw-grounding
  fix works on the VLM path too (heuristic already emits it; VLM board currently does not).
- [#12] **Opponent-aware strategy.** `_score_action` only scores the agent's own card. Once #11 lands,
  score with opponent context: pressure the low-card player (skip/reverse/+2 when next player is near
  UNO), hoard wilds, manage colour. This is where a real winning strategy lives.
- [9e] value-recognition quality (heuristic is colour-only → 9d defers to engine there); real-hardware
  coordinate-transform tuning (#B1).

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
