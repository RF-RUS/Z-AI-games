"""Trace propagation + service metrics + observability aggregation tests."""

import importlib


def _policy_app():
  from uno_policy.api import app
  return app


def test_trace_header_bound_into_logs_and_returned():
  from fastapi.testclient import TestClient
  client = TestClient(_policy_app())
  resp = client.get("/health", headers={"X-Trace-Id": "trace-abc"})
  assert resp.headers.get("X-Trace-Id") == "trace-abc"


def test_trace_id_generated_when_absent():
  from fastapi.testclient import TestClient
  client = TestClient(_policy_app())
  resp = client.get("/health")
  assert len(resp.headers.get("X-Trace-Id", "")) == 16


def test_local_metrics_endpoint_counts_requests():
  from fastapi.testclient import TestClient
  client = TestClient(_policy_app())
  client.post("/guard/chat", json={"text": "hi", "correlation_id": "c1"})
  metrics = client.get("/metrics").json()
  assert metrics["service"] == "policy-guard"
  assert metrics["total_requests"] >= 1
  # /metrics and /health themselves must not pollute their own counts
  assert all(e["path"] not in ("/metrics", "/health") for e in metrics["recent"])


def test_kill_switch_blocks_all_actions(monkeypatch):
  from fastapi.testclient import TestClient
  from uno_schemas.decision import DecisionExplanation, DecisionResult
  from uno_schemas.game import ActionType, LegalAction

  action = LegalAction(action_type=ActionType.DRAW_CARD, player_id="p1", action_id="a1")
  decision = DecisionResult(
    chosen_action=action, confidence=0.9,
    explanation=DecisionExplanation(summary="t"), correlation_id="c1",
  )
  body = {
    "decision": decision.model_dump(mode="json"),
    "legal_actions": [action.model_dump(mode="json")],
    "min_confidence": 0.3,
  }

  monkeypatch.setenv("UNO_KILL_SWITCH", "1")
  from uno_policy import api as policy_api
  importlib.reload(policy_api)
  try:
    client = TestClient(policy_api.app)
    assert client.get("/guard/kill-switch").json()["active"] is True
    resp = client.post("/guard/decision", json=body)
    assert resp.json()["allowed"] is False
    assert resp.json()["violation"]["violation_type"] == "kill_switch"

    released = client.post("/guard/kill-switch", json={"active": False, "reason": "test done"})
    assert released.json()["active"] is False
    assert client.post("/guard/decision", json=body).json()["allowed"] is True
  finally:
    monkeypatch.delenv("UNO_KILL_SWITCH")
    importlib.reload(policy_api)


def test_observability_aggregates_step_reports():
  from fastapi.testclient import TestClient
  from uno_observability.api import app

  client = TestClient(app)
  for i in range(3):
    r = client.post("/metrics/report", json={
      "service": "perception-service", "path": "/perceive",
      "status": 200, "latency_ms": float(i + 1), "correlation_id": "tr1",
    })
    assert r.json() == {"stored": True}
  # /metrics is the per-service snapshot (ServiceApp); the platform-wide
  # aggregate of all reported steps lives at /metrics/summary.
  snap = client.get("/metrics").json()
  assert snap["service"] == "observability-service"
  m = client.get("/metrics/summary").json()
  assert m["total_reported_steps"] >= 3
  assert m["by_status"].get("2xx", 0) >= 3
  assert "perception-service" in m["latency_by_service"]

  trace = client.get("/traces/tr1").json()
  assert trace["correlation_id"] == "tr1"
  assert len(trace["steps"]) >= 3
