"""Game service client — unified interface for game operations.

Wraps GamePlugin calls into a service-like client that the orchestrator
can use instead of direct uno-core HTTP calls. This is the bridge between
the old HTTP-based game service and the new plugin-based architecture.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from uno_shared.game_plugin import GameAction, GameEvent, GamePlugin, GameSnapshot
from uno_shared.game_registry import _ensure_default_plugins, get_game_plugin


class GameServiceClient:
    """Unified client for game operations via GamePlugin.

    Provides the same interface shape as the old uno-core HTTP client
    but delegates to the registered GamePlugin instead.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, GameSnapshot] = {}

    def create_game(
        self,
        game_type: str,
        game_id: str,
        player_names: list[str],
        seed: int | None = None,
    ) -> GameSnapshot:
        plugin = self._get_plugin(game_type)
        snapshot = plugin.create_game(game_id, player_names, seed)
        self._snapshots[game_id] = snapshot
        return snapshot

    def get_snapshot(self, game_id: str) -> GameSnapshot | None:
        return self._snapshots.get(game_id)

    def legal_actions(self, game_id: str) -> list[GameAction]:
        snapshot = self._require_snapshot(game_id)
        plugin = self._get_plugin(snapshot.game_type)
        return plugin.get_legal_actions(snapshot)

    def apply_action(
        self,
        game_id: str,
        action: GameAction,
        session_id: str | None = None,
    ) -> tuple[GameSnapshot, list[GameEvent]]:
        snapshot = self._require_snapshot(game_id)
        plugin = self._get_plugin(snapshot.game_type)
        new_snapshot, events = plugin.apply_action(snapshot, action, session_id)
        self._snapshots[game_id] = new_snapshot
        return new_snapshot, events

    def validate_action(
        self, game_id: str, action: GameAction
    ) -> tuple[bool, str]:
        snapshot = self._require_snapshot(game_id)
        plugin = self._get_plugin(snapshot.game_type)
        return plugin.validate_action(snapshot, action)

    def _get_plugin(self, game_type: str) -> GamePlugin:
        _ensure_default_plugins()
        return get_game_plugin(game_type)

    def _require_snapshot(self, game_id: str) -> GameSnapshot:
        if game_id not in self._snapshots:
            raise KeyError(f"game not found: {game_id}")
        return self._snapshots[game_id]


def action_to_game_action(
    action_type: str,
    player_id: str,
    action_id: str | None = None,
    card: dict[str, Any] | None = None,
    chosen_color: str | None = None,
) -> GameAction:
    """Create a GameAction from simple parameters.

    Convenience helper for creating game actions without importing
    UNO-specific types.
    """
    payload: dict[str, Any] = {}
    if card:
        payload["card"] = card
    if chosen_color:
        payload["chosen_color"] = chosen_color
    return GameAction(
        action_type=action_type,
        player_id=player_id,
        action_id=action_id or str(uuid4()),
        payload=payload,
    )
