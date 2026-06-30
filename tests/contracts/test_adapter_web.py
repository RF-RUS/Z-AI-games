"""adapter-web HTTP contract tests."""

import pytest
from fastapi.testclient import TestClient
from uno_adapter_web.api import app
from uno_schemas.adapter_web import (
  ActionExecutionRequest,
  AdapterMode,
  AttachWebAdapterRequest,
  WebActionType,
  WebAdapterProfile,
)


@pytest.mark.contract
def test_profiles_contract():
  client = TestClient(app)
  resp = client.get("/profiles")
  assert resp.status_code == 200
  profiles = [WebAdapterProfile.model_validate(p) for p in resp.json()]
  assert len(profiles) >= 1


@pytest.mark.contract
def test_attach_mock_contract():
  client = TestClient(app)
  resp = client.post("/attach", json=AttachWebAdapterRequest(
    session_id="contract-1",
    mode=AdapterMode.MOCK,
    profile_id="local-mock-uno",
  ).model_dump(mode="json"))
  assert resp.status_code == 200
  data = resp.json()
  assert data["attached"] is True
  assert data["mode"] == "mock"
  aid = data["adapter_id"]

  dom = client.get(f"/adapters/{aid}/dom")
  assert dom.status_code == 200
  assert "top_card" in dom.json()

  evidence = client.get(f"/adapters/{aid}/evidence")
  assert evidence.status_code == 200
  assert evidence.json()["dom_evidence"]["confidence"] > 0

  action = client.post(f"/adapters/{aid}/actions", json=ActionExecutionRequest(
    action_type=WebActionType.CLICK,
    selector="[data-testid='btn-draw']",
  ).model_dump(mode="json"))
  assert action.status_code == 200
  assert action.json()["success"] is True

  client.post(f"/adapters/{aid}/detach")


@pytest.mark.contract
def test_playwright_check_contract():
  client = TestClient(app)
  resp = client.get("/playwright/check")
  assert resp.status_code == 200
  assert "available" in resp.json()
