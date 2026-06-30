"""Smoke tests for adapter-web modes."""

import pytest
from fastapi.testclient import TestClient
from uno_adapter_web.api import app
from uno_adapter_web.runtime import playwright_available
from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterRequest


@pytest.mark.smoke
def test_adapter_web_mock_mode():
  client = TestClient(app)
  resp = client.post("/attach", json=AttachWebAdapterRequest(
    session_id="smoke", mode=AdapterMode.MOCK,
  ).model_dump(mode="json"))
  assert resp.json()["attached"] is True


@pytest.mark.smoke
def test_sample_profile_loads():
  client = TestClient(app)
  resp = client.get("/profiles/local-mock-uno")
  assert resp.status_code == 200
  assert resp.json()["profile_id"] == "local-mock-uno"


@pytest.mark.smoke
def test_playwright_deps_check():
  client = TestClient(app)
  resp = client.get("/playwright/check")
  data = resp.json()
  assert data["available"] == playwright_available()
  assert "local-mock-uno" in data["profiles"]
