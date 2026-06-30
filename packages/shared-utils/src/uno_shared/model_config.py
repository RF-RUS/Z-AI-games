"""Game model configuration registry.

Maps game_type → GameModelConfig. Games register their preferred models
at startup. Orchestrator reads this to route model calls.
"""

from __future__ import annotations

import logging

from uno_shared.game_plugin import GameModelConfig

logger = logging.getLogger("model_config")

# Default configs for known games
_DEFAULT_CONFIGS: dict[str, GameModelConfig] = {
    "uno": GameModelConfig(
        game_type="uno",
        strategy_models=["mock/uno-assistant"],
        vision_models=[],
        chat_models=["mock/uno-assistant"],
        intent_models=[],
        fallback_to_heuristic=True,
        chat_enabled=True,
        model_chat_enabled=True,
    ),
    "svintus": GameModelConfig(
        game_type="svintus",
        strategy_models=["heuristic"],
        vision_models=[],
        chat_models=[],
        intent_models=[],
        fallback_to_heuristic=True,
        chat_enabled=False,
    ),
}

# Runtime registry (mutable)
_registry: dict[str, GameModelConfig] = dict(_DEFAULT_CONFIGS)


def register_game_config(config: GameModelConfig) -> None:
    """Register a game model configuration."""
    _registry[config.game_type] = config
    logger.info("game_config_registered game_type=%s strategy=%s vision=%s chat=%s",
                config.game_type, config.strategy_models, config.vision_models, config.chat_models)


def get_game_config(game_type: str) -> GameModelConfig:
    """Get model config for a game type. Returns default if not registered."""
    if game_type in _registry:
        return _registry[game_type]
    # Return generic default for unknown games
    return GameModelConfig(
        game_type=game_type,
        strategy_models=["heuristic"],
        vision_models=[],
        chat_models=[],
        intent_models=[],
        fallback_to_heuristic=True,
    )


def list_configs() -> dict[str, GameModelConfig]:
    """List all registered game model configs."""
    return dict(_registry)


# Sentinel values that mean "use fallback strategy, not a model"
_STRATEGY_SENTINELS = {"heuristic", "random", "mock"}


def resolve_model_profile(
    game_type: str,
    task: str,  # "strategy" | "vision" | "chat" | "intent"
    available_profiles: list[str] | None = None,
) -> str | None:
    """Resolve the best model profile for a game+task combination.
    
    Returns profile_id or None (use fallback).
    
    Sentinel values like "heuristic", "random", "mock" in config mean
    "use this fallback strategy, not a model" — they are filtered out
    and return None (no model profile).
    """
    config = get_game_config(game_type)
    
    task_models = {
        "strategy": config.strategy_models,
        "vision": config.vision_models,
        "chat": config.chat_models,
        "intent": config.intent_models,
    }.get(task, [])
    
    if not task_models:
        return None
    
    # Filter out sentinel values — these mean "use fallback, not a model"
    real_models = [m for m in task_models if m not in _STRATEGY_SENTINELS]
    
    if not real_models:
        return None  # only sentinels configured → use heuristic/template fallback
    
    # If we know available profiles, pick the first match
    if available_profiles:
        for model in real_models:
            if model in available_profiles:
                return model
    
    # Otherwise return the first real preference (caller will handle availability)
    return real_models[0] if real_models else None
