# Session Orchestrator

Coordinates adapter → perception → decision → policy → execute → replay.

## Flow states

`idle`, `attaching`, `active`, `paused`, `disabled`, `error`, `replaying`

## Invariants

- Never mutates canonical state directly (uses uno-core API)
- Never bypasses decision-service or policy-guard
- Idempotent execution via correlation_id dedup

## Reuse

Copy `flow_controller.py`, `state_machine.py`, `recovery.py`, `clients.py` — no UNO-specific imports in state machine/recovery.
