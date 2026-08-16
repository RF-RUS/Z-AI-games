"""Decision and policy guard tests."""


import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_decision.policy import _extract_json_object, decide_heuristic, decide_model
from uno_perception.merger import build_observation
from uno_policy.guard import validate_chat_reply, validate_decision
from uno_schemas.chat import ChatReply
from uno_schemas.decision import DecisionExplanation, DecisionRequest, DecisionResult, StrategyId
from uno_schemas.game import ActionType, LegalAction
from uno_schemas.perception import Observation, ObservationConfidence


def _make_request(actions):
  return DecisionRequest(
    session_id="s1",
    observation=Observation(
      observation_id="o1",
      session_id="s1",
      timestamp_ms=0,
      confidence=ObservationConfidence(overall=0.9),
    ),
    legal_actions=actions,
    correlation_id="c1",
  )


def test_heuristic_prefers_play_over_draw():
  actions = [
    LegalAction(action_type=ActionType.DRAW_CARD, player_id="p1", action_id="a1"),
    LegalAction(
      action_type=ActionType.PLAY_CARD,
      player_id="p1",
      card=None,
      action_id="a2",
    ),
  ]
  # Fix card for play action
  from uno_schemas.game import Card, CardColor, CardValue
  actions[1].card = Card(color=CardColor.RED, value=CardValue.FIVE)
  result = decide_heuristic(_make_request(actions))
  assert result.chosen_action.action_type == ActionType.PLAY_CARD


def test_policy_blocks_illegal():
  legal = [LegalAction(action_type=ActionType.DRAW_CARD, player_id="p1", action_id="a1")]
  decision = DecisionResult(
    chosen_action=LegalAction(action_type=ActionType.PASS, player_id="p1", action_id="bad"),
    confidence=0.9,
    explanation=DecisionExplanation(summary="test"),
    correlation_id="c1",
  )
  allowed, violation = validate_decision(decision, legal)
  assert not allowed
  assert violation is not None


def test_chat_policy_blocks_leak():
  reply = ChatReply(text="My hand has a red 5 hidden", correlation_id="c1")
  allowed, violations = validate_chat_reply(reply, "c1")
  assert not allowed
  assert any("leak" in v for v in violations)


# ── _extract_json_object ──────────────────────────────────────────────────────

def test_policy_extract_json_fenced_block():
  text = '```json\n{"action_index": 1, "confidence": 0.8}\n```'
  result = _extract_json_object(text)
  assert result is not None
  assert json.loads(result)["action_index"] == 1


def test_policy_extract_json_fenced_no_tag():
  text = '```\n{"action_index": 0}\n```'
  result = _extract_json_object(text)
  assert result is not None
  assert json.loads(result)["action_index"] == 0


def test_policy_extract_json_reasoning_preamble():
  text = (
    "Let me think about the best move here.\n"
    '{"action_index": 2, "confidence": 0.9, "reasoning": "wild card best"}'
  )
  result = _extract_json_object(text)
  assert result is not None
  parsed = json.loads(result)
  assert parsed["action_index"] == 2
  assert parsed["reasoning"] == "wild card best"


def test_policy_extract_json_no_json_returns_none():
  assert _extract_json_object("") is None
  assert _extract_json_object("no braces here") is None
  assert _extract_json_object(None) is None  # type: ignore[arg-type]


def test_policy_extract_json_nested_objects():
  """Brace counter must not false-close on nested objects."""
  text = '{"action_index": 0, "meta": {"source": "policy"}}'
  result = _extract_json_object(text)
  assert result is not None
  assert json.loads(result)["meta"]["source"] == "policy"


# ── decide_model parse rescue ─────────────────────────────────────────────────

def _make_model_req(n_actions: int = 2) -> DecisionRequest:
  actions = [
    LegalAction(action_type=ActionType.PLAY_CARD, player_id="p1", action_id=f"a{i}")
    for i in range(n_actions)
  ]
  return DecisionRequest(
    session_id="s1",
    observation=build_observation("s1"),
    legal_actions=actions,
    strategy_id=StrategyId.MODEL_ASSIST,
    correlation_id="c1",
  )


def _patch_runtime(text: str, structured: dict | None = None):
  """Patch httpx.AsyncClient to return a controlled model-runtime-service payload."""
  mock_resp = MagicMock()
  mock_resp.raise_for_status = MagicMock()
  mock_resp.json.return_value = {
    "text": text,
    "structured": structured,
    "model_id": "test-model",
  }
  mock_client = AsyncMock()
  mock_client.post = AsyncMock(return_value=mock_resp)
  ctx = MagicMock()
  ctx.__aenter__ = AsyncMock(return_value=mock_client)
  ctx.__aexit__ = AsyncMock(return_value=False)
  return patch("httpx.AsyncClient", return_value=ctx)


@pytest.fixture(autouse=True)
def mock_tracker(monkeypatch):
  import uno_shared.model_observability as obs_mod
  tracker = MagicMock()
  tracker.start.return_value = MagicMock()
  monkeypatch.setattr(obs_mod, "get_usage_tracker", lambda: tracker)
  return tracker


def test_decide_model_rescues_fenced_json():
  """Fenced JSON in model text → rescue parses it, returns model decision not heuristic."""
  req = _make_model_req(2)
  fenced = '```json\n{"action_index": 1, "confidence": 0.85, "reasoning": "play"}\n```'
  with _patch_runtime(text=fenced):
    result = asyncio.run(decide_model(req))
  assert result.explanation.model_used is True
  assert result.chosen_action == req.legal_actions[1]


def test_decide_model_rescues_preamble_json():
  """Preamble-wrapped JSON in model text → rescue extracts and parses it."""
  req = _make_model_req(2)
  preamble = (
    "After careful analysis I recommend:\n"
    '{"action_index": 0, "confidence": 0.75, "reasoning": "safe"}'
  )
  with _patch_runtime(text=preamble):
    result = asyncio.run(decide_model(req))
  assert result.explanation.model_used is True
  assert result.chosen_action == req.legal_actions[0]


def test_decide_model_falls_back_on_unrecoverable():
  """Unrecoverable garbage text → heuristic fallback, model_used=False."""
  req = _make_model_req(2)
  with _patch_runtime(text="totally unparseable @@##$$"):
    result = asyncio.run(decide_model(req))
  assert result.explanation.model_used is False
  assert result.chosen_action in req.legal_actions
