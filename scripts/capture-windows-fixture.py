#!/usr/bin/env python3
"""Capture windows adapter fixtures."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "adapter-windows" / "src"))

from uno_adapter_windows.registry import attach_adapter, get_adapter
from uno_schemas.adapter_windows import AttachWindowsAdapterRequest, WindowsAdapterMode


async def capture(mode: str, output: Path, profile: str, launch: bool) -> None:
  req = AttachWindowsAdapterRequest(
    session_id="fixture-capture",
    profile_id=profile,
    mode=WindowsAdapterMode(mode),
    launch_test_target=launch,
  )
  resp = await attach_adapter(req)
  if not resp.attached:
    print(f"Attach failed: {resp.message}")
    sys.exit(1)
  adapter = get_adapter(resp.adapter_id)
  assert adapter
  bundle = await adapter.capture_evidence(resp.adapter_id)
  await adapter.detach()

  output.mkdir(parents=True, exist_ok=True)
  fid = profile.replace("/", "_")
  (output / f"{fid}_window_snapshot.json").write_text(bundle.window_snapshot.model_dump_json(indent=2), encoding="utf-8")
  (output / f"{fid}_ui_evidence.json").write_text(bundle.ui_evidence.model_dump_json(indent=2), encoding="utf-8")
  meta = {"profile_id": profile, "mode": mode, "chat_messages": bundle.chat_messages, "extracted": bundle.window_snapshot.extracted}
  (output / f"{fid}_meta.json").write_text(__import__("json").dumps(meta, indent=2), encoding="utf-8")
  print(f"Fixtures written to {output}")


def main() -> None:
  p = argparse.ArgumentParser()
  p.add_argument("--mode", choices=["mock", "pywinauto"], default="mock")
  p.add_argument("--profile", default="local-mock-uno")
  p.add_argument("--output", default="tests/fixtures/windows_adapter")
  p.add_argument("--launch-test-target", action="store_true")
  args = p.parse_args()
  asyncio.run(capture(args.mode, Path(args.output), args.profile, args.launch_test_target))


if __name__ == "__main__":
  main()
