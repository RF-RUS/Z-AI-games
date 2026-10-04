# AGENT_TODO

_Updated: 2026-08-24_

## In Progress
- [#16] **VERIFY the click-grounding fix — nothing below has been executed.** Written 2026-08-05 with no
  shell available: `uno_perception/hand_fusion.py`, the geometry block in `merger.py`, both
  `flow_controller.py` edits, `tests/unit/test_hand_fusion.py`. Steps:
  1. `.\.venv\Scripts\python.exe -m pytest tests\unit -q`
  2. Restart the backend, play, and confirm **the mouse actually moves**.
  3. In `artifacts/cycle_trace/<session>/NNNN/cycle.json` check `game_state.hand_geometry`:
     want `grounded == len(hand_cards)` and `method == "index"`. `grounded: 0` with a `reason` tells you
     which half failed; `method: "color_match"` means segmentation and the VLM disagreed on the hand.
  4. Grep the orchestrator log for `execute_refused_by_adapter` — if it fires, the coordinate reached the
     adapter and the adapter still refused, which is a *different* bug from having no coordinate.
- [#17] **Cycle takes 76.9 s** (session `e9f527e3`, cycle 4) with only ~11 s of it in the VLM. Suspect two
  VLM round-trips per cycle (perception + policy advice). Cycle 5 then failed in `observe` after 17.5 s and
  the operator showed "Session appears stale — no new steps arriving". Note the `merger.py` fix makes this
  *worse*: the heuristic now runs on VLM cycles too. Measure before optimizing — `timings_ms` is in every
  `cycle.json`.
- [#14] **Grow the perception corpus.** Infrastructure is landed and green (see below); it is empty.
  **Real frames now exist** at `artifacts/cycle_trace/e9f527e3-1383-4cf4-9ac9-7a023d65f235/0001..0004`, so
  `promote` is possible today. Cover different SCREEN TYPES (opponent's turn, own turn, colour picker,
  end-of-round, plus one where perception was visibly wrong — the VLM read the red *skip* as `red 0`)
  and **hand-verify each `expected.json`**. Until that happens `test_perception_corpus` skips — and a
  skip means the regression net does not exist yet, not that perception is fine.
  Runbook: `docs/runbooks/cycle-trace-and-replay.md`. Environment hygiene is part of the task: one UNO
  window, nothing overlapping the game area, or the frames are worthless as ground truth.
- [#15] **Confirm the thinking kill switch works.** Restart backend, play, and check that
  `provider_empty_content` is gone from the model-runtime log and `[CVv3]` reads `rec=vlm vlm=ok`.
  If `reasoning_chars` is still large, the build honours neither flag → **switch `model_name` to a
  non-thinking VLM** (qwen2.5vl, minicpm-v, llava). Do NOT raise `max_tokens` a third time; 1024 and 3072
  both returned `finish_reason=length` with empty content.
  _(Partly answered: session `e9f527e3` reached `vlm_status: "ok"` at confidence 0.95 with a correct
  7-card hand, so the kill switch appears to work — still wants one clean confirming log.)_
- [#19] **Bring Ollama back up** to clear `vlm_status: "mock_fallback"` (seen in session `cd83b7b0`).
  Operational issue — no code change needed. With the snapshot fix (#T8) in place, the next VLM-down cycle
  will run the heuristic cleanly. Checkpoint: cycle trace shows `crops_generated > 0` and
  `extraction_errors: []`.

## Done (2026-08-24 — drawn-card Play/Keep prompt decided by game strategy)
- [#20] **Strategy decides the Play/Keep dilemma.** After drawing, the game shows the card with a
  play-or-keep question; the old code clicked Play by static label priority (`_PROMPT_PRIORITY` ranks
  "play" first), never analysing the board. Now: VLM reports `drawn_card` (the highlighted just-drawn
  card); `perceived_actions.decide_drawn_play_or_keep(drawn, top, hand)` returns verdict + reason
  (unreadable → keep; non-matching → keep; wild hoarded unless nothing else plays; action cards and
  matching numbers → play); `choose_prompt_with_strategy` applies it only when both sides are visible,
  legacy `choose_prompt` for everything else; flow clicks it and announces "Prompt: X — why" in chat,
  `extra.prompt_strategy`, and the `prompt_click` log. +15 tests (unit strategy, VLM normalize/merger,
  full `run_cycle` flow). All green: 542 passed / 22 skipped.
- [#21] **Delivery-verification ratio was broken** (found while checking #20's unconfirmed-click path):
  `verify_screenshot_transition` counted NON-ZERO histogram bins instead of diff magnitude →
  `change_ratio` capped at ~0.0039 < default threshold 0.005 → every click read `no_visible_change`.
  Fixed to a magnitude-weighted sum over all 3 channels; `test_changed_board_confirms_delivery`
  (previously failing in the working tree from the prior session's executor changes) now passes.

## Done (2026-08-07 — transform confirmed clean; test pollution patched; opponents + draw_pile; policy parse rescue)
- [#Td] **Policy parse rescue — `decide_model` now uses `_extract_json_object`.**
  Same class of bug as #T9 (vlm_provider): `json.loads` on the bare model response fails on fenced or
  preamble-wrapped JSON and silently falls back to heuristic with `fallback_reason="parse_failed"`. The
  helper `_extract_json_object` was already present in `policy.py`; wired it into the `JSONDecodeError`
  handler so rescue is attempted before declaring failure. +8 tests in `test_decision_policy.py`
  (5 helper + 3 rescue path with httpx mocked). **NOT VERIFIED** (shell unavailable).
  Expected new baseline: 378 passed / 1 skipped.
- [#11] **Opponents + draw_pile in VLM board.** `vlm_provider._board_prompt` now requests
  `opponents:[{seat,hand_count}]` and `draw_pile:{x,y}`. `_normalize_board` extracts both (opponent
  helper coerces `hand_count` to int; `draw_pile` is `None` on absent/malformed coords). Merger copies
  `opponents` in the VLM-board key loop and injects `draw_pile` into `actionable_targets` so
  `find_draw_target` works on the VLM path even when the heuristic geometry block is skipped.
  +5 tests in `test_vlm_perception.py`. **NOT VERIFIED** (shell unavailable).
  Expected new baseline: 370 passed / 1 skipped.
- [#18] **Click transform confirmed 1:1 — not the cursor-shift bug.** Read `logs/adapter-windows.log`:
  `grounded_click` shows `frame_w=1296 frame_h=759 win_w=1296.0 win_h=759.0 scale_x=1.0 scale_y=1.0
  success=True`. Math checks out exactly (`86+649=735`, `166+652=818`). The pre-T5 "cursor above cards"
  symptom was the agent having no coordinate at all (falling to the UIA path), not a transform error.
  `grounded_by=None` is expected: the grounding provider has no named target for `play_card`, so the
  raw card-center coordinate from perception is used directly.
- [#Hk-s1] **`test_flow_cycle_failure.py` test pollution fixed.** Added `tmp_path, monkeypatch` to
  `test_observe_timeout_marks_failed_step_and_keeps_active_on_retry` and set
  `AGENT_CYCLE_TRACE_DIR` to `tmp_path / "trace"`. The pre-existing `artifacts/cycle_trace/s1/`
  directory in the repo is a leftover from before the fix; delete it manually.
- [#T9] **Rescue `parse_failed` VLM responses via `_extract_json_object`.** `cd83b7b0` cycle 1 had
  `vlm_status: "parse_failed"` — the model returned fenced or preamble-wrapped JSON that
  `json.loads(raw_text)` couldn't parse directly. Added `_extract_json_object(text)` to
  `vlm_provider.py`: tries markdown fence regex first, then a brace-counter scan to skip any
  reasoning preamble. The old `vlm_parse_failed` log now fires only for genuinely unrecoverable
  responses. +5 tests in `test_vlm_perception.py`. **NOT VERIFIED** (shell unavailable).
  Expected new baseline: 365 passed / 1 skipped.

- [#T8] **Screenshot snapshot in `perception-service/src/uno_perception/api.py`.**
  When `vlm_status: "mock_fallback"` (Ollama down, VLM timed out), the heuristic fallback ran 30+ s after
  request start and called `PIL.Image.open(screenshot.path)`. By then the adapter may have deleted or
  overwritten the `evidence-*.png` file → "unrecognized data stream". Fix: read the file into a
  `tempfile.mkstemp` snapshot **at request start**, before the VLM call. Both VLM and heuristic use the
  stable temp path. Cleaned up in `try/finally`. If the initial read fails (`OSError`), the original path
  is kept and downstream errors remain explicit. `data_base64` is NOT populated by the orchestrator (only
  `path` is set), so the fix had to work at the file level.
  New tests: `tests/unit/test_perception_snapshot.py` (4 cases: survives deletion, independent copy,
  cleanup in finally, OSError keeps original path).
  **NOT VERIFIED:** ruff and `pytest tests/unit` unrun (no shell). Baseline 356 passed / 1 skipped.

## Done (2026-08-05 — the agent had no coordinate to click)
- [#T5] `uno_perception/hand_fusion.py` — identity from the VLM, geometry from the heuristic. They were
  mutually exclusive in `merger.build_observation` (`if not vlm_has_cards`), so fixing the VLM broke every
  click. Governing rule: **never guess an alignment** — no coordinate is a stall, a wrong coordinate is a
  move the agent never chose. `game_state["hand_geometry"]` now records which path grounded the hand.
- [#T6] `flow_controller._execute` raises on a refused action. Adapters answer **HTTP 200 even when they
  refuse** (success lives in the body) and the return value was discarded → the operator said "Delivered"
  while the mouse never moved.
- [#T7] The trace was labelling every *successful* cycle `ok=false`: `failed_at` is a **progress** marker,
  not a failure marker. Now records the exception instead — and as `f"{type(exc).__name__}: {exc}"`,
  because httpx transport errors have an empty `str()`.

## Done (2026-08-04 — perception made testable offline)
- [#T1] `uno_shared.cycle_trace` — per-cycle frame + **full** perceived board (not counts) + provenance +
  decision, game-agnostic, best-effort, disk-bounded. Hooked into `run_cycle` from a `finally` so FAILED
  cycles are captured too — those are the frames worth having.
- [#T2] `scripts/replay_perception.py` — re-runs recognition over saved frames with no game, no services,
  no GPU. `promote` builds a fixture but leaves a `_TODO` key that makes the test fail until a human
  verifies the label, so the corpus cannot enshrine the current bug.
- [#T3] Fixed a bug CLASS found by the new tests: `getattr(obj, "attr", None)` does not protect against an
  attribute that RAISES (its default only covers `AttributeError`). In `recovery.format_exception_message`
  this meant the error FORMATTER raised inside `_handle_failure` — the recovery path died while reporting
  a timeout. Also fixed in `cycle_trace`. `pytest tests/unit`: 356 passed, 1 skipped.
- [#T4] VLM empty-response root cause + fix: qwen3-vl is a thinking model billing reasoning against
  `max_tokens`; server-side `metadata.extra_body` now turns thinking off. Same bug on the `policy_advice`
  path (256-token default) fixed. See `AGENT_LOG.md` 2026-08-04.

## Housekeeping
- ~~**Unit tests pollute the real artifacts dir.**~~ **Fixed 2026-08-07** — `test_flow_cycle_failure`
  now sets `AGENT_CYCLE_TRACE_DIR` via `monkeypatch`. The pre-existing `artifacts/cycle_trace/s1/`
  directory is a leftover; delete it manually.
- **ruff is declared in `[dependency-groups] dev` but is NOT installed in `.venv`** (`No module named
  ruff`), so `ruff check .` in `ai-context/RUNBOOKS.md` silently cannot run and lint has been skipped.
  Fix: `uv sync --group dev` (or `.\.venv\Scripts\python.exe -m pip install "ruff>=0.15.0"`).
- ~16 modules under `services/` still use `logging.getLogger()`, which in this repo is a **silent
  logger** (structlog owns stdout; stdlib records fall to `lastResort` → stderr, WARNING+ only).
  `perception/vlm_provider.py` and `decision/policy.py` are converted. Convert on touch, and remember
  structlog's `warning()` takes kwargs, NOT `%s`.

## Done (2026-07-14, D7 — generic action grounding)
- [#13] Grounding layer: `GroundingProvider` contract + `resolve_grounding` (cheapest-first,
  `found ⟹ conf≥min`), `VLMGroundingProvider` + `default_providers` reusing the VLM `/invoke` path.
- `POST /ground` on perception + `clients.ground()` (+ in-process); `choose_color` grounded in
  `flow_controller._execute` (cheap perceived-`prompts[]` path → VLM fallback → `target_x/target_y`);
  `choose_color` branch in `_map_action_windows`.
- Reliability: UIA-walk time budget (`extract_ui_tree`), adapter execute deadline (`api.py`),
  `choose_color` added to UIA-skip set — grounding failures degrade cleanly, no more `ReadTimeout`.
- `tests/unit/test_vlm_grounding.py` (8 tests, no live model); `.env.example` VLM/zone vars; docs
  updated (overview, plugin-interfaces, model-integration, integration/perception, vlm-ollama runbook).
- Deferred (upgrade path): Set-of-Marks+OpenCV, Template/UIA providers behind the contract.

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
- [#10-real] User: Ollama profile now ships **enabled**. Ensure `ollama serve` is running +
  `VLM_PERCEPTION=1` / `VLM_PROFILE_ID=local/ollama-vlm`, restart backend, rerun. Read `[CVv3]`: want
  `rec=vlm`. If `rec=heuristic vlm=<reason>`, the reason is the exact fix (runbook §4: 503=profile off,
  disabled=env not set, mock_fallback=Ollama down, error=model not pulled).
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
