"""Game plugin contract — domain-only interface for game implementations.

Each game (UNO, Svintus, etc.) implements this protocol. The orchestrator
and core platform depend only on this interface, never on game-specific types.

GamePlugin is domain-only: it handles game state, rules, and legal actions.
Adapter-specific request translation lives in the adapter boundary.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class GameModelConfig(BaseModel):
    """Per-game model preferences — which models to use for each task.
    
    Each game plugin can declare preferred models. The platform routes
    to the best available model and falls back gracefully.
    """
    
    game_type: str
    
    # Strategy models (ordered by preference, first available wins)
    strategy_models: list[str] = Field(default_factory=lambda: ["heuristic"])
    
    # Vision models (for canvas/WebGL games that need screenshot perception)
    vision_models: list[str] = Field(default_factory=list)
    
    # Chat models
    chat_models: list[str] = Field(default_factory=list)
    
    # Intent detection models
    intent_models: list[str] = Field(default_factory=list)
    
    # Fallback behavior
    fallback_to_heuristic: bool = True
    fallback_to_template: bool = True
    fallback_to_mock: bool = True
    
    # Safety
    chat_enabled: bool = True
    model_chat_enabled: bool = False
    max_chat_length: int = 200


class GameSnapshot(BaseModel):
    """Game-agnostic state snapshot — opaque to core platform.

    Each game plugin populates this with its own state structure.
    Core platform treats it as an opaque dict.
    """

    game_type: str
    game_id: str
    current_player_id: str
    players: list[dict[str, Any]] = Field(default_factory=list)
    public_state: dict[str, Any] = Field(default_factory=dict)
    hand_size: int | None = None
    winner_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GameAction(BaseModel):
    """Game-agnostic legal action — opaque to core platform.

    Each game plugin defines its own action semantics.
    Core platform treats action_type and payload as opaque strings/dicts.
    """

    action_type: str
    player_id: str
    action_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class GameEvent(BaseModel):
    """Game-agnostic domain event — opaque to core platform."""

    event_type: str
    game_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class GamePlugin(Protocol):
    """Domain-only contract for game implementations.

    Responsibilities:
    - Game state management (create, snapshot, transition)
    - Legal action generation
    - Action validation
    - Action application (state transition)
    - Observation parsing (game-specific evidence → game state)
    - Strategy hints for decision layer
    - Model configuration (preferred models per task)

    NOT responsible for:
    - Adapter-specific request translation
    - UI element selection
    - Profile management
    - Transport/network concerns
    """

    game_type: str
    model_config: GameModelConfig

    def create_game(
        self,
        game_id: str,
        player_names: list[str],
        seed: int | None = None,
    ) -> GameSnapshot:
        """Create initial game state."""
        ...

    def get_legal_actions(self, state: GameSnapshot) -> list[GameAction]:
        """Generate legal actions for current game state."""
        ...

    def validate_action(
        self, state: GameSnapshot, action: GameAction
    ) -> tuple[bool, str]:
        """Validate if an action is legal. Returns (is_valid, reason)."""
        ...

    def apply_action(
        self,
        state: GameSnapshot,
        action: GameAction,
        session_id: str | None = None,
    ) -> tuple[GameSnapshot, list[GameEvent]]:
        """Apply action, return new state + events."""
        ...

    def parse_observation(
        self,
        raw_evidence: dict[str, Any],
        game_context: dict[str, Any] | None = None,
    ) -> GameSnapshot:
        """Parse raw adapter evidence into game state.
        This is where game-specific extraction lives.
        """
        ...

    def snapshot_to_observation(
        self, state: GameSnapshot
    ) -> dict[str, Any]:
        """Convert game snapshot to observation-compatible dict.
        Used by perception merger for game-specific state construction.
        """
        ...

    def strategy_hints(
        self,
        state: GameSnapshot,
        observation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Provide game-specific hints for decision strategy.
        Returns opaque dict that decision layer can use.
        """
        ...
