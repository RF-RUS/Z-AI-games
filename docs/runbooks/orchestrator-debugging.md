# Orchestrator Debugging

```powershell
python scripts/orchestrator-status.py
python scripts/orchestrator-status.py <session_id>
python scripts/orchestrator-debug.py <session_id>
```

Full session notes (web attach + post-attach fixes): **[operator-debug-checkpoint.md](operator-debug-checkpoint.md)**

## Flow states

```
idle → attaching → active → (paused | error)
         ↑
         └── web start(): warmup observe here before active
```

| State | Meaning |
|-------|---------|
| `attaching` | Adapter attach **or** web observe warmup (post-start) |
| `active` | Ready for manual/automatic ticks |
| `error` | Unrecoverable failure; see `error` + `last_recovery` |

Tick is **skipped** while `attaching` and warmup not complete.

## Step history

`GET /sessions/{id}/steps` — observe, perceive, legal_actions, decide, guard, execute, record

On failure, last matching step has `result.success=false`, `result.error`, `result.error_class`.

**Note:** step marker for `observe` is appended before `web_evidence()` completes — check `success=false` on the same step, not only later steps.

## Post-attach cycle failures

Typical web failure after successful attach:

1. Failing step: **`observe`** (`web_evidence` → adapter-web `capture_evidence`)
2. Empty error text was caused by `httpx.ReadTimeout` — now formatted via `format_exception_message()`
3. Logs: `flow_cycle_failed` with `failed_step`, `error`, `error_type`, `recovery_reason`

Direct probe:

```powershell
curl "http://127.0.0.1:8104/adapters/{adapter_id}/evidence?correlation_id=probe"
```

## Attach diagnostics propagation

Search orchestrator logs:

```
web_attach_diagnostics_checkpoint_1
web_attach_diagnostics_checkpoint_2
web_attach_diagnostics_checkpoint_3
web_attach_diagnostics_checkpoint_4
```

Failed attach API may return **502** with `{ message, session }` including `attach_startup_diagnostics`.

## Warmup

Web `POST /sessions/{id}/start` triggers background warmup observe. Session stays `attaching` until success:

```
web_observe_warmup_ok
web_observe_warmup_failed
```

## Logs

Search for `flow_cycle_failed`, `replay_record_failed`, `web_observe_warmup_failed`.

## Recovery behavior

- `RETRY` (transient / low confidence): keeps `flow_state=active`, increments retry by `error_class`
- Web exhausted retries: `STOP` with reason including exception text
- UI: cycle failure panel (distinct from attach failure panel)

## Visual trace

Screenshot trace captures frame.png + meta.json at each pipeline step. See **[screenshot-trace.md](screenshot-trace.md)** for enable, verification, and troubleshooting.
