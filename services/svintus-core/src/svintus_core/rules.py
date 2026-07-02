"""Svintus rules — legal action generation and validation."""

from __future__ import annotations

from uuid import uuid4

from svintus_core.state import SvintusCard, SvintusState


def _can_play_on_top(card: SvintusCard, state: SvintusState) -> bool:
    top = state.top_card
    effective = state.effective_color
    if card.color == "wild":
        return True
    if top.color == "wild" or top.value in ("wild", "wild_draw_four"):
        return card.color == effective
    return card.color == top.color or card.value == top.value


def generate_legal_actions(state: SvintusState, player_id: str | None = None) -> list[dict]:
    """Generate legal actions for current game state."""
    if state.winner_id:
        return []

    pid = player_id or state.current_player.player_id
    if pid != state.current_player.player_id:
        return []

    actions = []
    hand = state.hands.get(pid, [])

    if state.pending_draw > 0:
        actions.append({
            "action_type": "draw_card",
            "player_id": pid,
            "action_id": str(uuid4()),
            "payload": {},
        })
        return actions

    playable = [c for c in hand if _can_play_on_top(c, state)]
    for card in playable:
        if card.color == "wild":
            for color in ("red", "yellow", "green", "blue"):
                actions.append({
                    "action_type": "play_card",
                    "player_id": pid,
                    "action_id": str(uuid4()),
                    "payload": {
                        "card": {"color": card.color, "value": card.value},
                        "chosen_color": color,
                    },
                })
        else:
            actions.append({
                "action_type": "play_card",
                "player_id": pid,
                "action_id": str(uuid4()),
                "payload": {
                    "card": {"color": card.color, "value": card.value},
                },
            })

    actions.append({
        "action_type": "draw_card",
        "player_id": pid,
        "action_id": str(uuid4()),
        "payload": {},
    })

    if len(hand) == 2 and pid not in state.said_svintus:
        actions.append({
            "action_type": "call_svintus",
            "player_id": pid,
            "action_id": str(uuid4()),
            "payload": {},
        })

    return actions


def is_action_legal(state: SvintusState, action: dict) -> bool:
    legal = generate_legal_actions(state, action.get("player_id"))
    return any(
        a["action_id"] == action.get("action_id") for a in legal
    ) or _match_action(legal, action)


def _match_action(legal: list[dict], action: dict) -> bool:
    for a in legal:
        if (a["action_type"] == action.get("action_type")
            and a["player_id"] == action.get("player_id")
            and a.get("payload", {}).get("card") == action.get("payload", {}).get("card")
            and a.get("payload", {}).get("chosen_color")
            == action.get("payload", {}).get("chosen_color")):
            return True
    return False


def validate_action(state: SvintusState, action: dict) -> tuple[bool, str]:
    if state.winner_id:
        return False, "game already finished"
    if action.get("player_id") != state.current_player.player_id:
        return False, "not player's turn"
    if not is_action_legal(state, action):
        return False, "illegal action"
    return True, "ok"
