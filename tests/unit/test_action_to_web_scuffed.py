"""Test adapter action mapping for scuffed-uno-web profile — with card identity."""

from uno_shared.adapter_registry import GenericAdapterClient, _find_card_slot_by_identity


def test_scuffed_play_card_uses_dynamic_slot():
  client = GenericAdapterClient("web", "http://noop")
  req = client.map_action("play_card", "scuffed-uno-web", card_color="red", card_value="5")
  assert req.action_type == "click_coordinate"
  assert req.selector_key == "hand_slot_0"
  assert req.extra.get("coordinate_reference") == "canvas"
  assert req.extra.get("card_color") == "red"
  assert req.extra.get("card_value") == "5"
  assert req.extra.get("slot_index") == 0


def test_scuffed_play_card_blue_uses_slot_1():
  client = GenericAdapterClient("web", "http://noop")
  req = client.map_action("play_card", "scuffed-uno-web", card_color="blue", card_value="skip")
  assert req.selector_key == "hand_slot_1"
  assert req.extra.get("card_color") == "blue"
  assert req.extra.get("slot_index") == 1


def test_scuffed_play_card_green_uses_slot_2():
  client = GenericAdapterClient("web", "http://noop")
  req = client.map_action("play_card", "scuffed-uno-web", card_color="green", card_value="7")
  assert req.selector_key == "hand_slot_2"
  assert req.extra.get("slot_index") == 2


def test_scuffed_play_card_no_color_uses_slot_0():
  client = GenericAdapterClient("web", "http://noop")
  req = client.map_action("play_card", "scuffed-uno-web")
  assert req.selector_key == "hand_slot_0"
  assert req.extra.get("slot_index") == 0
  assert req.extra.get("matched_by") == "color_fallback"


def test_scuffed_draw_uses_coordinate_click():
  client = GenericAdapterClient("web", "http://noop")
  req = client.map_action("draw_card", "scuffed-uno-web")
  assert req.action_type == "click_coordinate"
  assert req.selector_key == "draw"
  assert req.extra.get("coordinate_reference") == "canvas"


def test_local_mock_still_uses_dom_click():
  client = GenericAdapterClient("web", "http://noop")
  req = client.map_action("draw_card", "local-mock-uno")
  assert req.action_type == "click"
  assert req.selector == "[data-testid='btn-draw']"


# --- Card identity matching tests ---

def test_find_card_slot_by_identity_exact_match():
  hand_cards = [
    {"color": "red", "number": "5", "slot_index": 0},
    {"color": "blue", "number": "skip", "slot_index": 1},
  ]
  assert _find_card_slot_by_identity(hand_cards, "red", "5") == 0
  assert _find_card_slot_by_identity(hand_cards, "blue", "skip") == 1


def test_find_card_slot_by_color_only():
  hand_cards = [
    {"color": "red", "number": "5", "slot_index": 0},
    {"color": "red", "number": "7", "slot_index": 1},
  ]
  assert _find_card_slot_by_identity(hand_cards, "red", None) == 0


def test_find_card_slot_no_match():
  hand_cards = [
    {"color": "red", "number": "5", "slot_index": 0},
    {"color": "blue", "number": "skip", "slot_index": 1},
  ]
  assert _find_card_slot_by_identity(hand_cards, "yellow", "3") is None


def test_find_card_slot_empty_hand():
  assert _find_card_slot_by_identity([], "red", "5") is None


def test_map_action_with_hand_cards():
  client = GenericAdapterClient("web", "http://noop")
  hand_cards = [
    {"color": "red", "number": "5", "slot_index": 0},
    {"color": "blue", "number": "skip", "slot_index": 1},
    {"color": "green", "number": "7", "slot_index": 2},
  ]
  req = client.map_action("play_card", "scuffed-uno-web", card_color="green", card_value="7", hand_cards=hand_cards)
  assert req.selector_key == "hand_slot_2"
  assert req.extra.get("matched_by") == "identity"
  assert req.extra.get("slot_index") == 2


def test_map_action_identity_fallback_to_color():
  client = GenericAdapterClient("web", "http://noop")
  hand_cards = [
    {"color": "red", "number": "5", "slot_index": 0},
  ]
  req = client.map_action("play_card", "scuffed-uno-web", card_color="blue", card_value="3", hand_cards=hand_cards)
  assert req.selector_key == "hand_slot_1"
  assert req.extra.get("matched_by") == "color_fallback"
