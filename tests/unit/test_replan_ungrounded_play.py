"""Regression: a play_card whose card is absent from the perceived hand must be
replanned as draw_card — never delivered to the adapter as an ungroundable click.

Session de3856d6: perception read colours fine, the simulator stayed desynced and
demanded blue cards the real hand didn't have; grounding correctly refused, and
the cycle died with "adapter did not perform play_card: target 'play_red_five'
not found in UIA tree". The honest move was always draw.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_orchestrator.flow_controller import FlowController
from uno_schemas.decision import DecisionExplanation, DecisionResult
from uno_schemas.game import ActionType, Card, CardColor, CardValue, LegalAction
from uno_schemas.orchestrator import (
  AdapterBinding,
  FlowState,
  SessionDetail,
  SessionSpec,
)
from uno_schemas.perception import Observation, ObservationConfidence
from uno_schemas.session import AdapterType, SessionConfig, SessionPhase


def _detail() -> SessionDetail:
    spec = SessionSpec(config=SessionConfig(adapter_type=AdapterType.WINDOWS, adapter_id="win-1"))
    return SessionDetail(
        session_id="s-replan",
        flow_state=FlowState.ACTIVE,
        phase=SessionPhase.EXECUTE,
        correlation_id="c1",
        config=spec.config,
        adapter_bindings=[
            AdapterBinding(adapter_type="windows", adapter_id="win-1", profile_id="real-uno-desktop"),
        ],
    )


def _observation(hand: list[dict]) -> Observation:
    return Observation(
        observation_id="o1",
        session_id="s-replan",
        timestamp_ms=0,
        game_type="unknown-game",
        game_state={
            "screen_type": "in_game",
            "hand_cards": hand,
            "top_card": {"color": "green", "value": "0"},
            "regions": [
                {"id": "draw_pile", "type": "button", "x": 336, "y": 151, "width": 142, "height": 106},
            ],
        },
        confidence=ObservationConfidence(overall=0.6),
    )


def _decision(card_color: str, card_value: str) -> DecisionResult:
    return DecisionResult(
        chosen_action=LegalAction(
            action_type=ActionType.PLAY_CARD,
            player_id="p1",
            card=Card(color=CardColor(card_color), value=CardValue(card_value)),
            action_id="phantom-play",
        ),
        confidence=0.8,
        explanation=DecisionExplanation(summary="simulator said so"),
        correlation_id="c1",
    )


class TestReplanUngroundedPlayAsDraw:
    def _flow_and_client(self):
        flow = FlowController()
        client = AsyncMock()
        client.map_action = MagicMock(return_value=MagicMock(selector_key="draw"))
        client.execute_action = AsyncMock(return_value=MagicMock(success=True))
        registry = MagicMock()
        registry.get_client = MagicMock(return_value=client)
        return flow, client, registry

    @pytest.mark.asyncio
    async def test_phantom_play_replanned_to_grounded_draw(self):
        """Chosen blue card, real hand has only red/green/yellow → draw at deck coords."""
        flow, client, registry = self._flow_and_client()
        detail = _detail()
        obs = _observation([
            {"color": "red", "value": "unknown", "center": {"x": 457, "y": 652}},
            {"color": "green", "value": "unknown", "center": {"x": 517, "y": 652}},
            {"color": "yellow", "value": "unknown", "center": {"x": 699, "y": 652}},
        ])
        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            await flow._execute(detail.adapter_bindings[0], _decision("blue", "skip"), detail, "c1", obs, None)

        args, kwargs = client.map_action.call_args
        assert kwargs["action_type"] == "draw_card"
        # Deck region centred: x 336+71=407, y 151+53=204
        assert kwargs["payload"]["draw_target"] == [407, 204]
        assert client.execute_action.await_count == 1

    @pytest.mark.asyncio
    async def test_existing_play_is_not_replanned(self):
        """Chosen green card exists in hand (colour-only) → grounds, no replan."""
        flow, client, registry = self._flow_and_client()
        detail = _detail()
        obs = _observation([
            {"color": "red", "value": "unknown", "center": {"x": 457, "y": 652}},
            {"color": "green", "value": "unknown", "center": {"x": 517, "y": 652}},
        ])
        binding = detail.adapter_bindings[0]
        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            await flow._execute(binding, _decision("green", "unknown"), detail, "c1", obs, None)

        args, kwargs = client.map_action.call_args
        assert kwargs["action_type"] == "play_card"
        assert kwargs["payload"]["card_color"] == "green"

    @pytest.mark.asyncio
    async def test_no_perception_keeps_old_behaviour(self):
        """No screenshot CV data → can't know what's on screen → act as decided (no swap)."""
        flow, client, registry = self._flow_and_client()
        detail = _detail()
        obs = Observation(
            observation_id="o1", session_id="s-replan", timestamp_ms=0,
            confidence=ObservationConfidence(overall=0.1),
        )
        binding = detail.adapter_bindings[0]
        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            await flow._execute(binding, _decision("blue", "skip"), detail, "c1", obs, None)

        args, kwargs = client.map_action.call_args
        assert kwargs["action_type"] == "play_card"
