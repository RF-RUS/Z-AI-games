#!/usr/bin/env python3
"""Debug orchestrator session — run one tick and print steps."""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "session-orchestrator" / "src"))

from uno_orchestrator.orchestrator import SessionOrchestrator


async def main() -> None:
  sid = sys.argv[1]
  orch = SessionOrchestrator()
  result = await orch.run_tick(sid)
  steps = orch.get_steps(sid)
  print(json.dumps({"tick": result, "steps": [s.model_dump(mode="json") for s in steps[-10:]]}, indent=2))


if __name__ == "__main__":
  asyncio.run(main())
