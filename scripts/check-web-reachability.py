"""Check whether a target URL is reachable outside Playwright."""

from __future__ import annotations

import asyncio
import json
import sys

from uno_adapter_web.navigation_diagnostics import check_url_reachability


async def main() -> int:
  url = sys.argv[1] if len(sys.argv) > 1 else "https://scuffeduno.online/"
  result = await check_url_reachability(url)
  print(json.dumps(result.model_dump(mode="json"), indent=2))
  return 0 if result.reachable else 1


if __name__ == "__main__":
  raise SystemExit(asyncio.run(main()))
