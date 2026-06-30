#!/usr/bin/env python3
"""Check model provider health for a profile."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "model-runtime-service" / "src"))

from uno_model_runtime.providers import get_provider
from uno_schemas.model import ModelProfile


async def main() -> None:
  p = argparse.ArgumentParser()
  p.add_argument("--profile", default="mock/uno-assistant")
  args = p.parse_args()
  path = ROOT / "models" / "profiles" / f"{args.profile.replace('/', '__')}.json"
  profile = ModelProfile.model_validate_json(path.read_text(encoding="utf-8"))
  health = await get_provider(profile.provider).health(profile)
  print(json.dumps(health.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
  asyncio.run(main())
