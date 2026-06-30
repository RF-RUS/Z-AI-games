#!/usr/bin/env python3
"""Run model benchmark from CLI."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "model-runtime-service" / "src"))

from uno_model_runtime.benchmark_runner import run_benchmark
from uno_schemas.model import ModelProfile


async def main() -> None:
  p = argparse.ArgumentParser()
  p.add_argument("--dataset", default="chat_intent")
  p.add_argument("--profile", default="mock/uno-assistant")
  args = p.parse_args()
  path = ROOT / "models" / "profiles" / f"{args.profile.replace('/', '__')}.json"
  profile = ModelProfile.model_validate_json(path.read_text(encoding="utf-8"))
  result = await run_benchmark(args.dataset, profile)
  print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
  asyncio.run(main())
