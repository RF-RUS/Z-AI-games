#!/usr/bin/env python3
"""Start orchestrator web session (mock adapter)."""

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
  p.add_argument("--url", default=None)
  p.add_argument("--profile", default="local-mock-uno")
  p.add_argument("--tick", action="store_true")
  args = p.parse_args()
  orch = SessionOrchestrator()
  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
    web_profile_id=args.profile,
    target_url=args.url,
  )
  detail = await orch.create_session_with_game(spec)
  await orch.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=AdapterType.WEB, target_url=args.url, profile_id=args.profile))
  await orch.start(detail.session_id)
  if args.tick:
    result = await orch.run_tick(detail.session_id)
    print(json.dumps(result, indent=2))
  else:
    print(json.dumps(orch.status(detail.session_id).model_dump(mode="json"), indent=2))


if __name__ == "__main__":
  asyncio.run(main())
