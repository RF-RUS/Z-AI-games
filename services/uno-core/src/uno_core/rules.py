"""Legal action generation and validation."""

from __future__ import annotations

from uuid import uuid4

from uno_schemas.game import ActionType, Card, CardColor, CardValue, LegalAction

from uno_core.state import GameState


def _can_play_on_top(card: Card, state: GameState) -> bool:
  top = state.top_card
  effective = state.effective_color
  if card.color == CardColor.WILD:
    return True
  if top.color == CardColor.WILD or top.value in (CardValue.WILD, CardValue.WILD_DRAW_FOUR):
    return card.color == effective
  return card.color == top.color or card.value == top.value


def generate_legal_actions(state: GameState, player_id: str | None = None) -> list[LegalAction]:
  if state.winner_id:
    return []

  pid = player_id or state.current_player.player_id
  if pid != state.current_player.player_id:
    return []

  actions: list[LegalAction] = []
  hand = state.hands[pid]

  if state.pending_draw > 0:
    actions.append(
      LegalAction(
        action_type=ActionType.DRAW_CARD,
        player_id=pid,
        action_id=str(uuid4()),
      )
    )
    return actions

  playable = [c for c in hand if _can_play_on_top(c, state)]
  for card in playable:
    # Wild cards need color choice — represented as separate actions per color for simplicity
    if card.color == CardColor.WILD:
      for color in (CardColor.RED, CardColor.YELLOW, CardColor.GREEN, CardColor.BLUE):
        actions.append(
          LegalAction(
            action_type=ActionType.PLAY_CARD,
            player_id=pid,
            card=card,
            chosen_color=color,
            action_id=str(uuid4()),
          )
        )
    else:
      actions.append(
        LegalAction(
          action_type=ActionType.PLAY_CARD,
          player_id=pid,
          card=card,
          action_id=str(uuid4()),
        )
      )

  # Can always draw if no play or chooses to
  actions.append(
    LegalAction(
      action_type=ActionType.DRAW_CARD,
      player_id=pid,
      action_id=str(uuid4()),
    )
  )

  if len(hand) == 2 and pid not in state.said_uno:
    actions.append(
      LegalAction(action_type=ActionType.CALL_UNO, player_id=pid, action_id=str(uuid4()))
    )

  return actions


def is_action_legal(state: GameState, action: LegalAction) -> bool:
  legal = generate_legal_actions(state, action.player_id)
  return any(a.action_id == action.action_id for a in legal) or _match_action(legal, action)


def _match_action(legal: list[LegalAction], action: LegalAction) -> bool:
  for a in legal:
    if (
      a.action_type == action.action_type
      and a.player_id == action.player_id
      and a.card == action.card
      and a.chosen_color == action.chosen_color
    ):
      return True
  return False


def validate_action(state: GameState, action: LegalAction) -> tuple[bool, str]:
  if state.winner_id:
    return False, "game already finished"
  if action.player_id != state.current_player.player_id:
    return False, "not player's turn"
  if not is_action_legal(state, action):
    return False, "illegal action"
  return True, "ok"
