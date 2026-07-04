"""Hand segmentation calibrated against REAL UNO desktop screenshots.

Fixtures are actual game frames (1296x759). Assertions are lenient-but-meaningful
so the heuristic can be tuned live on the target machine without breaking CI, yet
still guards the calibrated geometry + colour signal.
"""

from pathlib import Path

import pytest

pytest.importorskip("PIL")
from uno_perception.hand_segmentation import segment_hand_cards  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "uno_desktop"

# Reference window 1296x759 → hand region (see real-uno-desktop profile ratios).
HAND_REGION = {"x": int(1296 * 0.30), "y": int(759 * 0.75),
               "width": int(1296 * 0.45), "height": int(759 * 0.22)}


def _require(name: str) -> str:
  p = FIXTURES / name
  if not p.exists():
    pytest.skip(f"fixture missing: {p}")
  return str(p)


@pytest.mark.parametrize("fixture,expected_n", [
  ("hand7_a.jpeg", 7),
  ("hand7_b.jpeg", 7),
  ("hand8.jpeg", 8),
])
def test_segments_real_hands(fixture, expected_n):
  slots = segment_hand_cards(_require(fixture), HAND_REGION)
  assert slots, "no cards segmented"
  # Count within +/-1 of truth (fan overlap makes exact count hard).
  assert abs(len(slots) - expected_n) <= 1

  # Click centers monotonic left-to-right and inside the frame.
  xs = [s.center[0] for s in slots]
  assert xs == sorted(xs)
  for s in slots:
    assert 0 < s.center[0] < 1296 and 0 < s.center[1] < 759
    bx, by, bw, bh = s.bounds
    assert bx <= s.center[0] <= bx + bw
    assert bw > 0 and bh > 0

  # Colour signal: every real hand here starts with green cards and contains
  # blue cards; the rightmost card is a (dark) wild +4.
  colors = [s.color for s in slots]
  assert "green" in colors[:3]
  assert "blue" in colors
  assert colors[-1] == "wild"
