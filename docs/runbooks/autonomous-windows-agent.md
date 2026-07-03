# Runbook — Autonomous Windows Agent (long, unattended, resumable)

Drive the screenshot-driven Windows agent through an unattended
perceive → decide → guard → execute → verify → record loop with per-tick
checkpointing, crash/restart recovery, and resume-after-break.

Scripts:
- `scripts/run-windows-agent.py` — the autonomous runner (one long session).
- `scripts/watchdog-windows-agent.py` — supervisor that restarts the runner on crash.

## Modes

| Mode | Flag | Needs | Use |
|------|------|-------|-----|
| In-process (default) | `--in-process` | nothing (ASGI transport) | mock runs on any OS; local dev |
| Networked | `--http` | services on ports 8100+ | real multi-service deployment |
| Mock RPA | *(default)* | any OS | `local-mock-uno` profile, no real input |
| Real RPA | `--pywinauto` | **Windows host** + target window | drives real mouse/keyboard |

`local-mock-uno` works on macOS/Linux/Windows. `--pywinauto` requires a real Windows
desktop (pywinauto/UIA + Win32 screen capture).

## Quick start

```bash
# Cross-platform smoke — 20 autonomous mock ticks
python scripts/run-windows-agent.py --profile local-mock-uno --max-ticks 20

# Bounded unattended run (1 hour), unique run id
python scripts/run-windows-agent.py --run-id nightly --max-duration 3600

# Real Windows (on a Windows host), driving a real UNO window
python scripts/run-windows-agent.py --profile real-uno-desktop --pywinauto \
    --window-title "UNO" --max-duration 1800
```

## Resume after a break or crash

State is checkpointed atomically **every tick** to
`artifacts/agent-runs/<run_id>/checkpoint.json`. Re-run with the same `--run-id` and
`--resume` to continue counting/limits where it stopped (tick numbering, ok/failed
counts, restart count). Learned click-zones persist independently in the adapter's
`zone_store` (Postgres) and reload on their own.

```bash
python scripts/run-windows-agent.py --run-id nightly --resume --max-duration 3600
```

## Unattended with auto-restart (recommended for long runs)

The watchdog supervises the runner and restarts it on a hard crash (window died,
pywinauto fault, OOM, non-zero exit) with exponential backoff, always resuming.
Unknown args pass straight through to the runner.

```bash
python scripts/watchdog-windows-agent.py --run-id nightly \
    --profile real-uno-desktop --pywinauto --max-duration 3600 \
    --max-restarts 20 --backoff 5 --backoff-max 300
```

Watchdog stops when the runner exits cleanly (limit reached or Ctrl-C). It gives up
after `--max-restarts` crash restarts.

## Key flags (runner)

| Flag | Default | Meaning |
|------|---------|---------|
| `--profile` | `local-mock-uno` | adapter-windows profile id |
| `--window-title` | none | title hint to attach to |
| `--pywinauto` | off | real RPA (Windows only) |
| `--launch-test-target` | off | launch bundled tkinter UNO mock on attach |
| `--max-ticks` | 0 (∞) | stop after N ticks |
| `--max-duration` | 0 (∞) | stop after N seconds |
| `--tick-interval` | 1.0 | seconds between ticks |
| `--error-backoff-max` | 30 | cap (s) for adaptive backoff after consecutive errors |
| `--run-id` | `default` | names the artifacts/checkpoint dir |
| `--resume` | off | restore progress from checkpoint |
| `--http` | off | use networked services instead of in-process |

## Recovery model (two tiers)

1. **In-loop** — the orchestrator flow classifies errors (transient / low-confidence /
   policy / permanent) and retries/falls back per `recovery.py`. The runner adds
   **adaptive backoff**: after consecutive tick errors it waits
   `min(tick_interval · 2ⁿ, error_backoff_max)`; one success resets the cadence. This
   self-heals rate limits and transient blips.
2. **Process-level** — the watchdog restarts the whole runner after a crash and resumes
   from checkpoint. Survives faults the in-process loop cannot (process death).

## Artifacts

Per run under `artifacts/agent-runs/<run_id>/` (git-ignored):
- `checkpoint.json` — durable run/progress state (rewritten atomically each tick).
- `run.log.jsonl` — one JSON line per tick / lifecycle event (`started`, `tick_ok`,
  `tick_error`, `backoff`, `resume`, `limit_reached`, `run_complete`).

Inspect progress:
```bash
cat artifacts/agent-runs/<run_id>/checkpoint.json
grep -c tick_ok artifacts/agent-runs/<run_id>/run.log.jsonl
```

## Known constraints

- **Real-hardware validation requires a Windows host** — mock validates the full loop,
  checkpoint/resume, watchdog, and backoff cross-platform, but not real pywinauto input
  or Win32 screen capture. See `AGENT_BLOCKERS.md` #B1.
- The adapter rate-limits actions (10/s). Keep `--tick-interval ≥ 0.1s`; adaptive backoff
  absorbs occasional bursts.
- Screenshot verification is currently a global pixel-change check — see `AGENT_TODO.md`
  #6 for the planned region-aware hardening.
