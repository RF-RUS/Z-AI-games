"""Extraction guard tests — verify that unsupported extraction paths are blocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_orchestrator.clients import binding_for
from uno_orchestrator.flow_controller import RuntimeSession
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.decision import DecisionExplanation, DecisionResult
from uno_schemas.game import ActionType, LegalAction
from uno_schemas.orchestrator import SessionSpec
from uno_schemas.perception import Observation, ObservationConfidence, UiEvidence
from uno_schemas.session import AdapterType, SessionConfig
from uno_shared.adapter_protocol import GenericActionResult, GenericEvidenceBundle


@pytest.mark.asyncio
async def test_extraction_continues_when_game_state_confidence_zero():
    """When UIA tree has no game state, agent continues with heuristic fallback."""
    orch = SessionOrchestrator()
    observation = Observation(
        observation_id="obs-1", session_id="s", timestamp_ms=1,
        confidence=ObservationConfidence(overall=0.5, game_state=0.0),
    )
    ui = UiEvidence(confidence=0.5, element_tree={"extracted": {}})
    evidence_bundle = GenericEvidenceBundle(
        adapter_id="win-1", session_id="s",
        ui_evidence=ui.model_dump(mode="json"),
    )

    mock_client = AsyncMock()
    mock_client.capture_evidence = AsyncMock(return_value=evidence_bundle)

    mock_registry = MagicMock()
    mock_registry.get_client = MagicMock(return_value=mock_client)

    orch._clients.perceive = AsyncMock(return_value=observation)
    orch._clients.legal_actions = AsyncMock(return_value=[
        LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="d1")
    ])
    orch._clients.decide = AsyncMock(return_value=DecisionResult(
        chosen_action=LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="d1"),
        confidence=0.9, explanation=DecisionExplanation(summary="test"), correlation_id="c1",
    ))
    orch._clients.guard_decision = AsyncMock(return_value={"allowed": True})
    orch._clients.send_bot_message = AsyncMock(return_value=MagicMock())
    orch._clients.apply_action = AsyncMock()
    orch._clients.replay_event = AsyncMock()
    orch._clients.replay_observation = AsyncMock()

    with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=mock_registry):
        spec = SessionSpec(
            config=SessionConfig(adapter_type=AdapterType.WINDOWS, adapter_id="win-1"),
            windows_profile_id="local-mock-uno", automatic=False,
        )
        detail = await orch.create_session_with_game(spec)
        detail.adapter_bindings = [binding_for(AdapterType.WINDOWS, "win-1", "local-mock-uno")]
        orch._sessions[detail.session_id] = RuntimeSession(detail=detail, spec=spec)
        await orch.start(detail.session_id)

        result = await orch.run_tick(detail.session_id)

        assert result.get("extraction_blocked") is not True
        assert "action" in result
        assert detail.metrics.policy_blocks >= 1
        mock_client.execute_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_extraction_allowed_when_game_state_confidence_nonzero():
    """When game_state confidence > 0 (native desktop), execute proceeds normally."""
    orch = SessionOrchestrator()
    observation = Observation(
        observation_id="obs-1", session_id="s", timestamp_ms=1,
        confidence=ObservationConfidence(overall=0.9, game_state=0.85),
    )
    ui = UiEvidence(confidence=0.9, element_tree={"extracted": {"top_card": {"color": "red", "value": "5"}}})
    evidence_bundle = GenericEvidenceBundle(
        adapter_id="win-1", session_id="s",
        ui_evidence=ui.model_dump(mode="json"),
    )
    legal = [LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="d1")]

    mock_client = AsyncMock()
    mock_client.capture_evidence = AsyncMock(return_value=evidence_bundle)
    mock_client.execute_action = AsyncMock(return_value=GenericActionResult(
        success=True, action_type="click_input", duration_ms=1,
    ))

    mock_registry = MagicMock()
    mock_registry.get_client = MagicMock(return_value=mock_client)

    orch._clients.perceive = AsyncMock(return_value=observation)
    orch._clients.legal_actions = AsyncMock(return_value=legal)
    orch._clients.decide = AsyncMock(return_value=DecisionResult(
        chosen_action=legal[0], confidence=0.9,
        explanation=DecisionExplanation(summary="test"), correlation_id="c1",
    ))
    orch._clients.guard_decision = AsyncMock(return_value={"allowed": True})
    orch._clients.apply_action = AsyncMock()
    orch._clients.replay_event = AsyncMock()
    orch._clients.replay_observation = AsyncMock()

    with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=mock_registry):
        spec = SessionSpec(
            config=SessionConfig(adapter_type=AdapterType.WINDOWS, adapter_id="win-1"),
            windows_profile_id="local-mock-uno", automatic=False,
        )
        detail = await orch.create_session_with_game(spec)
        detail.adapter_bindings = [binding_for(AdapterType.WINDOWS, "win-1", "local-mock-uno")]
        orch._sessions[detail.session_id] = RuntimeSession(detail=detail, spec=spec)
        await orch.start(detail.session_id)

        result = await orch.run_tick(detail.session_id)

        assert result.get("extraction_blocked") is not True
        assert "action" in result
        mock_client.execute_action.assert_awaited_once()
