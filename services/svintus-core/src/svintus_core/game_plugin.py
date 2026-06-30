"""Svintus game plugin — second GamePlugin implementation.

Demonstrates that the GamePlugin protocol works with a game
different from UNO. This is the proof-of-multi-game.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from uno_shared.game_plugin import GameAction, GameEvent, GameSnapshot

from svintus_core.reducer import apply_action as svintus_apply
from svintus_core.reducer import to_public_state
from svintus_core.rules import generate_legal_actions
from svintus_core.rules import validate_action as svintus_validate
from svintus_core.state import SvintusState, create_svintus_state


class SvintusGamePlugin:
    """Svintus game plugin implementing the GamePlugin protocol.

    Key differences from UNO:
    - game_type = "svintus"
    - action_type "call_svintus" instead of "call_uno"
    - Penalty for forgetting to call is 3 cards (instead of 2)
    - Same card set for this PoC
    """

    game_type = "svintus"

    def __init__(self) -> None:
        self._states: dict[str, SvintusState] = {}

    def create_game(
        self,
        game_id: str,
        player_names: list[str],
        seed: int | None = None,
    ) -> GameSnapshot:
        state = create_svintus_state(game_id, player_names, seed)
        self._states[game_id] = state
        return _state_to_snapshot(state)

    def get_legal_actions(self, state: GameSnapshot) -> list[GameAction]:
        internal = self._get_internal(state.game_id)
        actions = generate_legal_actions(internal)
        return [_dict_to_game_action(a) for a in actions]

    def validate_action(
        self, state: GameSnapshot, action: GameAction
    ) -> tuple[bool, str]:
        internal = self._get_internal(state.game_id)
        action_dict = _game_action_to_dict(action)
        return svintus_validate(internal, action_dict)

    def apply_action(
        self,
        state: GameSnapshot,
        action: GameAction,
        session_id: str | None = None,
    ) -> tuple[GameSnapshot, list[GameEvent]]:
        internal = self._get_internal(state.game_id)
        action_dict = _game_action_to_dict(action)
        new_state, events = svintus_apply(internal, action_dict, session_id)
        self._states[state.game_id] = new_state
        return _state_to_snapshot(new_state), [
            GameEvent(
                event_type=e.get("event_type", "unknown"),
                game_id=e.get("game_id", state.game_id),
                payload=e.get("payload", {}),
            )
            for e in events
        ]

    def parse_observation(
        self,
        raw_evidence: dict[str, Any],
        game_context: dict[str, Any] | None = None,
    ) -> GameSnapshot:
        return GameSnapshot(
            game_type="svintus",
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
        return {"game_type": "svintus", "call_word": "svintus", "penalty_cards": 3}

    def _get_internal(self, game_id: str) -> SvintusState:
        if game_id not in self._states:
            raise KeyError(f"game not found: {game_id}")
        return self._states[game_id]

    def clear(self, game_id: str | None = None) -> None:
        if game_id:
            self._states.pop(game_id, None)
        else:
            self._states.clear()


# --- Conversion helpers ---


def _state_to_snapshot(state: SvintusState) -> GameSnapshot:
    public = to_public_state(state)
    return GameSnapshot(
        game_type="svintus",
        game_id=state.game_id,
        current_player_id=state.current_player.player_id,
        players=[
            {"player_id": p.player_id, "display_name": p.display_name, "seat": p.seat}
            for p in state.players
        ],
        public_state=public,
        hand_size=state.hand_size(state.current_player.player_id),
        winner_id=state.winner_id,
        metadata={
            "direction": state.direction,
            "active_color": state.active_color,
            "pending_draw": state.pending_draw,
            "sequence": state.sequence,
            "said_svintus": list(state.said_svintus),
        },
    )


def _dict_to_game_action(action_dict: dict) -> GameAction:
    return GameAction(
        action_type=action_dict["action_type"],
        player_id=action_dict["player_id"],
        action_id=action_dict.get("action_id", str(uuid4())),
        payload=action_dict.get("payload", {}),
    )


def _game_action_to_dict(action: GameAction) -> dict:
    return {
        "action_type": action.action_type,
        "player_id": action.player_id,
        "action_id": action.action_id,
        "payload": action.payload,
    }
