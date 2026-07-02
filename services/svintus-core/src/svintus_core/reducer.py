"""Svintus reducer — apply actions and generate events."""

from __future__ import annotations

from svintus_core.state import SvintusCard, SvintusState


def apply_action(
    state: SvintusState, action: dict, session_id: str | None = None
) -> tuple[SvintusState, list[dict]]:
    """Apply an action to the game state and return new state + events."""
    action_type = action.get("action_type")
    player_id = action.get("player_id")
    payload = action.get("payload", {})
    events = []

    if action_type == "play_card":
        card_data = payload.get("card", {})
        card = SvintusCard(color=card_data["color"], value=card_data["value"])

        if card in state.hands.get(player_id, []):
            state.hands[player_id].remove(card)
        state.discard_pile.append(card)

        chosen_color = payload.get("chosen_color")
        if card.color == "wild" and chosen_color:
            state.active_color = chosen_color
        else:
            state.active_color = None

        if len(state.hands.get(player_id, [])) == 0:
            state.winner_id = player_id
            events.append({
                "event_type": "player_won",
                "game_id": state.game_id,
                "payload": {"winner_id": player_id},
            })

        _apply_card_effect(state, card)
        events.append({
            "event_type": "card_played",
            "game_id": state.game_id,
            "payload": {"card": card_data, "player_id": player_id},
        })

    elif action_type == "draw_card":
        for _ in range(max(1, state.pending_draw)):
            if state.draw_pile:
                drawn = state.draw_pile.pop()
                state.hands.setdefault(player_id, []).append(drawn)
            else:
                _reshuffle_discard(state)
                if state.draw_pile:
                    drawn = state.draw_pile.pop()
                    state.hands.setdefault(player_id, []).append(drawn)
        state.pending_draw = 0
        events.append({
            "event_type": "card_drawn",
            "game_id": state.game_id,
            "payload": {"player_id": player_id},
        })

    elif action_type == "call_svintus":
        state.said_svintus.add(player_id)
        events.append({
            "event_type": "svintus_called",
            "game_id": state.game_id,
            "payload": {"player_id": player_id},
        })

    state.advance_turn()
    state.sequence += 1
    return state, events


def _apply_card_effect(state: SvintusState, card: SvintusCard) -> None:
    if card.value == "skip":
        state.advance_turn()
    elif card.value == "reverse":
        state.direction *= -1
        if len(state.players) == 2:
            state.advance_turn()
    elif card.value == "draw_two":
        state.pending_draw += 2
    elif card.value == "wild_draw_four":
        state.pending_draw += 4


def _reshuffle_discard(state: SvintusState) -> None:
    if len(state.discard_pile) <= 1:
        return
    top = state.discard_pile[-1]
    state.draw_pile = state.discard_pile[:-1]
    state.discard_pile = [top]
    import random
    random.shuffle(state.draw_pile)


def to_public_state(state: SvintusState) -> dict:
    return {
        "top_card": {"color": state.top_card.color, "value": state.top_card.value},
        "draw_pile_count": len(state.draw_pile),
        "discard_pile_count": len(state.discard_pile),
        "current_player_id": state.current_player.player_id,
        "direction": state.direction,
        "pending_draw": state.pending_draw,
        "hand_sizes": {p.player_id: state.hand_size(p.player_id) for p in state.players},
    }
