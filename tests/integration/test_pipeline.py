"""Integration: perception -> decision -> guard flow."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from uno_decision.api import app as decision_app
from uno_perception.api import app as perception_app
from uno_policy.api import app as policy_app
from uno_schemas.decision import DecisionRequest, StrategyId
from uno_schemas.game import ActionType, LegalAction

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_perception_decision_guard_pipeline():
  dom_data = json.loads((FIXTURES / "dom_snapshot.json").read_text())

  p_client = TestClient(perception_app)
  obs_resp = p_client.post("/perceive", json={
    "session_id": "int-1",
    "dom": {"snapshot": dom_data, "confidence": 0.9},
  })
  assert obs_resp.status_code == 200
  observation = obs_resp.json()

  legal = [LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="draw-1")]

  d_client = TestClient(decision_app)
  dec_resp = d_client.post("/decide", json=DecisionRequest(
    session_id="int-1",
    observation=observation,
    legal_actions=[a.model_dump() for a in legal],
    strategy_id=StrategyId.HEURISTIC,
    correlation_id="corr-1",
  ).model_dump(mode="json"))
  assert dec_resp.status_code == 200
  decision = dec_resp.json()

  g_client = TestClient(policy_app)
  guard_resp = g_client.post("/guard/decision", json={
    "decision": decision,
    "legal_actions": [a.model_dump() for a in legal],
    "min_confidence": 0.1,
  })
  assert guard_resp.status_code == 200
  assert guard_resp.json()["allowed"] is True
