"""Windows session tick progression after attach fallback."""

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
from uno_shared.adapter_registry import GenericAdapterClient


def test_windows_action_mapping_draw_card():
  client = GenericAdapterClient("windows", "http://noop")
  req = client.map_action("draw_card")
  assert req.selector_key == "draw"
  assert req.domain_action == "draw_card"
  assert req.action_type == "click_input"


def test_windows_action_mapping_play_card():
  client = GenericAdapterClient("windows", "http://noop")
  req = client.map_action("play_card")
  assert req.selector_key == "play_red_five"
  assert req.domain_action == "play_card"


@pytest.mark.asyncio
async def test_windows_fallback_session_tick_completes_execute():
  orch = SessionOrchestrator()
  legal = [LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="draw-1")]
  chosen = legal[0]
  observation = Observation(
    observation_id="obs-1",
    session_id="s",
    timestamp_ms=1,
    confidence=ObservationConfidence(overall=0.9, game_state=0.85),
  )
  decision = DecisionResult(
    chosen_action=chosen,
    confidence=0.9,
    explanation=DecisionExplanation(summary="test"),
    correlation_id="c1",
  )
  ui = UiEvidence(confidence=0.9, element_tree={"extracted": {}})

  evidence_bundle = GenericEvidenceBundle(
    adapter_id="win-1",
    session_id="s",
    ui_evidence=ui.model_dump(mode="json"),
  )

  mock_adapter_client = AsyncMock()
  mock_adapter_client.capture_evidence = AsyncMock(return_value=evidence_bundle)
  mock_adapter_client.execute_action = AsyncMock(return_value=GenericActionResult(
    success=True,
    action_type="click_input",
    duration_ms=1,
  ))

  mock_registry = MagicMock()
  mock_registry.get_client = MagicMock(return_value=mock_adapter_client)

  orch._clients.perceive = AsyncMock(return_value=observation)
  orch._clients.legal_actions = AsyncMock(return_value=legal)
  orch._clients.decide = AsyncMock(return_value=decision)
  orch._clients.guard_decision = AsyncMock(return_value={"allowed": True, "violation": None})
  orch._clients.apply_action = AsyncMock(return_value={"ok": True})
  orch._clients.replay_event = AsyncMock()
  orch._clients.replay_observation = AsyncMock()

  with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=mock_registry):
    spec = SessionSpec(
      config=SessionConfig(adapter_type=AdapterType.WINDOWS, adapter_id="win-1"),
      windows_profile_id="local-mock-uno",
      automatic=False,
    )
    detail = await orch.create_session_with_game(spec)
    detail.adapter_bindings = [binding_for(AdapterType.WINDOWS, "win-1", "local-mock-uno")]
    orch._sessions[detail.session_id] = RuntimeSession(detail=detail, spec=spec)
    await orch.start(detail.session_id)

    result = await orch.run_tick(detail.session_id)

    assert "action" in result
    assert result.get("error") is None
    assert detail.metrics.total_steps == 1
    assert detail.metrics.policy_blocks == 0
    assert detail.error is None
    step_names = [s.step_name.value for s in orch.get_steps(detail.session_id)]
    assert "execute" in step_names
    assert "record" in step_names
    mock_adapter_client.execute_action.assert_awaited_once()
