"""Standalone model registry example."""

import asyncio
from pathlib import Path

from uno_model_registry.registry import ModelRegistry


async def main():
  reg = ModelRegistry(Path("./models/registry"))
  for m in reg.list_models():
    print(f"{m.model_id} [{m.runtime.value}] enabled={m.enabled}")


if __name__ == "__main__":
  asyncio.run(main())
