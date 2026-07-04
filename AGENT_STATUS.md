# AGENT_STATUS

_Updated: 2026-07-03 · Agent: Claude (senior autonomous coding agent)_

## Goal
Screenshot-driven Windows game agent that perceives → decides → acts → recovers
**fully autonomously**, survives long runs, and **resumes after a session break** — with
minimal token spend and no lost progress between sessions.

## Current phase
Phases A + C **DONE & mock-validated**: autonomous runner, checkpoint/resume, watchdog,
adaptive backoff, long-run + fault-injection. Remaining: docs (#8), verification hardening (#6, backlog),
real-Windows run (#7, blocked on host #B1).

## Autonomous harness (built 2026-07-03)
- `scripts/run-windows-agent.py` — continuous tick loop; atomic per-tick checkpoint
  (`artifacts/agent-runs/<run_id>/checkpoint.json`); `--resume`; `--max-ticks`/`--max-duration`;
  adaptive error backoff (`--error-backoff-max`); graceful SIGINT/SIGTERM; JSONL run log.
  `--in-process` (mock, any OS) or `--http`.
- `scripts/watchdog-windows-agent.py` — supervises the runner; auto-restart on crash with
  exponential backoff + `--max-restarts`; always resumes; stops on clean exit.
- **Validated (mock, in-process):** 100-tick run 0 crashes; 40/40 ok under rate limit;
  adaptive backoff self-heals; `kill -9` mid-run → resume continued without progress loss.
- Real pywinauto path unchanged; still needs a Windows host (#B1) for the final DoD run.

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
- **No autonomous entrypoint for long runs.** `scripts/start-orchestrator-session-windows.py`
  does a single `--tick` then exits; never sets `automatic=True`, never runs `_run_loop`.
- **No cross-session resume / checkpoint.** Process crash loses all session state.
- **No process-level watchdog / auto-restart.**
- **Cannot run real pywinauto here** — host is macOS. Mock path is cross-platform and IS validatable.

## Next 3 priorities
1. [#1] In-process windows adapter registry helper (mock runs without HTTP services).
2. [#2] `scripts/run-windows-agent.py` — continuous autonomous loop with limits + logging.
3. [#3] Checkpoint persistence + `--resume`.

## Known blocker
Real-Windows/pywinauto validation (DoD "confirmed on real run") needs a Windows host — see `AGENT_BLOCKERS.md`.
Everything except the real-hardware run is unblocked via the cross-platform mock adapter.
