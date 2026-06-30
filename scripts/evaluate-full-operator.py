#!/usr/bin/env python3
"""Run full-operator evaluation on scenario dataset."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "session-orchestrator" / "src"))

from uno_orchestrator.evaluation_runner import run_operator_evaluation
from uno_orchestrator.in_process_clients import InProcessClients
from uno_orchestrator.orchestrator import SessionOrchestrator


async def main() -> None:
  p = argparse.ArgumentParser()
  p.add_argument("--dataset", default="full_operator")
  p.add_argument("--in-process", action="store_true", default=True, help="Use ASGI in-process services (default)")
  args = p.parse_args()
  clients = InProcessClients() if args.in_process else None
  orch = SessionOrchestrator(clients=clients) if clients else SessionOrchestrator()
  result = await run_operator_evaluation(args.dataset, orchestrator=orch, clients=clients)
  print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
  asyncio.run(main())
