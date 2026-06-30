#!/usr/bin/env python3
"""Start orchestrator windows session (mock adapter)."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "session-orchestrator" / "src"))

from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.orchestrator import AttachAdapterBody, SessionSpec
from uno_schemas.session import AdapterType, SessionConfig


async def main() -> None:
  p = argparse.ArgumentParser()
  p.add_argument("--window-title", default=None)
  p.add_argument("--profile", default="local-mock-uno")
  p.add_argument("--tick", action="store_true")
  p.add_argument("--pywinauto", action="store_true", help="Use real pywinauto attended RPA (default: mock)")
  p.add_argument("--launch-test-target", action="store_true", help="Launch tkinter UNO mock app on attach")
  args = p.parse_args()
  orch = SessionOrchestrator()
  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WINDOWS, adapter_id="pending"),
    windows_profile_id=args.profile,
    window_title=args.window_title,
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
  if args.tick:
    print(json.dumps(await orch.run_tick(detail.session_id), indent=2))
  else:
    print(json.dumps(orch.status(detail.session_id).model_dump(mode="json"), indent=2))


if __name__ == "__main__":
  asyncio.run(main())
