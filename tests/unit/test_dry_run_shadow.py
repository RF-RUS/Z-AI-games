"""Dry-run safety mode + shadow evaluation tests.

Dry-run: observe→infer→legalize→decide→guard run normally but EXECUTE must never
reach the adapter. Shadow: the opposite strategy runs as a non-binding observer.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_decision.policy import _run_shadow, decide_heuristic
from uno_orchestrator.clients import binding_for
from uno_orchestrator.flow_controller import RuntimeSession
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.decision import DecisionExplanation, DecisionRequest, DecisionResult, ShadowComparison
from uno_schemas.game import ActionType, LegalAction
from uno_schemas.orchestrator import SessionSpec
from uno_schemas.perception import Observation, ObservationConfidence
from uno_schemas.session import AdapterType, SessionConfig
from uno_shared.adapter_protocol import GenericActionResult, GenericEvidenceBundle


def _decision(action: LegalAction) -> DecisionResult:
  return DecisionResult(
    chosen_action=action,
    confidence=0.9,
    explanation=DecisionExplanation(summary="test"),
    correlation_id="c1",
  )


@pytest.mark.asyncio
async def test_dry_run_never_executes():
  """dry_run=True: full pipeline runs, but the adapter never receives the action."""
  orch = SessionOrchestrator()
  observation = Observation(
    observation_id="obs-1", session_id="s", timestamp_ms=1,
    confidence=ObservationConfidence(overall=0.9),
  )
  evidence_bundle = GenericEvidenceBundle(adapter_id="win-1", session_id="s")

  mock_client = AsyncMock()
  mock_client.capture_evidence = AsyncMock(return_value=evidence_bundle)
  mock_client.execute_action = AsyncMock(
    return_value=GenericActionResult(success=True, action_type="draw_card"),
  )
  mock_registry = MagicMock()
  mock_registry.get_client = MagicMock(return_value=mock_client)

  draw = LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="d1")
  orch._clients.perceive = AsyncMock(return_value=observation)
  orch._clients.legal_actions = AsyncMock(return_value=[draw])
  orch._clients.decide = AsyncMock(return_value=_decision(draw))
  orch._clients.guard_decision = AsyncMock(return_value={"allowed": True, "violation": None})
  orch._clients.send_bot_message = AsyncMock(return_value=MagicMock())
  orch._clients.apply_action = AsyncMock()

  with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=mock_registry):
    spec = SessionSpec(config=SessionConfig(
      adapter_type=AdapterType.WINDOWS, adapter_id="win-1", dry_run=True,
    ))
    detail = await orch.create_session_with_game(spec)
    detail.adapter_bindings = [binding_for(AdapterType.WINDOWS, "win-1", "local-mock-uno")]
    orch._sessions[detail.session_id] = RuntimeSession(detail=detail, spec=spec)
    await orch.start(detail.session_id)
    result = await orch.run_tick(detail.session_id)

  assert result.get("dry_run") is True
  assert result["planned_action"]["action_id"] == "d1"
  mock_client.execute_action.assert_not_awaited()


def _shadow_req() -> DecisionRequest:
  actions = [
    LegalAction(action_type=ActionType.PLAY_CARD, player_id="p1", action_id="a1"),
    LegalAction(action_type=ActionType.DRAW_CARD, player_id="p1", action_id="a2"),
  ]
  from uno_perception.merger import build_observation
  return DecisionRequest(
    session_id="s1",
    observation=build_observation("s1"),
    legal_actions=actions,
    strategy_id="heuristic",
    correlation_id="c1",
  )


@pytest.mark.asyncio
async def test_shadow_returns_comparison_without_touching_primary():
  req = _shadow_req()
  primary = decide_heuristic(req)
  comparison = await _run_shadow(req, primary)
  assert isinstance(comparison, ShadowComparison)
  assert comparison.shadow_strategy == "model_assist"
  # Shadow failing (no model runtime up in unit env) must still produce a
  # comparison or None — never an exception that kills the cycle.
  assert comparison is None or isinstance(comparison.agree_with_primary, bool)


@pytest.mark.asyncio
async def test_shadow_failure_is_swallowed():
  req = _shadow_req()
  primary = decide_heuristic(req)
  with patch("httpx.AsyncClient", side_effect=RuntimeError("runtime down")):
    comparison = await _run_shadow(req, primary)
  # Either the heuristic-primary path (no model needed) still worked, or the
  # failure was swallowed — both are acceptable, an exception is not.
  assert comparison is None or isinstance(comparison, ShadowComparison)
