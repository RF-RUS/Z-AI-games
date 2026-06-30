"""Integration: windows evidence -> perception -> decision."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uno_adapter_windows.api import app as win_app
from uno_decision.api import app as decision_app
from uno_perception.api import app as perception_app
from uno_schemas.adapter_windows import AttachWindowsAdapterRequest, WindowsAdapterMode
from uno_schemas.decision import DecisionRequest, StrategyId
from uno_schemas.game import ActionType, LegalAction

FIXTURES = Path(__file__).parent.parent / "fixtures" / "windows_adapter"


@pytest.mark.integration
def test_mock_windows_evidence_to_perception():
  client = TestClient(win_app)
  attach = client.post("/attach", json=AttachWindowsAdapterRequest(
    session_id="int-win", mode=WindowsAdapterMode.MOCK,
  ).model_dump(mode="json"))
  aid = attach.json()["adapter_id"]
  evidence = client.get(f"/adapters/{aid}/evidence").json()

  p = TestClient(perception_app)
  obs = p.post("/perceive", json={"session_id": "int-win", "ui": evidence["ui_evidence"]}).json()
  assert obs["confidence"]["overall"] > 0
  assert obs.get("visible_chat") or obs.get("table_state")


@pytest.mark.integration
def test_fixture_file_pipeline():
  meta_path = FIXTURES / "local-mock-uno_meta.json"
  if not meta_path.exists():
    pytest.skip("run scripts/capture-windows-fixture.py first")
  ui_path = FIXTURES / "local-mock-uno_ui_evidence.json"
  ui = json.loads(ui_path.read_text(encoding="utf-8"))
  p = TestClient(perception_app)
  obs = p.post("/perceive", json={"session_id": "f", "ui": ui}).json()
  legal = [LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="d1")]
  dec = TestClient(decision_app).post("/decide", json=DecisionRequest(
    session_id="f", observation=obs, legal_actions=[a.model_dump() for a in legal],
    strategy_id=StrategyId.HEURISTIC, correlation_id="c1",
  ).model_dump(mode="json")).json()
  assert dec["chosen_action"]["action_type"] == "draw_card"
