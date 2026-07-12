"""Tests for perceived legal actions (9d) — play the RIGHT card, not the leftmost.

Pure-function tests: legal moves come from the detected hand + top card via the
UNO match rule, so a chosen action carries the real card's colour+value. The
board in test_matches_real_screenshot mirrors the user's Ubisoft UNO frame
(top = yellow reverse; hand = red 6, green reverse, yellow reverse).
"""

from __future__ import annotations

from uno_orchestrator.perceived_actions import (
    _to_card,
    legal_actions_from_perception,
)
from uno_schemas.game import ActionType, CardColor, CardValue


def test_to_card_maps_aliases():
    c = _to_card({"color": "yellow", "value": "reverse"})
    assert c is not None and c.color == CardColor.YELLOW and c.value == CardValue.REVERSE
    assert _to_card({"color": "red", "value": "6"}).value == CardValue.SIX
    assert _to_card({"color": "wild", "value": "+4"}).value == CardValue.WILD_DRAW_FOUR


def test_to_card_rejects_unreadable():
    assert _to_card({"color": "red", "value": ""}) is None       # colour-only
    assert _to_card({"color": "", "value": "6"}) is None          # no colour
    assert _to_card({"color": "chartreuse", "value": "6"}) is None
    assert _to_card("nope") is None


def test_matches_real_screenshot_board():
    """User's frame: top yellow reverse; hand red6 / green reverse / yellow reverse.

    Playable = green reverse (value match) + yellow reverse (colour+value). Red 6
    does not match. DRAW is always present. Each play action carries its card.
    """
    top = {"color": "yellow", "value": "reverse"}
    hand = [
        {"color": "red", "value": "6"},
        {"color": "green", "value": "reverse"},
        {"color": "yellow", "value": "reverse"},
    ]
    actions = legal_actions_from_perception(hand, top)
    assert actions is not None
    plays = [a for a in actions if a.action_type == ActionType.PLAY_CARD]
    draws = [a for a in actions if a.action_type == ActionType.DRAW_CARD]
    assert len(draws) == 1
    played = {(a.card.color.value, a.card.value.value) for a in plays}
    assert played == {("green", "reverse"), ("yellow", "reverse")}
    # red 6 (no match) must NOT be offered as a play
    assert ("red", "6") not in played


def test_wild_always_playable():
    top = {"color": "red", "value": "6"}
    hand = [{"color": "wild", "value": "wild"}, {"color": "blue", "value": "2"}]
    actions = legal_actions_from_perception(hand, top)
    played = {(a.card.color.value, a.card.value.value)
              for a in actions if a.action_type == ActionType.PLAY_CARD}
    assert ("wild", "wild") in played
    assert ("blue", "2") not in played  # no colour/value match to red 6


def test_falls_back_when_board_unreadable():
    """No top card, empty hand, or colour-only hand → None (use the engine)."""
    assert legal_actions_from_perception(None, {"color": "red", "value": "6"}) is None
    assert legal_actions_from_perception([{"color": "red", "value": "6"}], None) is None
    # colour-only hand (values unreadable) → None, don't blind-play
    assert legal_actions_from_perception(
        [{"color": "red", "value": ""}], {"color": "red", "value": "6"}
    ) is None


def test_no_playable_still_offers_draw():
    top = {"color": "red", "value": "6"}
    hand = [{"color": "green", "value": "2"}, {"color": "blue", "value": "9"}]
    actions = legal_actions_from_perception(hand, top)
    assert actions is not None
    assert [a.action_type for a in actions] == [ActionType.DRAW_CARD]
