"""Fusing VLM card identity with heuristic card geometry.

This is the seam where "the agent knows what it holds" meets "the agent knows where
to click". It earns its own test file because a mistake here is the WORST failure
mode this project has: not a stall, but a confident click on the wrong card — the
agent playing something it never decided to play, with every log line green.

Context (AGENT_LOG.md 2026-08-05): perception read the hand perfectly, the decision
was correct, and the mouse never moved, because the VLM path had suppressed the only
component that produces coordinates.
"""

from __future__ import annotations

from types import SimpleNamespace

from uno_perception.hand_fusion import attach_hand_geometry


def _slot(index: int, color: str, x: int, conf: float = 0.9) -> SimpleNamespace:
  """A `HandCardSlot`-shaped object (tuples, as the real dataclass emits)."""
  return SimpleNamespace(
    slot_index=index, color=color, bounds=(x, 700, 80, 120),
    center=(x + 40, 760), color_confidence=conf,
  )


def test_index_alignment_grounds_every_card() -> None:
  cards = [
    {"color": "red", "value": "1"},
    {"color": "red", "value": "4"},
    {"color": "green", "value": "8"},
  ]
  slots = [_slot(0, "red", 600), _slot(1, "red", 700), _slot(2, "green", 800)]

  fused, diag = attach_hand_geometry(cards, slots)

  assert diag["method"] == "index" and diag["grounded"] == 3
  # Identity comes from the VLM and must survive untouched — the heuristic cannot
  # read values at all, so letting it near them would be a downgrade.
  assert [c["value"] for c in fused] == ["1", "4", "8"]
  assert fused[1]["center"] == {"x": 740, "y": 760}
  assert fused[1]["bounds"] == {"x": 700, "y": 700, "width": 80, "height": 120}
  assert fused[0]["geometry_source"] == "hand_segmentation"


def test_does_not_mutate_input() -> None:
  cards = [{"color": "red", "value": "1"}]
  attach_hand_geometry(cards, [_slot(0, "red", 600)])
  assert cards == [{"color": "red", "value": "1"}], "caller's board must not be edited in place"


def test_wild_card_is_grounded_by_position() -> None:
  """A wild has no colour, so only index alignment can ever place it."""
  cards = [{"color": "red", "value": "4"}, {"color": "wild", "value": "wild_draw_four"}]
  slots = [_slot(0, "red", 600), _slot(1, "blue", 700)]  # heuristic misreads the wild

  fused, diag = attach_hand_geometry(cards, slots)

  # The wild's colour is not comparable, so it cannot count as a contradiction.
  assert diag["method"] == "index"
  assert fused[1]["center"] == {"x": 740, "y": 760}


def test_count_mismatch_falls_back_to_colour_matching() -> None:
  """Segmentation guesses the card count from strip width; it is often off by one."""
  cards = [{"color": "red", "value": "1"}, {"color": "green", "value": "8"}]
  slots = [_slot(0, "red", 600), _slot(1, "green", 700), _slot(2, "green", 800)]

  fused, diag = attach_hand_geometry(cards, slots)

  assert diag["method"] == "color_match" and "mismatch" in diag["reason"]
  assert fused[0]["center"]["x"] == 640
  # Leftmost unused slot of that colour, not an arbitrary one.
  assert fused[1]["center"]["x"] == 740
  assert fused[1]["geometry_source"] == "hand_segmentation_color_match"


def test_contradicting_colour_order_refuses_index_alignment() -> None:
  """The hand is shifted by one — indices must NOT be trusted.

  This is the case that would click the wrong card, so it must degrade to colour
  matching rather than quietly pairing index to index.
  """
  cards = [{"color": "red", "value": "1"}, {"color": "green", "value": "8"}]
  slots = [_slot(0, "green", 600), _slot(1, "red", 700)]

  fused, diag = attach_hand_geometry(cards, slots)

  assert diag["method"] == "color_match"
  # Each card gets the slot that actually shows its colour, i.e. crossed over.
  assert fused[0]["center"]["x"] == 740
  assert fused[1]["center"]["x"] == 640


def test_unmatchable_card_gets_no_geometry() -> None:
  """No coordinate is a STALL — visible and fixable. A wrong coordinate is a wrong
  move — silent and unfixable. So the ambiguous card must come back bare."""
  cards = [{"color": "red", "value": "1"}, {"color": "blue", "value": "2"}]
  slots = [_slot(0, "red", 600), _slot(1, "red", 700), _slot(2, "red", 800)]

  fused, diag = attach_hand_geometry(cards, slots)

  assert "center" in fused[0]
  assert "center" not in fused[1] and "bounds" not in fused[1]
  assert diag["grounded"] == 1


def test_low_confidence_slot_colour_does_not_veto_alignment() -> None:
  """The colour check catches a gross shift; it must not second-guess the model on a
  slot the classifier itself is unsure about."""
  cards = [{"color": "red", "value": "1"}, {"color": "green", "value": "8"}]
  slots = [_slot(0, "red", 600), _slot(1, "blue", 700, conf=0.2)]

  fused, diag = attach_hand_geometry(cards, slots)

  assert diag["method"] == "index" and diag["grounded"] == 2


def test_empty_inputs_report_why() -> None:
  """The diagnostic lands in the cycle trace; 'no geometry' must say which half was
  missing, or the next debugging session starts from zero again."""
  _, no_cards = attach_hand_geometry([], [_slot(0, "red", 600)])
  assert no_cards["grounded"] == 0 and "no cards" in no_cards["reason"]

  _, no_slots = attach_hand_geometry([{"color": "red", "value": "1"}], [])
  assert no_slots["grounded"] == 0 and "segmentation" in no_slots["reason"]


def test_accepts_dict_shaped_slots() -> None:
  """Callers should not need to import the dataclass to supply geometry."""
  cards = [{"color": "red", "value": "1"}]
  slots = [{"color": "red", "center": {"x": 640, "y": 760},
            "bounds": {"x": 600, "y": 700, "width": 80, "height": 120},
            "color_confidence": 0.9}]

  fused, diag = attach_hand_geometry(cards, slots)

  assert diag["grounded"] == 1
  assert fused[0]["center"] == {"x": 640, "y": 760}


# --- CV count-recovery (the 3b VLM hand-collapse, 2026-08-28) ----------------
# The small VLM degenerates: on a real 9-card fan it returned hand_cards=[red 7]
# (identical to the top card, conf 0.5). Segmentation measured 9 slots. Recovery
# turns the surplus measured slots into colour-only cards (value "unknown") so the
# agent knows the hand is bigger than one. Gated so the normal off-by-one never
# fires, and a VLM that read most of the hand is never padded.

def _fan(n: int, colors: list[str], start_x: int = 300, step: int = 100) -> list[SimpleNamespace]:
  slots = []
  for i in range(n):
    x = start_x + i * step
    slots.append(SimpleNamespace(
      slot_index=i, color=colors[i % len(colors)],
      bounds=(x, 700, 80, 120), center=(x + 40, 760), color_confidence=0.9,
    ))
  return slots


def test_collapse_to_one_recovers_full_hand() -> None:
  """The live failure: VLM says 1 red 7, CV measured 9 slots of real colours.
  The recovered hand must keep the VLM's red 7 AND add the 8 missing cards as
  colour-only (value unknown, measured coordinate), in left-to-right order."""
  colors = ["red", "green", "blue", "yellow", "red", "green", "blue", "yellow", "red"]
  cards = [{"color": "red", "value": "7"}]  # the VLM's single collapsed card
  slots = _fan(9, colors)

  fused, diag = attach_hand_geometry(cards, slots)

  assert diag["method"] == "cv_count_recovery"
  assert len(fused) == 9
  assert diag["grounded"] == 1 and diag["recovered"] == 8
  # The VLM card survives, untouched.
  assert any(c["value"] == "7" for c in fused)
  # Recovered cards are colour-only with a measured centre, in fan order.
  unknowns = [c for c in fused if c["value"] == "unknown"]
  assert len(unknowns) == 8
  assert all(c["center"]["x"] is not None for c in unknowns)
  assert all(c["geometry_source"] == "cv_recovered_color_only" for c in unknowns)
  # Left-to-right: the centre-x is non-decreasing.
  xs = [c["center"]["x"] for c in fused]
  assert xs == sorted(xs)


def test_off_by_one_does_not_recover() -> None:
  """Segmentation's width estimate is often off by ONE. A single surplus slot
  must NOT fabricate a card — that would be a guess, and this layer never guesses."""
  cards = [
    {"color": "red", "value": "1"},
    {"color": "green", "value": "8"},
  ]
  slots = _fan(3, ["red", "green", "blue"])  # one extra slot

  fused, diag = attach_hand_geometry(cards, slots)

  # Falls through to colour matching; the lone surplus slot is too few to recover.
  assert diag["method"] != "cv_count_recovery"
  assert "recovered" not in diag
  # No card with value "unknown" was invented.
  assert all(c["value"] != "unknown" for c in fused)


def test_wild_slot_is_never_recovered() -> None:
  """A 'wild' (dark) slot cannot be told from a draw-four by colour — recovering
  it as a colour-only card would be a guess, so it is skipped even when there is
  a large surplus."""
  cards = [{"color": "red", "value": "7"}]
  slots = _fan(4, ["red", "wild", "green", "blue"])

  fused, diag = attach_hand_geometry(cards, slots)

  assert diag["method"] == "cv_count_recovery"
  # red 7 (VLM) + green + blue recovered; the wild slot is absent.
  assert len(fused) == 3
  assert all(c["color"] != "wild" for c in fused)


def test_low_confidence_slot_not_recovered() -> None:
  """A slot whose colour is a coin flip (low confidence) is not recovered: the
  colour would be a guess, and a wrong colour is worse than an absent card."""
  cards = [{"color": "red", "value": "7"}]
  slots = [
    _slot(0, "red", 300),
    _slot(1, "green", 400, conf=0.2),  # low confidence
    _slot(2, "blue", 500, conf=0.2),   # low confidence
    _slot(3, "yellow", 600, conf=0.9), # the only trustworthy one
  ]

  fused, diag = attach_hand_geometry(cards, slots)

  # Only the yellow slot is recovered (green/blue are coin flips).
  assert len(fused) == 2  # red 7 + yellow
  assert [c for c in fused if c["value"] == "unknown"][0]["color"] == "yellow"
