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
