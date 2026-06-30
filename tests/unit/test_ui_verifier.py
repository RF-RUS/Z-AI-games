"""Unit tests for Windows RPA screenshot verification."""

from pathlib import Path

from PIL import Image
from uno_adapter_windows.rpa.verification.ui_verifier import verify_screenshot_transition


def _write_png(path: Path, color: tuple[int, int, int]) -> None:
  Image.new("RGB", (40, 40), color).save(path)


def test_verify_detects_visible_change(tmp_path: Path):
  before = tmp_path / "before.png"
  after = tmp_path / "after.png"
  _write_png(before, (0, 0, 0))
  _write_png(after, (255, 255, 255))
  result = verify_screenshot_transition(str(before), str(after), min_change_ratio=0.001)
  assert result.passed
  assert result.change_ratio > 0.001


def test_verify_rejects_identical_frames(tmp_path: Path):
  before = tmp_path / "before.png"
  after = tmp_path / "after.png"
  _write_png(before, (10, 20, 30))
  _write_png(after, (10, 20, 30))
  result = verify_screenshot_transition(str(before), str(after))
  assert not result.passed
  assert result.status == "no_visible_change"


def test_verify_missing_frame():
  result = verify_screenshot_transition(None, "/missing.png")
  assert not result.passed
  assert result.status == "missing_frame"
