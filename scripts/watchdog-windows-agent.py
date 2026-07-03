#!/usr/bin/env python3
"""Process-level watchdog for the autonomous Windows agent.

Supervises ``run-windows-agent.py`` as a child process and restarts it after a
hard crash (window died, pywinauto fault, OOM kill, non-zero exit) with
exponential backoff, always resuming from the run checkpoint so no progress is
lost. In-loop recovery (retry/backoff/fallback) already lives inside the tick
loop; this closes the remaining gap — surviving a *process* death during a long
unattended run.

Exit-code contract from the child runner:
  0  clean stop (limit reached or SIGINT/SIGTERM)  -> watchdog stops too
  2  attach failed                                 -> retried (may be transient)
  other / killed by signal                         -> crash, restart with backoff

Example
  python scripts/watchdog-windows-agent.py --run-id nightly \
      --profile real-uno-desktop --pywinauto --max-duration 3600 \
      --max-restarts 20
Unknown args are passed straight through to run-windows-agent.py.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "run-windows-agent.py"


def parse_args(argv=None) -> tuple[argparse.Namespace, list[str]]:
  p = argparse.ArgumentParser(
    description="Watchdog/supervisor for run-windows-agent.py",
    epilog="Any unrecognized args are forwarded to run-windows-agent.py.",
  )
  p.add_argument("--run-id", default="default")
  p.add_argument("--max-restarts", type=int, default=10,
                 help="max crash restarts before giving up (0 = infinite)")
  p.add_argument("--backoff", type=float, default=5.0, help="base backoff seconds")
  p.add_argument("--backoff-max", type=float, default=300.0, help="max backoff seconds")
  p.add_argument("--python", default=sys.executable, help="python interpreter for the child")
  return p.parse_known_args(argv)


def main() -> None:
  args, passthrough = parse_args()
  restarts = 0
  child: subprocess.Popen | None = None
  stopping = False

  def _forward(signum, _frame):
    nonlocal stopping
    stopping = True
    if child and child.poll() is None:
      try:
        child.send_signal(signum)
      except Exception:
        pass

  signal.signal(signal.SIGINT, _forward)
  signal.signal(signal.SIGTERM, _forward)

  while True:
    # Always resume: with no prior checkpoint the runner just starts fresh.
    cmd = [args.python, str(RUNNER), "--run-id", args.run_id, "--resume", *passthrough]
    attempt_no = restarts + 1
    print(f"[watchdog] launch attempt={attempt_no} run_id={args.run_id} cmd={' '.join(cmd)}",
          flush=True)
    started = time.monotonic()
    child = subprocess.Popen(cmd)
    rc = child.wait()
    elapsed = time.monotonic() - started

    if stopping:
      print(f"[watchdog] stopped by signal; child rc={rc}", flush=True)
      raise SystemExit(0)
    if rc == 0:
      print(f"[watchdog] child exited cleanly (rc=0) after {elapsed:.1f}s — done", flush=True)
      raise SystemExit(0)

    restarts += 1
    if args.max_restarts and restarts > args.max_restarts:
      print(f"[watchdog] giving up after {restarts - 1} restarts (rc={rc})", flush=True)
      raise SystemExit(1)

    # Exponential backoff, capped. Reset-ish: long healthy runs still back off
    # the same way — simple and predictable for unattended operation.
    delay = min(args.backoff * (2 ** (restarts - 1)), args.backoff_max)
    reason = "attach_failed" if rc == 2 else f"crash rc={rc}"
    print(f"[watchdog] {reason} after {elapsed:.1f}s — restart {restarts} in {delay:.1f}s",
          flush=True)
    time.sleep(delay)


if __name__ == "__main__":
  main()
