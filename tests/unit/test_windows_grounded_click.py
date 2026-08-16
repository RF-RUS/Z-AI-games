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


def test_find_card_center_refuses_when_the_colour_is_absent():
  """No red card exists, so there is NO correct coordinate — and none must be invented.

  This used to return the first card in the hand (a green one). That is the worst bug
  shape this project has: the decision was "play red", the agent clicked green, and the
  step was logged as delivered. No coordinate makes the agent stall, which is visible
  and fixable; a wrong coordinate is a move it never chose. See `_find_card_center`.
  """
  assert _find_card_center(HAND, "red", None) is None
  assert _find_card_center(None, "blue", None) is None
  assert _find_card_center([], "blue", None) is None


def test_colour_only_match_still_works_for_valueless_heuristic_cards():
  """The heuristic reads colour but never the number, emitting `value: "unknown"`.

  Asking for blue 7 when the only blue card's value is unreadable: that card is the best
  available inference, so it is allowed. Refusing here would make the agent unable to
  play at all whenever the VLM is off.
  """
  assert _find_card_center(HAND, "blue", "7") == (574, 652)


def test_known_different_value_is_never_a_substitute():
  """With a real value present, a mismatch is a contradiction, not a gap to paper over."""
  hand = [{"color": "red", "value": "9", "center": {"x": 300, "y": 650}}]
  assert _find_card_center(hand, "red", "4") is None
  # ...and the same card is clickable when it IS the one that was chosen.
  assert _find_card_center(hand, "red", "9") == (300, 650)


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
