#!/usr/bin/env python3
"""Autonomous long-running driver for the screenshot-driven Windows agent.

Drives the orchestrator tick loop continuously — perceive → decide → guard →
execute → verify → record — with per-tick checkpointing, resume-after-break,
run limits, structured logging, and graceful shutdown. Designed for unattended
long runs.

Modes
  --in-process (default)  Route adapter + service calls through ASGI transport,
                          no microservices required. `local-mock-uno` works on
                          any OS; `--pywinauto` still needs a real Windows host.
  --http                  Use networked services (ports 8100+ must be running).

Examples
  # Cross-platform smoke: 20 mock ticks
  python scripts/run-windows-agent.py --profile local-mock-uno --max-ticks 20

  # Resume a run after a crash / session break
  python scripts/run-windows-agent.py --run-id nightly --resume --max-duration 3600

  # Real Windows (on a Windows host)
  python scripts/run-windows-agent.py --profile real-uno-desktop --pywinauto \
      --window-title "UNO" --max-duration 1800
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import signal
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("packages/schemas/src", "services/session-orchestrator/src"):
  sys.path.insert(0, str(ROOT / sub))

DEFAULT_ARTIFACTS = ROOT / "artifacts" / "agent-runs"


@dataclass
class RunCheckpoint:
  """Durable run/progress state. Rewritten atomically after every tick.

  Game-learning (learned click zones) persists separately in the adapter's
  zone_store (Postgres); this checkpoint only carries run progress so a fresh
  process can pick up counting/limits where a crashed one left off.
  """

  run_id: str
  profile: str
  pywinauto: bool = False
  started_at_ms: int = 0
  updated_at_ms: int = 0
  session_id: str = ""
  tick_count: int = 0
  ticks_ok: int = 0
  ticks_failed: int = 0
  ticks_skipped: int = 0
  last_status: str = "init"
  last_error: str | None = None
  restarts: int = 0
  metrics: dict = field(default_factory=dict)

  @classmethod
  def load(cls, path: Path) -> RunCheckpoint | None:
    if not path.exists():
      return None
    try:
      data = json.loads(path.read_text(encoding="utf-8"))
      return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    except Exception:
      return None

  def save(self, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic on POSIX + Windows


class RunLogger:
  """Append-only JSONL run log (one line per tick / lifecycle event)."""

  def __init__(self, path: Path) -> None:
    self.path = path
    path.parent.mkdir(parents=True, exist_ok=True)
    self._fh = path.open("a", encoding="utf-8")

  def emit(self, event: str, **fields) -> None:
    rec = {"ts_ms": int(time.time() * 1000), "event": event, **fields}
    self._fh.write(json.dumps(rec, default=str) + "\n")
    self._fh.flush()
    # human-friendly console line
    extra = " ".join(f"{k}={v}" for k, v in fields.items() if k != "result")
    print(f"[{event}] {extra}".rstrip(), flush=True)

  def close(self) -> None:
    with contextlib.suppress(Exception):
      self._fh.close()


def _now_ms() -> int:
  return int(time.time() * 1000)


async def _build_orchestrator(in_process: bool):
  """Construct an orchestrator wired for in-process or networked adapters."""
  from uno_orchestrator.orchestrator import SessionOrchestrator

  if in_process:
    from uno_orchestrator.in_process_clients import (
      InProcessClients,
      setup_in_process_windows_registry,
    )
    setup_in_process_windows_registry()
    return SessionOrchestrator(clients=InProcessClients())
  return SessionOrchestrator()


async def _attach_and_start(orch, args) -> str:
  from uno_schemas.orchestrator import AttachAdapterBody, SessionSpec
  from uno_schemas.session import AdapterType, SessionConfig

  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WINDOWS, adapter_id="pending"),
    windows_profile_id=args.profile,
    window_title=args.window_title,
    automatic=False,  # runner drives ticks explicitly for checkpoint/limit control
  )
  detail = await orch.create_session_with_game(spec)
  await orch.attach_adapter(detail.session_id, AttachAdapterBody(
    adapter_type=AdapterType.WINDOWS,
    window_title=args.window_title,
    profile_id=args.profile,
    windows_use_pywinauto=args.pywinauto,
    launch_test_target=args.launch_test_target,
  ))
  await orch.start(detail.session_id)
  return detail.session_id


def _metrics_snapshot(orch, session_id: str) -> dict:
  try:
    status = orch.status(session_id)
    m = getattr(status, "metrics", None)
    if m is not None:
      return m.model_dump(mode="json") if hasattr(m, "model_dump") else dict(m)
  except Exception:
    pass
  return {}


async def run(args) -> int:
  run_dir = Path(args.artifacts_dir) / args.run_id
  ckpt_path = run_dir / "checkpoint.json"
  log = RunLogger(run_dir / "run.log.jsonl")

  ckpt = RunCheckpoint.load(ckpt_path) if args.resume else None
  if ckpt and args.resume:
    ckpt.restarts += 1
    log.emit("resume", run_id=args.run_id, prior_ticks=ckpt.tick_count, restarts=ckpt.restarts)
  else:
    ckpt = RunCheckpoint(run_id=args.run_id, profile=args.profile,
                         pywinauto=args.pywinauto, started_at_ms=_now_ms())

  stop = asyncio.Event()

  def _request_stop(*_):
    stop.set()

  loop = asyncio.get_running_loop()
  for sig in (signal.SIGINT, signal.SIGTERM):
    with contextlib.suppress(NotImplementedError):
      loop.add_signal_handler(sig, _request_stop)

  orch = await _build_orchestrator(args.in_process)
  try:
    session_id = await _attach_and_start(orch, args)
  except Exception as exc:  # attach is the one place we cannot recover in-loop
    ckpt.last_status = "attach_failed"
    ckpt.last_error = f"{type(exc).__name__}: {exc}"
    ckpt.updated_at_ms = _now_ms()
    ckpt.save(ckpt_path)
    log.emit("attach_failed", error=ckpt.last_error)
    log.close()
    return 2

  ckpt.session_id = session_id
  log.emit("started", session_id=session_id, profile=args.profile,
           pywinauto=args.pywinauto, in_process=args.in_process,
           max_ticks=args.max_ticks, max_duration=args.max_duration)

  deadline = time.monotonic() + args.max_duration if args.max_duration else None
  session_ticks = 0
  consecutive_errors = 0

  while not stop.is_set():
    if args.max_ticks and session_ticks >= args.max_ticks:
      log.emit("limit_reached", reason="max_ticks", ticks=session_ticks)
      break
    if deadline and time.monotonic() >= deadline:
      log.emit("limit_reached", reason="max_duration")
      break

    ckpt.tick_count += 1
    session_ticks += 1
    tick_started = time.monotonic()
    try:
      result = await orch.run_tick(session_id)
      if isinstance(result, dict) and result.get("skipped"):
        ckpt.ticks_skipped += 1
        ckpt.last_status = "skipped"
        ckpt.last_error = None
        consecutive_errors = 0
        log.emit("tick_skipped", tick=ckpt.tick_count, reason=result.get("reason"))
      elif isinstance(result, dict) and result.get("error"):
        ckpt.ticks_failed += 1
        ckpt.last_status = "error"
        ckpt.last_error = str(result.get("error"))
        consecutive_errors += 1
        log.emit("tick_error", tick=ckpt.tick_count, error=ckpt.last_error,
                 latency_ms=int((time.monotonic() - tick_started) * 1000))
      else:
        ckpt.ticks_ok += 1
        ckpt.last_status = "ok"
        ckpt.last_error = None
        consecutive_errors = 0
        action = result.get("action") if isinstance(result, dict) else None
        log.emit("tick_ok", tick=ckpt.tick_count, action=action,
                 latency_ms=int((time.monotonic() - tick_started) * 1000))
    except asyncio.CancelledError:
      raise
    except Exception as exc:
      # In-loop recovery lives inside the flow; this catches anything that
      # escapes so the long run survives a single bad tick.
      ckpt.ticks_failed += 1
      ckpt.last_status = "exception"
      ckpt.last_error = f"{type(exc).__name__}: {exc}"
      consecutive_errors += 1
      log.emit("tick_exception", tick=ckpt.tick_count, error=ckpt.last_error)

    ckpt.metrics = _metrics_snapshot(orch, session_id)
    ckpt.updated_at_ms = _now_ms()
    ckpt.save(ckpt_path)

    # Adaptive backoff: after consecutive errors (rate limit, transient blip,
    # temporary window loss) wait longer before the next tick so the run
    # self-heals instead of hammering. A single success resets the cadence.
    sleep_for = args.tick_interval
    if consecutive_errors:
      sleep_for = min(args.tick_interval * (2 ** consecutive_errors), args.error_backoff_max)
      log.emit("backoff", tick=ckpt.tick_count, consecutive_errors=consecutive_errors,
               sleep_s=round(sleep_for, 2))
    # interruptible sleep between ticks
    with contextlib.suppress(asyncio.TimeoutError):
      await asyncio.wait_for(stop.wait(), timeout=sleep_for)

  ckpt.last_status = "stopped" if stop.is_set() else ckpt.last_status
  ckpt.updated_at_ms = _now_ms()
  ckpt.save(ckpt_path)
  log.emit("run_complete", ticks=ckpt.tick_count, ok=ckpt.ticks_ok,
           failed=ckpt.ticks_failed, skipped=ckpt.ticks_skipped,
           stopped_by_signal=stop.is_set())
  log.close()

  with contextlib.suppress(Exception):
    await orch.stop(session_id)
  return 0


def parse_args(argv=None) -> argparse.Namespace:
  p = argparse.ArgumentParser(description="Autonomous Windows agent runner")
  p.add_argument("--profile", default="local-mock-uno")
  p.add_argument("--window-title", default=None)
  p.add_argument("--pywinauto", action="store_true",
                 help="Use real pywinauto RPA (requires Windows host)")
  p.add_argument("--launch-test-target", action="store_true",
                 help="Launch bundled tkinter UNO mock app on attach")
  p.add_argument("--max-ticks", type=int, default=0, help="0 = unlimited")
  p.add_argument("--max-duration", type=float, default=0.0,
                 help="seconds; 0 = unlimited")
  p.add_argument("--tick-interval", type=float, default=1.0,
                 help="seconds between ticks")
  p.add_argument("--error-backoff-max", type=float, default=30.0,
                 help="cap (s) for adaptive backoff after consecutive tick errors")
  p.add_argument("--run-id", default="default")
  p.add_argument("--resume", action="store_true",
                 help="restore progress from an existing checkpoint")
  p.add_argument("--artifacts-dir", default=str(DEFAULT_ARTIFACTS))
  mode = p.add_mutually_exclusive_group()
  mode.add_argument("--in-process", dest="in_process", action="store_true", default=True)
  mode.add_argument("--http", dest="in_process", action="store_false")
  return p.parse_args(argv)


def main() -> None:
  args = parse_args()
  raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
  main()
