# AGENT_TODO

_Updated: 2026-07-03_

## In Progress
- _(idle — awaiting direction on #9 / BLOCKERS #B2)_

## Blocked
- [#9] **Real gameplay: wire screenshot CV coords → windows execution.** Root cause of "agent
  doesn't play". Blocked on direction (CV desktop vs web adapter) + Windows host — see BLOCKERS #B2.
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
