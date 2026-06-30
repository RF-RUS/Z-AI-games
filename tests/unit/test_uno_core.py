"""UNO core unit tests."""

from uuid import uuid4

import pytest
from uno_core.deck import build_standard_deck
from uno_core.reducer import apply_action
from uno_core.rules import generate_legal_actions, validate_action
from uno_core.state import create_initial_state
from uno_schemas.game import ActionType, Card, CardColor, CardValue, LegalAction


def test_standard_deck_size():
  deck = build_standard_deck()
  assert len(deck) == 108


def test_create_game_deals_seven_cards():
  state = create_initial_state("g1", ["A", "B"], seed=42)
  assert all(len(h) == 7 for h in state.hands.values())
  assert len(state.players) == 2


def test_legal_actions_include_draw():
  state = create_initial_state("g1", ["A", "B"], seed=1)
  actions = generate_legal_actions(state)
  assert any(a.action_type == ActionType.DRAW_CARD for a in actions)


def test_play_card_reduces_hand():
  state = create_initial_state("g1", ["A", "B"], seed=99)
  pid = state.current_player.player_id
  hand_before = len(state.hands[pid])
  actions = [a for a in generate_legal_actions(state) if a.action_type == ActionType.PLAY_CARD]
  if not actions:
    pytest.skip("no playable card")
  new_state, events = apply_action(state, actions[0])
  assert len(new_state.hands[pid]) == hand_before - 1
  assert len(events) >= 1


def test_illegal_action_rejected():
  state = create_initial_state("g1", ["A", "B"], seed=2)
  bad = LegalAction(
    action_type=ActionType.PLAY_CARD,
    player_id=state.players[1].player_id,
    card=Card(color=CardColor.RED, value=CardValue.NINE),
    action_id=str(uuid4()),
  )
  ok, msg = validate_action(state, bad)
  assert not ok
