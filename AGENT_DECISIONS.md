# AGENT_DECISIONS

Key architectural/technical decisions. Append-only; supersede with a new dated entry.

---

### D1 (2026-07-03) — Validate autonomy on the mock adapter, cross-platform
**Decision:** Build and validate the autonomous harness using the `local-mock-uno` profile via
in-process clients on the current macOS host. Real pywinauto stays a separate, Windows-only validation step.
**Why:** Host is macOS; pywinauto/Win32 capture cannot run here. The mock adapter and the entire
orchestration/loop/recovery/checkpoint logic ARE platform-independent, so 90% of the goal is testable now.
**Consequence:** DoD "confirmed on a real run" splits into (a) mock long-run confirmed here,
(b) real-Windows run deferred to a Windows host (see AGENT_BLOCKERS #B1).

### D2 (2026-07-03) — Autonomy harness lives in a new script, not by editing the loop
**Decision:** Add `scripts/run-windows-agent.py` (+ optional watchdog) driving the existing
`orchestrator._run_loop` / `run_tick`; do NOT rewrite the in-process loop.
**Why:** `_run_loop` already handles per-cycle recovery well. The missing piece is a long-lived
entrypoint + persistence + process supervision — orthogonal concerns best kept out of core.
**Consequence:** Core services untouched → low regression risk, small atomic commits.

### D3 (2026-07-03) — Checkpoint = JSON file per run, resume = replay-safe counters
**Decision:** Persist run state (session id, tick count, metrics snapshot, last status, timestamps)
to `artifacts/agent-runs/<run_id>/checkpoint.json`, rewritten atomically each tick.
Durable game-learning already persists via the Postgres `zone_store`; the checkpoint only carries
**run/progress** state, not game rules state.
**Why:** File-based checkpoint is dependency-free, inspectable, and matches the "markdown/state files as
source of truth" mandate. Postgres already owns learned zones — no duplication.
**Consequence:** Resume restores progress + continues; learned zones reload from Postgres independently.

### D5 (2026-07-04) — Real desktop gameplay is NOT wired; two possible paths
**Finding:** For a canvas/desktop game (UNO.exe), the agent cannot play because
(a) legal actions come from a simulated engine keyed by `game_id`, decoupled from the real
screen, and (b) the windows executor clicks by `selector_key` through UIA→static layout and
ignores the screenshot-detected card coordinates that perception already produces.
**Decision (pending human input — see BLOCKERS #B2):** two mutually-exclusive directions:
  - **Path A — CV-driven desktop execution:** derive turn/legal actions from the observation and
    pass detected card coordinates into `visual_executor` so clicks hit real cards. Larger effort;
    needs a Windows host to iterate; CV reliability unproven.
  - **Path B — steer to the web adapter:** the `real-uno-desktop` profile itself says match play is
    "web_only — use scuffed-uno-web". If UNO.exe is browser-based, the intended route is the web
    adapter (Playwright canvas coords), which is the active sprint per ROADMAP.
**Interim decision (done now):** stop the harmful blind-click (suppress static layout fallback for
`web_only` profiles) and make Pause/New behave correctly — regardless of which path is chosen.
**Why:** don't build the large CV wiring blind on macOS; fix the honest-behavior + control bugs first,
then pick A/B with the user and validate on hardware.

### D4 (2026-07-03) — Recovery strategy: two tiers
**Decision:** (1) In-loop recovery = existing `recovery.decide_recovery` (retry/backoff/fallback-mock/manual).
(2) Process-level watchdog = restart the whole runner on hard crash (window died, pywinauto fault),
with exponential backoff + max-restarts, resuming from checkpoint.
**Why:** In-loop recovery cannot survive a process death; a supervisor closes that gap for long runs.

### D6 (2026-07-12) — Pivot to VLM perception; heuristic CV becomes a fallback
**Finding:** On real Ubisoft UNO.exe the heuristic pipeline (`canvas_plugin` fixed relative zones +
`hand_segmentation` `width/~60px` + HSV colour buckets) reads **0 cards** from a 3D, fanned, rotated
hand — the exact `hand3.jpeg` failure mode. It was calibrated on flat `scuffed-uno` fixtures and does
not generalize. The project goal is a **universal agent for ANY card game**, so per-game zone/colour
calibration is the wrong abstraction: every new game/skin would need new fixtures.
**Decision:** Make a **general-purpose VLM the primary perception path**. Feed the screenshot to a
vision-language model that returns structured state `{screen_type, whose_turn, top_card, hand_cards[]
with bounds+center}`. The perception contract **already supports this** — `api.py` has a
`vlm: VisionInference` field and `merger.py` already consumes `vlm.structured`; the only missing piece
is a producer. The heuristic `canvas_plugin` stays as a **cheap fallback** (offline / no-VLM / cost gate).
**Why:** One vision path works across games with no per-game calibration; it directly fixes the current
real-UNO failure; and it reuses existing contract plumbing (small, low-risk wiring, not a rewrite).
Card VALUE recognition (the open 9e gap) also comes "for free" from a VLM vs the colour-only heuristic.
**Consequence:** New task **#10** (VLM producer → `vlm` slot). Model choice via `model-runtime-service`
(a capable multimodal model — default to a current Claude vision model unless a local VLM is required by
cost/offline constraints). Grounding (click the returned coordinate) reuses the existing 9c path.
Supersedes the heuristic-first assumption in D5 Path A; Path A's coordinate-grounding wiring is kept.
**Open:** confirm on a Windows host after backend restart that `pcv=v3` (rules out the stale-service
red herring) before investing in the VLM producer.
