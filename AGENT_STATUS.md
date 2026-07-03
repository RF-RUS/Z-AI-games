# AGENT_STATUS

_Updated: 2026-07-03 · Agent: Claude (senior autonomous coding agent)_

## Goal
Screenshot-driven Windows game agent that perceives → decides → acts → recovers
**fully autonomously**, survives long runs, and **resumes after a session break** — with
minimal token spend and no lost progress between sessions.

## Current phase
Phase A — Autonomous runtime harness. **Runner + checkpoint/resume DONE & mock-validated.**
Remaining in A: process-level watchdog (#4). Then Phase C long-run validation (#5).

## Autonomous runner (built 2026-07-03)
`scripts/run-windows-agent.py` — continuous tick loop, atomic per-tick checkpoint
(`artifacts/agent-runs/<run_id>/checkpoint.json`), `--resume`, `--max-ticks`/`--max-duration`,
graceful SIGINT/SIGTERM stop, JSONL run log. In-process (mock, any OS) or `--http`.
Validated: 5 ticks ok + resume 6→8. Real pywinauto path unchanged, still needs Windows host (#B1).

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
