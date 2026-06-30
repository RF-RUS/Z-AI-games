"""UNO game plugin — first GamePlugin implementation.

Wraps the existing uno-core engine as a GamePlugin, making the
orchestrator game-agnostic while preserving all UNO-specific behavior.

The plugin maintains an internal state registry keyed by game_id,
since full game state (including private hands) cannot be serialized
into the opaque GameSnapshot.
"""

from __future__ import annotations

from typing import Any

from uno_shared.game_plugin import GameAction, GameEvent, GameSnapshot

from uno_core.reducer import apply_action as uno_apply_action
from uno_core.reducer import to_public_table_state
from uno_core.rules import generate_legal_actions
from uno_core.rules import validate_action as uno_validate_action
from uno_core.state import GameState, create_initial_state


class UnoGamePlugin:
    """UNO game plugin implementing the GamePlugin protocol.

    Maintains internal GameState registry for full state access.
    GameSnapshot is the external (serialized) view; GameState is the
    internal (canonical) view.
    """

    game_type = "uno"

    def __init__(self) -> None:
        self._states: dict[str, GameState] = {}

    def create_game(
        self,
        game_id: str,
        player_names: list[str],
        seed: int | None = None,
    ) -> GameSnapshot:
        state = create_initial_state(game_id, player_names, seed)
        self._states[game_id] = state
        return _state_to_snapshot(state)

    def get_legal_actions(self, state: GameSnapshot) -> list[GameAction]:
        internal = self._get_internal(state.game_id)
        actions = generate_legal_actions(internal)
        return [_legal_action_to_game_action(a) for a in actions]

    def validate_action(
        self, state: GameSnapshot, action: GameAction
    ) -> tuple[bool, str]:
        internal = self._get_internal(state.game_id)
        legal_action = _game_action_to_legal_action(action, state)
        return uno_validate_action(internal, legal_action)

    def apply_action(
        self,
        state: GameSnapshot,
        action: GameAction,
        session_id: str | None = None,
    ) -> tuple[GameSnapshot, list[GameEvent]]:
        internal = self._get_internal(state.game_id)
        legal_action = _game_action_to_legal_action(action, state)
        new_state, events = uno_apply_action(internal, legal_action, session_id)
        self._states[state.game_id] = new_state
        return _state_to_snapshot(new_state), [
            GameEvent(
                event_type=e.event_type.value,
                game_id=e.game_id,
                payload=e.payload,
                correlation_id=e.correlation_id,
            )
            for e in events
        ]

    def parse_observation(
        self,
        raw_evidence: dict[str, Any],
        game_context: dict[str, Any] | None = None,
    ) -> GameSnapshot:
        return GameSnapshot(
            game_type="uno",
            game_id=raw_evidence.get("game_id", "unknown"),
            current_player_id=raw_evidence.get("current_player_id", "unknown"),
            public_state=raw_evidence,
        )

    def snapshot_to_observation(self, state: GameSnapshot) -> dict[str, Any]:
        return state.public_state

    def strategy_hints(
        self,
        state: GameSnapshot,
        observation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"game_type": "uno"}

    def _get_internal(self, game_id: str) -> GameState:
        if game_id not in self._states:
            raise KeyError(f"game not found: {game_id}")
        return self._states[game_id]

    def clear(self, game_id: str | None = None) -> None:
        """Clear internal state (for testing)."""
        if game_id:
            self._states.pop(game_id, None)
        else:
            self._states.clear()


# --- Conversion helpers ---


def _state_to_snapshot(state: GameState) -> GameSnapshot:
    public = to_public_table_state(state)
    return GameSnapshot(
        game_type="uno",
        game_id=state.game_id,
        current_player_id=state.current_player.player_id,
        players=[
            {"player_id": p.player_id, "display_name": p.display_name, "seat": p.seat}
            for p in state.players
        ],
        public_state=public.model_dump(),
        hand_size=state.hand_size(state.current_player.player_id),
        winner_id=state.winner_id,
        metadata={
            "direction": state.direction,
            "active_color": state.active_color.value if state.active_color else None,
            "pending_draw": state.pending_draw,
            "sequence": state.sequence,
        },
    )


def _legal_action_to_game_action(action) -> GameAction:
    payload: dict[str, Any] = {}
    if action.card:
        payload["card"] = {"color": action.card.color.value, "value": action.card.value.value}
    if action.chosen_color:
        payload["chosen_color"] = action.chosen_color.value
    return GameAction(
        action_type=action.action_type.value,
        player_id=action.player_id,
        action_id=action.action_id,
        payload=payload,
    )


def _game_action_to_legal_action(action: GameAction, snapshot: GameSnapshot):
    from uno_schemas.game import ActionType, Card, CardColor, CardValue, LegalAction

    card = None
    if "card" in action.payload:
        card_data = action.payload["card"]
        card = Card(
            color=CardColor(card_data["color"]),
            value=CardValue(card_data["value"]),
        )

    chosen_color = None
    if "chosen_color" in action.payload:
        chosen_color = CardColor(action.payload["chosen_color"])

    return LegalAction(
        action_type=ActionType(action.action_type),
        player_id=action.player_id,
        card=card,
        chosen_color=chosen_color,
        action_id=action.action_id,
    )
