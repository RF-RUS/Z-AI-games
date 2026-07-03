# AGENT_TODO

_Updated: 2026-07-03_

## In Progress
- [#4] Process-level watchdog: auto-restart on crash, exponential backoff, `--max-restarts`, resume from checkpoint.

## Backlog
### Phase A — Autonomous runtime harness (unblocked, mock-validated)
- _(next: #4 watchdog — see In Progress)_

### Phase B — Perception/decision/execution hardening
- [#6] Harden verification: region-aware/structural check tied to expected outcome (replace global pixel ratio).
- Review confidence/uncertainty thresholds (0.7 gate) against real fragility.

### Phase C — Validation
- [#5] Long-run mock validation (100+ ticks, zero manual intervention) + fault injection (detach → recover → resume).

### Phase E — Docs
- [#8] Update README + runbook: launch autonomous agent, resume, watchdog, limits, constraints.

## Blocked
- [#7] Real Windows validation — needs Windows host + pywinauto + real UNO target (macOS host here).

## Done
- Full audit of screenshot-driven Windows agent architecture.
- Created AGENT_STATUS / TODO / LOG / DECISIONS / BLOCKERS.
- Confirmed baseline: default orchestrator needs HTTP services; in-process path is the route for mock runs.
- [#1] In-process windows adapter registry (`setup_in_process_windows_registry`) via ASGI transport.
- [#2] `scripts/run-windows-agent.py` autonomous continuous runner (limits, logging, graceful stop).
- [#3] Atomic per-tick checkpoint + `--resume` (validated: ticks 6→8 across restart).
