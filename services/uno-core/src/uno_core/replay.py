"""Replay events back into state."""

from __future__ import annotations

from uno_schemas.game import DomainEvent, EventType, LegalAction, ReplayEnvelope

from uno_core.reducer import apply_action
from uno_core.state import GameState, create_initial_state


def replay_events(
  events: list[DomainEvent],
  player_names: list[str] | None = None,
) -> GameState:
  if not events:
    raise ValueError("no events to replay")

  game_id = events[0].game_id
  names = player_names or ["P1", "P2", "P3", "P4"]
  state = create_initial_state(game_id, names[:4])

  for event in sorted(events, key=lambda e: e.sequence):
    if event.event_type == EventType.CARD_PLAYED:
      from uno_schemas.game import ActionType, Card
      card = Card.model_validate(event.payload["card"])
      action = LegalAction(
        action_type=ActionType.PLAY_CARD,
        player_id=event.payload["player_id"],
        card=card,
        action_id=event.event_id,
      )
      state, _ = apply_action(state, action, event.session_id)
    elif event.event_type == EventType.CARD_DRAWN:
      from uno_schemas.game import ActionType
      action = LegalAction(
        action_type=ActionType.DRAW_CARD,
        player_id=event.payload["player_id"],
        action_id=event.event_id,
      )
      state, _ = apply_action(state, action, event.session_id)

  return state


def load_replay(envelope: ReplayEnvelope) -> GameState:
  names = envelope.metadata.get("player_names", ["P1", "P2", "P3", "P4"])
  return replay_events(envelope.events, names)
