# AGENT_STATUS

_Updated: 2026-07-12 · Agent: Claude (senior autonomous coding agent)_

## Goal
A **universal card-game agent**: perceive → decide → act → recover **fully autonomously** on ANY
card game (starting with real UNO.exe), surviving long runs and resuming after a session break, with
minimal token spend. "Universal" is the load-bearing word — perception must NOT be hardcoded per game.

## Current phase
**Blocked on real-game perception.** Autonomy harness (runner/checkpoint/resume/watchdog) is done and
mock-validated. The CV→click pipeline is wired and fixture-tested. But on the real Ubisoft UNO.exe the
agent still does not play: the heuristic CV can't read the real (3D, fanned, rotated) layout, and the
perception service is running stale code (`pcv=MISSING`). Next real move = **VLM perception (D6)**,
which is also the correct architecture for the "any game" goal.

## Latest real run (2026-07-12) — why it still doesn't play
- Error: `Screenshot received but no cards recognized. [CVv3] pcv=MISSING(restart-perception-8103)
  screenshot=1296x759 … hand_cards=0 avg_brightness=101`.
- **Capture is fine** (brightness 101 = real content) — the 07-05 black-frame fix holds.
- **Two blockers:** (1) perception :8103 stale → restart backend (`stop-backend.ps1` + `dev-backend.ps1`);
  (2) even fresh, the UNO-specific heuristic (`canvas_plugin` fixed zones + `hand_segmentation` width/60
  + HSV) is calibrated on flat fixtures and can't read the real fanned/rotated hand. → pivot to VLM.
- **Unlock:** the perception contract ALREADY has a `vlm: VisionInference` slot (`api.py:27`) that the
  merger already consumes (`merger.py:195/239`) — it's just never produced. Wiring a VLM producer fixes
  this game AND generalizes to any game. See AGENT_DECISIONS **D6**.

## Autonomous harness (built 2026-07-03) — DONE, mock-validated
- `scripts/run-windows-agent.py` — continuous tick loop; atomic per-tick checkpoint
  (`artifacts/agent-runs/<run_id>/checkpoint.json`); `--resume`; `--max-ticks`/`--max-duration`;
  adaptive error backoff (`--error-backoff-max`); graceful SIGINT/SIGTERM; JSONL run log.
  `--in-process` (mock, any OS) or `--http`.
- `scripts/watchdog-windows-agent.py` — supervises the runner; auto-restart on crash with
  exponential backoff + `--max-restarts`; always resumes; stops on clean exit.
- **Validated (mock, in-process):** 100-tick run 0 crashes; 40/40 ok under rate limit;
  adaptive backoff self-heals; `kill -9` mid-run → resume continued without progress loss.
- Real pywinauto path unchanged; still needs a Windows host (#B1) for the final DoD run.

## Real gameplay (task #9) — direction: CV desktop (Electron), Windows adapter
- **9a done:** CV recognition runs in production (was silently skipped) + detected cards carry bounds+center.
- **9b done:** per-card hand segmentation (`hand_segmentation.py`) calibrated & tested on 3 REAL frames
  → each hand card now has color + absolute click center. hand7_a exact (G,G,B,B,B,B,wild).
- **9-CRITICAL done:** `_observe` never surfaced the adapter screenshot (read a non-existent field) →
  CV never ran on real Windows → everything was `not_in_game`. **This was the reason nothing happened.**
  Fixed + verified end-to-end (real frame → in_game + 7 cards w/ coords).
- **9c done:** execution grounding — the chosen card's CV coordinate is clicked (flow→map_action→
  schema→`visual_executor._execute_grounded_click`), not a static point.
- **9d NEXT:** legal actions + whose-turn from the DETECTED state (not the simulated engine).
- **9e pending:** card VALUE recognition; real-hardware tuning of the coord transform / clicks (#B1).
- **9-BLOCKED (2026-07-12):** on real UNO.exe the heuristic reads 0 cards from the fanned/rotated hand.
  Zone+HSV heuristic doesn't generalize → superseded by **#10 VLM perception (D6)** as the primary path;
  heuristic demoted to fallback. 9d/9e resume once perception returns a real hand.

## Next 3 priorities (revised 2026-07-12)
1. **User:** restart backend (`stop-backend.ps1` → `dev-backend.ps1`), rerun once, confirm `pcv=v3`.
   Expected: heuristic still fails the fanned hand → confirms the pivot.
2. **[#10] VLM perception producer** feeding the existing `vlm: VisionInference` slot: screenshot →
   structured `{screen_type, whose_turn, top_card, hand_cards[]}`. Game-agnostic; heuristic = fallback.
3. **[9d]** legal actions / whose-turn from the detected state (uno-core rules on the VLM hand).

## Real-run findings (2026-07-04)
User ran real UNO.exe → agent captured screen but only looped clicking one fixed point, no play.
- **Why no play:** perception→execution are decoupled — legal actions come from a simulated engine
  (not the screen); executor clicks by `selector_key` (UIA→static layout), ignoring screenshot-detected
  card coords. Real desktop gameplay is **not wired** (task #9, BLOCKERS #B2). `real-uno-desktop`
  profile is preview-only (`web_only`).
- **Fixed now (cross-platform, tested):** Pause holds; New button resets; blind fixed-point click
  suppressed for `web_only` profiles (agent now reports uncertain instead of hammering a wrong spot).
- **Needs human:** pick real-play direction (CV desktop vs web adapter) — BLOCKERS #B2.

## DoD status
Met on the cross-platform mock path: autonomous perceive→decide→act→verify→record, recovers from
typical faults, survives long runs, resumes after break/crash. **Open:** real-hardware confirmation (#7/#B1).

## Source of truth
- **Code** = ground truth. These `AGENT_*.md` files = updatable state layer.
- Platform state: `.mimocode/STATE.md`, `docs/ROADMAP.md`, `ai-context/PROJECT_MEMORY.md`.
- Windows agent core: `services/adapter-windows/src/uno_adapter_windows/` (esp. `rpa/`, `runtime.py`).
- Orchestration/autonomy: `services/session-orchestrator/src/uno_orchestrator/`
  (`orchestrator.py` `_run_loop`, `flow_controller.py`, `recovery.py`).

## Done (already existed in repo — audited, not built by me)
- Mature RPA pipeline: locate→act→verify (`rpa/executor/visual_executor.py`).
- Target cascade: UIA → learned zones (Postgres) → static layout_targets
  (`rpa/perception/target_locator.py`) — no single hardcoded coord path.
- Humanized input, focus handling, multi-method screenshot capture (pywinauto/PIL/PrintWindow/BitBlt).
- In-process autonomous loop (`orchestrator._run_loop`) + error classification/recovery (`recovery.py`).
- CI green since fix_0.1.2; 292 unit tests pass.

## Partially done / weak
- **Verification** is a global pixel-diff ratio (≥0.5%) — proves "something changed", not the right thing.
- **Learned zones** are the only durable state; **session/run progress is in-memory only**.

## Broken / not confirmed
- **Real-game perception (2026-07-12):** heuristic CV reads 0 cards from real UNO.exe (fanned/rotated
  hand). Blocks actual play. → #10 VLM perception.
- **Cannot run real pywinauto here** — host is macOS. Mock path is cross-platform and IS validatable.
- _(Resolved 07-03: autonomous entrypoint, cross-session resume/checkpoint, and process watchdog were
  the original "broken" items — all built & mock-validated. See harness section above.)_

## Known blocker
Real-Windows/pywinauto validation (DoD "confirmed on real run") needs a Windows host — see `AGENT_BLOCKERS.md`.
Everything except the real-hardware run is unblocked via the cross-platform mock adapter.
