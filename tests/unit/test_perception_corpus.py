"""Perception regression over a corpus of REAL frames captured from live play.

This is the guard rail for the multi-game goal. Perception is the part of this agent
that breaks silently: it does not raise, it returns a plausible board that is wrong,
and the agent then plays a hand that is not on screen (AGENT_LOG.md 2026-08-04 —
a mock board reached the agent at confidence 0.8). Unit tests over synthetic inputs
cannot catch that; only real pixels with a human-verified answer can.

When Svintus support lands, THIS is what tells you UNO still works.

The corpus lives in `tests/fixtures/perception/<game>/<case>/` and is grown from
cycle traces via `scripts/replay_perception.py promote`. The test SKIPS when the
corpus is empty, so a fresh checkout is never red — but note that a skip means the
regression net does not exist yet, not that perception is fine.

Only the deterministic recognizer runs here. Calling the VLM would make the suite
depend on a running Ollama, a loaded model and ~11 s per frame; that belongs in
`replay_perception.py run --recognizer vlm`, run by hand.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
  sys.path.insert(0, str(SCRIPTS))

replay = pytest.importorskip(
  "replay_perception", reason="scripts/replay_perception.py not importable"
)

CASES = replay.discover_cases()


@pytest.mark.skipif(not CASES, reason="no labelled perception fixtures yet — see scripts/replay_perception.py")
@pytest.mark.parametrize("case_dir", CASES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_perception_matches_label(case_dir: Path) -> None:
  frame = next(iter(sorted(case_dir.glob("frame.*"))))
  expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))

  # An unedited stub still carries the agent's own guess as the "expected" answer.
  # Comparing it to the agent would pass trivially and enshrine the current bug, so
  # fail loudly instead of quietly reporting green.
  assert "_TODO" not in expected, (
    f"{case_dir / 'expected.json'} was never hand-verified (still has _TODO). "
    "Check every field against the frame by eye, then delete that key."
  )

  actual = asyncio.run(replay._perceive_frame(frame, case_dir.parent.name, "heuristic"))
  ok, problems = replay._compare(expected, actual)
  assert ok, f"{case_dir.parent.name}/{case_dir.name}: " + " | ".join(problems)


def test_hand_comparison_ignores_order_but_not_duplicates() -> None:
  """Guards the comparison itself — a lenient differ makes the whole corpus lie."""
  a = [{"color": "red", "value": "6"}, {"color": "blue", "value": "9"}]
  reordered = [{"color": "blue", "value": "9"}, {"color": "red", "value": "6"}]
  duplicated = [{"color": "red", "value": "6"}, {"color": "red", "value": "6"}]

  # The hand is fanned and rotated; left-to-right order is not ground truth.
  assert replay._norm_hand(a) == replay._norm_hand(reordered)
  # Two red 6s is a different hand from one red 6 — duplicates must count.
  assert replay._norm_hand(duplicated) != replay._norm_hand([{"color": "red", "value": "6"}])
  # Case and the "number" spelling some models emit must normalize to the same card.
  assert replay._norm_hand([{"color": "RED", "number": 6}]) == replay._norm_hand(
    [{"color": "red", "value": "6"}]
  )


def test_compare_only_asserts_labelled_keys() -> None:
  """A partially-labelled case must still be usable, not silently pass everything."""
  actual = {"screen_type": "in_game", "top_card": {"color": "red", "value": "6"}, "hand_cards": []}

  ok, _ = replay._compare({"screen_type": "in_game"}, actual)
  assert ok, "an unlabelled key must not be compared"

  ok, problems = replay._compare({"top_card": {"color": "blue", "value": "9"}}, actual)
  assert not ok and "top_card" in problems[0]
