"""Game plugin registry — dynamic lookup of game implementations.

The orchestrator uses the registry to get the correct game plugin
without knowing about concrete game types.
"""

from __future__ import annotations

from uno_shared.game_plugin import GamePlugin

_registry: dict[str, GamePlugin] = {}


def register_game_plugin(game_type: str, plugin: GamePlugin) -> None:
    """Register a game plugin implementation."""
    _registry[game_type] = plugin


def get_game_plugin(game_type: str) -> GamePlugin:
    """Get a registered game plugin by game type.

    Raises KeyError if no plugin registered for game_type.
    """
    if game_type not in _registry:
        raise KeyError(f"no game plugin registered for: {game_type}")
    return _registry[game_type]


def has_game_plugin(game_type: str) -> bool:
    """Check if a game plugin is registered."""
    return game_type in _registry


def list_game_plugins() -> list[str]:
    """List all registered game types."""
    return list(_registry.keys())


def _ensure_default_plugins() -> None:
    """Register default game plugins if not already registered."""
    if "uno" not in _registry:
        from uno_core.game_plugin import UnoGamePlugin
        _registry["uno"] = UnoGamePlugin()
    if "svintus" not in _registry:
        try:
            from svintus_core.game_plugin import SvintusGamePlugin
            _registry["svintus"] = SvintusGamePlugin()
        except ImportError:
            pass  # svintus-core not installed
