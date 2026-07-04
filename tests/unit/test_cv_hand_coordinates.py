"""CV plumbing: detected hand cards must carry absolute bounds + click center.

Foundation for grounding a chosen action to a real card coordinate (task #9).
Previously canvas_plugin dropped the per-card hand data (kept only a count), so
detected coordinates never reached the observation and could not be clicked.
"""

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402
from uno_perception.canvas_plugin import HeuristicCanvasUNOPlugin  # noqa: E402


def _make_fixture(path: str, w: int = 400, h: int = 300) -> None:
  # Bright, non-empty frame so the hand zone (bottom 30%) is not classified empty.
  img = Image.new("RGB", (w, h), (40, 40, 40))
  # Paint a bright red "hand" strip along the bottom.
  for y in range(int(h * 0.7), h):
    for x in range(w):
      img.putpixel((x, y), (200, 30, 30))
  img.save(path)


def test_hand_cards_carry_absolute_bounds_and_center(tmp_path):
  shot = tmp_path / "frame.png"
  _make_fixture(str(shot))

  inference = HeuristicCanvasUNOPlugin().infer_from_screenshot(str(shot))
  assert inference.screen_valid

  ve = inference.raw_metadata.get("visual_extraction", {})
  hand = ve.get("hand_cards", [])
  assert hand, "hand_cards must be propagated (not just a count)"

  for card in hand:
    assert "bounds" in card and "center" in card
    b, c = card["bounds"], card["center"]
    # Absolute image coordinates, within the frame.
    assert 0 <= b["x"] <= 400 and 0 <= b["y"] <= 300
    assert b["width"] > 0 and b["height"] > 0
    assert 0 <= c["x"] <= 400 and 0 <= c["y"] <= 300
    # Center sits inside bounds.
    assert b["x"] <= c["x"] <= b["x"] + b["width"]
    assert b["y"] <= c["y"] <= b["y"] + b["height"]
