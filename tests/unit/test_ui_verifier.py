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


def test_verify_default_threshold_detects_partial_board_redraw(tmp_path: Path):
    """A real card play changes only PART of the frame. At the DEFAULT threshold
    (0.005) such a change must still be detected — the old count-based formula
    capped the ratio at ~0.0039 and reported 'no_visible_change' even when a
    quarter of the board was fully redrawn."""
    from PIL import ImageDraw

    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (40, 40), (180, 160, 40)).save(before)
    img = Image.open(before).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 19, 19], fill=(20, 200, 20))  # 25% of the board redrawn
    img.save(after)
    result = verify_screenshot_transition(str(before), str(after))
    assert result.passed
    assert result.status == "passed"
    assert result.change_ratio > 0.005


def test_verify_default_threshold_ignores_noise(tmp_path: Path):
    """A single-pixel flicker (video noise / cursor shimmer) is NOT a played card."""
    after_src = (10, 20, 30)
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _write_png(before, after_src)
    img = Image.open(before).convert("RGB")
    img.putpixel((5, 5), (13, 22, 31))  # tiny local fluctuation
    img.save(after)
    result = verify_screenshot_transition(str(before), str(after))
    assert not result.passed
    assert result.status == "no_visible_change"


def test_verify_missing_frame():
  result = verify_screenshot_transition(None, "/missing.png")
  assert not result.passed
  assert result.status == "missing_frame"
