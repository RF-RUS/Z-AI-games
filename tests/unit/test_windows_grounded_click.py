"""Windows execution grounding (task #9c): a chosen card is mapped to its
CV-detected screen coordinate so the agent clicks the real card, not a static
hardcoded point.
"""

from uno_shared.adapter_registry import (
  GenericAdapterClient,
  _find_card_center,
)

HAND = [
  {"card_id": "hand_0", "color": "green", "value": "unknown", "center": {"x": 452, "y": 652}},
  {"card_id": "hand_1", "color": "green", "value": "unknown", "center": {"x": 513, "y": 652}},
  {"card_id": "hand_2", "color": "blue", "value": "unknown", "center": {"x": 574, "y": 652}},
  {"card_id": "hand_6", "color": "wild", "value": "unknown", "center": {"x": 819, "y": 652}},
]


def test_find_card_center_prefers_color_match():
  assert _find_card_center(HAND, "blue", None) == (574, 652)
  assert _find_card_center(HAND, "green", None) == (452, 652)  # first green
  assert _find_card_center(HAND, "wild", None) == (819, 652)


def test_find_card_center_falls_back_to_first_card():
  assert _find_card_center(HAND, "red", None) == (452, 652)  # no red → first card
  assert _find_card_center(None, "blue", None) is None
  assert _find_card_center([], "blue", None) is None


def test_find_card_center_from_bounds_when_no_center():
  hand = [{"color": "blue", "bounds": {"x": 100, "y": 200, "width": 60, "height": 160}}]
  assert _find_card_center(hand, "blue", None) == (130, 280)


def test_map_action_windows_grounds_play_to_coordinate():
  client = GenericAdapterClient("windows", "http://noop")
  req = client.map_action("play_card", card_color="blue", hand_cards=HAND)
  assert req.extra.get("target_x") == 574
  assert req.extra.get("target_y") == 652
  assert req.extra.get("grounded_by") == "cv_detection"
  # still carries the selector for the UIA fallback path
  assert req.selector_key == "play_red_five"


def test_map_action_windows_no_handcards_no_target():
  client = GenericAdapterClient("windows", "http://noop")
  req = client.map_action("play_card", card_color="blue")
  assert "target_x" not in req.extra
  assert req.selector_key == "play_red_five"
