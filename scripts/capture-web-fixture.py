#!/usr/bin/env python3
"""Capture web adapter fixture via running adapter-web service or direct Playwright."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "adapter-web" / "src"))

from uno_adapter_web.registry import attach_adapter, get_adapter
from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterRequest


async def capture(mode: str, output_dir: Path, profile_id: str, url: str | None) -> None:
  req = AttachWebAdapterRequest(
    session_id="fixture-capture",
    profile_id=profile_id,
    url=url,
    mode=AdapterMode(mode),
    headless=True,
  )
  resp = await attach_adapter(req)
  if not resp.attached:
    print(f"Attach failed: {resp.message}")
    sys.exit(1)

  adapter = get_adapter(resp.adapter_id)
  assert adapter
  bundle = await adapter.capture_evidence(resp.adapter_id)
  await adapter.detach()

  output_dir.mkdir(parents=True, exist_ok=True)
  fixture_id = profile_id.replace("/", "_")

  (output_dir / f"{fixture_id}_dom_snapshot.json").write_text(
    bundle.dom_snapshot.model_dump_json(indent=2), encoding="utf-8"
  )
  (output_dir / f"{fixture_id}_dom_evidence.json").write_text(
    bundle.dom_evidence.model_dump_json(indent=2), encoding="utf-8"
  )
  meta = {
    "profile_id": profile_id,
    "mode": mode,
    "url": resp.url,
    "chat_messages": bundle.chat_messages,
    "extracted": bundle.dom_snapshot.extracted,
  }
  (output_dir / f"{fixture_id}_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

  if bundle.screenshot and bundle.screenshot.path:
    import shutil
    shutil.copy(bundle.screenshot.path, output_dir / f"{fixture_id}_screenshot.png")

  print(f"Fixtures written to {output_dir}")


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("--mode", choices=["mock", "playwright"], default="mock")
  parser.add_argument("--profile", default="local-mock-uno")
  parser.add_argument("--url", default=None)
  parser.add_argument("--output", default="tests/fixtures/web_adapter")
  args = parser.parse_args()
  asyncio.run(capture(args.mode, Path(args.output), args.profile, args.url))


if __name__ == "__main__":
  main()
