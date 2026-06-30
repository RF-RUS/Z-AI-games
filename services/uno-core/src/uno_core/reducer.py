"""Apply actions and emit domain events."""

from __future__ import annotations

import time
from copy import deepcopy
from uuid import uuid4

from uno_schemas.game import (
  ActionType,
  CardColor,
  CardValue,
  DomainEvent,
  EventType,
  LegalAction,
  PublicTableState,
)

from uno_core.rules import validate_action
from uno_core.state import GameState


def _now_ms() -> int:
  return int(time.time() * 1000)


def apply_action(state: GameState, action: LegalAction, session_id: str | None = None) -> tuple[GameState, list[DomainEvent]]:
  ok, msg = validate_action(state, action)
  if not ok:
    raise ValueError(msg)

  new_state = deepcopy(state)
  events: list[DomainEvent] = []
  seq = new_state.sequence

  def emit(event_type: EventType, payload: dict) -> None:
    nonlocal seq
    seq += 1
    events.append(
      DomainEvent(
        event_id=str(uuid4()),
        event_type=event_type,
        game_id=new_state.game_id,
        session_id=session_id,
        sequence=seq,
        timestamp_ms=_now_ms(),
        payload=payload,
      )
    )

  pid = action.player_id
  hand = new_state.hands[pid]

  if action.action_type == ActionType.CALL_UNO:
    new_state.said_uno.add(pid)
    emit(EventType.UNO_CALLED, {"player_id": pid})
  elif action.action_type == ActionType.DRAW_CARD:
    draw_count = max(1, new_state.pending_draw)
    drawn = []
    for _ in range(draw_count):
      if not new_state.draw_pile:
        _reshuffle_draw_pile(new_state)
      if new_state.draw_pile:
        card = new_state.draw_pile.pop()
        hand.append(card)
        drawn.append(card.model_dump())
    new_state.pending_draw = 0
    emit(EventType.CARD_DRAWN, {"player_id": pid, "cards": drawn, "count": len(drawn)})
    new_state.advance_turn()
  elif action.action_type == ActionType.PLAY_CARD:
    card = action.card
    assert card is not None
    hand.remove(card)
    new_state.discard_pile.append(card)
    new_state.pending_draw = 0

    if card.color == CardColor.WILD and action.chosen_color:
      new_state.active_color = action.chosen_color
      emit(EventType.COLOR_CHOSEN, {"player_id": pid, "color": action.chosen_color.value})
    elif card.color != CardColor.WILD:
      new_state.active_color = None

    emit(EventType.CARD_PLAYED, {"player_id": pid, "card": card.model_dump()})

    if len(hand) == 0:
      new_state.winner_id = pid
      emit(EventType.PLAYER_WON, {"player_id": pid})
      emit(EventType.GAME_ENDED, {"winner_id": pid})
    else:
      _apply_card_effect(new_state, card, emit)
      if not new_state.winner_id:
        new_state.advance_turn(_skip_steps_for(card))

  new_state.sequence = seq
  return new_state, events


def _reshuffle_draw_pile(state: GameState) -> None:
  if len(state.discard_pile) <= 1:
    return
  top = state.discard_pile.pop()
  state.draw_pile = state.discard_pile
  state.discard_pile = [top]
  from uno_core.deck import shuffle_deck
  state.draw_pile = shuffle_deck(state.draw_pile)


def _skip_steps_for(card) -> int:
  if card.value == CardValue.SKIP:
    return 2
  return 1


def _apply_card_effect(state: GameState, card, emit) -> None:
  if card.value == CardValue.REVERSE:
    if len(state.players) == 2:
      emit(EventType.TURN_SKIPPED, {"player_id": state.next_player_id()})
    else:
      state.direction *= -1
      emit(EventType.DIRECTION_REVERSED, {"direction": state.direction})
  elif card.value == CardValue.SKIP:
    emit(EventType.TURN_SKIPPED, {"player_id": state.next_player_id()})
  elif card.value == CardValue.DRAW_TWO:
    state.pending_draw += 2
    emit(EventType.DRAW_PENALTY_APPLIED, {"amount": 2, "target": state.next_player_id()})
  elif card.value == CardValue.WILD_DRAW_FOUR:
    state.pending_draw += 4
    emit(EventType.DRAW_PENALTY_APPLIED, {"amount": 4, "target": state.next_player_id()})


def to_public_table_state(state: GameState) -> PublicTableState:
  return PublicTableState(
    top_card=state.top_card,
    draw_pile_count=len(state.draw_pile),
    discard_pile_count=len(state.discard_pile),
    current_player_id=state.current_player.player_id,
    direction=state.direction,
    pending_draw=state.pending_draw,
  )
