"""Tests for model config resolution."""

from uno_shared.game_plugin import GameModelConfig
from uno_shared.model_config import (
    get_game_config,
    register_game_config,
    resolve_model_profile,
)


def test_resolve_model_profile_heuristic_only():
    """When strategy_models=['heuristic'], resolve returns None (no model)."""
    register_game_config(GameModelConfig(
        game_type="test_heuristic_only",
        strategy_models=["heuristic"],
    ))
    result = resolve_model_profile("test_heuristic_only", "strategy")
    assert result is None  # 'heuristic' is a sentinel, not a model


def test_resolve_model_profile_real_model():
    """When strategy_models=['remote-vllm-poker'], resolve returns the profile."""
    register_game_config(GameModelConfig(
        game_type="test_game",
        strategy_models=["remote-vllm-poker"],
    ))
    result = resolve_model_profile("test_game", "strategy")
    assert result == "remote-vllm-poker"


def test_resolve_model_profile_mixed():
    """When strategy_models=['heuristic', 'remote-vllm-poker'], resolve returns the real model."""
    register_game_config(GameModelConfig(
        game_type="test_mixed",
        strategy_models=["heuristic", "remote-vllm-poker"],
    ))
    result = resolve_model_profile("test_mixed", "strategy")
    assert result == "remote-vllm-poker"


def test_resolve_model_profile_empty():
    """When strategy_models=[], resolve returns None."""
    register_game_config(GameModelConfig(
        game_type="test_empty",
        strategy_models=[],
    ))
    result = resolve_model_profile("test_empty", "strategy")
    assert result is None


def test_resolve_model_profile_unknown_game():
    """Unknown game returns default config with heuristic sentinel → None."""
    result = resolve_model_profile("nonexistent_game", "strategy")
    assert result is None


def test_resolve_model_profile_with_available():
    """When available_profiles is provided, picks first match."""
    register_game_config(GameModelConfig(
        game_type="test_avail",
        strategy_models=["heuristic", "model-a", "model-b"],
    ))
    # Only model-b is available
    result = resolve_model_profile("test_avail", "strategy", available_profiles=["model-b"])
    assert result == "model-b"


def test_resolve_model_profile_with_available_no_match():
    """When available_profiles doesn't match any, returns first real model."""
    register_game_config(GameModelConfig(
        game_type="test_no_match",
        strategy_models=["heuristic", "model-a"],
    ))
    result = resolve_model_profile("test_no_match", "strategy", available_profiles=["model-x"])
    assert result == "model-a"


def test_resolve_model_profile_chat():
    """Chat models resolve correctly."""
    register_game_config(GameModelConfig(
        game_type="test_chat",
        chat_models=["gpt-3.5-turbo"],
    ))
    result = resolve_model_profile("test_chat", "chat")
    assert result == "gpt-3.5-turbo"


def test_resolve_model_profile_vision():
    """Vision models resolve correctly."""
    register_game_config(GameModelConfig(
        game_type="test_vision",
        vision_models=["gpt-4-vision"],
    ))
    result = resolve_model_profile("test_vision", "vision")
    assert result == "gpt-4-vision"


def test_get_game_config_default():
    """Unknown game returns default config."""
    config = get_game_config("nonexistent")
    assert config.game_type == "nonexistent"
    assert config.strategy_models == ["heuristic"]


def test_get_game_config_registered():
    """Registered game returns its config."""
    config = get_game_config("uno")
    assert config.game_type == "uno"
    assert "local/ollama-vlm" in config.strategy_models
