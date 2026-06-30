"""Deterministic synthetic preview frame for mock Windows attended mode."""

from __future__ import annotations

from pathlib import Path

from uno_adapter_windows.rpa.session_state import screen_frame_from_path
from uno_schemas.adapter_windows import ScreenFrame


def build_mock_synthetic_frame(
  artifacts_dir: Path,
  window_title: str,
  labels: list[str],
  session_id: str,
) -> ScreenFrame:
  from PIL import Image, ImageDraw

  width, height = 640, 360
  img = Image.new("RGB", (width, height), (15, 20, 25))
  draw = ImageDraw.Draw(img)
  draw.rectangle([0, 0, width - 1, 44], fill=(37, 99, 235))
  draw.text((14, 14), window_title[:72], fill=(255, 255, 255))
  draw.text((14, 56), "SYNTHETIC MOCK PREVIEW — no desktop capture", fill=(148, 163, 184))
  y = 88
  for label in labels[:8]:
    draw.text((24, y), label[:76], fill=(231, 236, 243))
    y += 28
  artifacts_dir.mkdir(parents=True, exist_ok=True)
  path = artifacts_dir / "synthetic_preview.png"
  img.save(path)
  return screen_frame_from_path(str(path), session_id, width=width, height=height)
