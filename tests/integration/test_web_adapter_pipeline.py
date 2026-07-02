"""Integration: adapter-web evidence -> perception -> decision."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uno_adapter_web.api import app as adapter_app
from uno_decision.api import app as decision_app
from uno_perception.api import app as perception_app
from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterRequest
from uno_schemas.decision import DecisionRequest, StrategyId
from uno_schemas.game import ActionType, LegalAction

FIXTURES = Path(__file__).parent.parent / "fixtures" / "web_adapter"


@pytest.mark.integration
def test_mock_evidence_to_perception():
  a_client = TestClient(adapter_app)
  attach = a_client.post("/attach", json=AttachWebAdapterRequest(
    session_id="int-web", mode=AdapterMode.MOCK, profile_id="local-mock-uno",
  ).model_dump(mode="json"))
  aid = attach.json()["adapter_id"]
  evidence = a_client.get(f"/adapters/{aid}/evidence").json()

  p_client = TestClient(perception_app)
  obs_resp = p_client.post("/perceive", json={
    "session_id": "int-web",
    "dom": evidence["dom_evidence"],
  })
  assert obs_resp.status_code == 200
  obs = obs_resp.json()
  assert obs["confidence"]["overall"] > 0
  assert obs.get("table_state") is not None or obs.get("visible_chat")


@pytest.mark.integration
def test_fixture_file_perception_pipeline():
  meta_path = FIXTURES / "local-mock-uno_meta.json"
  if not meta_path.exists():
    pytest.skip("fixture not captured yet — run scripts/capture-web-fixture.py")

  evidence_path = FIXTURES / "local-mock-uno_dom_evidence.json"
  evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

  p_client = TestClient(perception_app)
  obs = p_client.post("/perceive", json={"session_id": "fixture", "dom": evidence}).json()

  legal = [LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="d1")]
  d_client = TestClient(decision_app)
  dec = d_client.post("/decide", json=DecisionRequest(
    session_id="fixture",
    observation=obs,
    legal_actions=[a.model_dump() for a in legal],
    strategy_id=StrategyId.HEURISTIC,
    correlation_id="int-corr",
  ).model_dump(mode="json")).json()
  assert dec["chosen_action"]["action_type"] == "draw_card"


@pytest.mark.integration
def test_replay_with_artifacts(tmp_path, monkeypatch):
  from uno_replay.api import app as replay_app
  from uno_replay.api import store

  monkeypatch.setattr(store, "base_path", tmp_path)
  monkeypatch.setattr(store, "artifacts_path", tmp_path / "artifacts")
  store.artifacts_path.mkdir(parents=True, exist_ok=True)

  from uno_schemas.adapter_web import (
    ReplayArtifactRef,
    ReplayArtifactType,
  )
  from uno_schemas.game import DomainEvent, EventType

  client = TestClient(replay_app)
  event = DomainEvent(
    event_id="e1", event_type=EventType.CARD_PLAYED, game_id="g1",
    sequence=1, timestamp_ms=0, payload={"player_id": "p1"},
  )
  client.post("/replays/r1/events", json=event.model_dump(mode="json"))
  client.post("/replays/r1/artifacts", json=ReplayArtifactRef(
    artifact_id="a1", artifact_type=ReplayArtifactType.SCREENSHOT, path="/tmp/s.png",
  ).model_dump(mode="json"))

  detail = client.get("/replays/r1/detail").json()
  assert len(detail["events"]) == 1
  assert len(detail["artifacts"]) == 1
