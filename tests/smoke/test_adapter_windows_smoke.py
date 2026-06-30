"""Smoke tests for adapter-windows."""

import pytest
from fastapi.testclient import TestClient
from uno_adapter_windows.api import app
from uno_schemas.adapter_windows import AttachWindowsAdapterRequest


@pytest.mark.smoke
def test_mock_attach_smoke():
  client = TestClient(app)
  resp = client.post("/attach", json=AttachWindowsAdapterRequest(session_id="smoke").model_dump(mode="json"))
  assert resp.json()["attached"]


@pytest.mark.smoke
def test_profile_load_smoke():
  client = TestClient(app)
  assert client.get("/profiles/local-mock-uno").status_code == 200


@pytest.mark.smoke
def test_health_has_windows_details():
  client = TestClient(app)
  h = client.get("/health").json()
  assert "pywinauto_available" in h["details"]
