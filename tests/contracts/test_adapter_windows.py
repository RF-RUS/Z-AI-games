"""adapter-windows HTTP contract tests."""

import pytest
from fastapi.testclient import TestClient
from uno_adapter_windows.api import app
from uno_schemas.adapter_windows import (
  AttachWindowsAdapterRequest,
  OperatorPreviewState,
  PreviewFrameKind,
  WindowsActionExecutionRequest,
  WindowsActionType,
  WindowsAdapterMode,
  WindowsAdapterProfile,
)


@pytest.mark.contract
def test_profiles_contract():
  client = TestClient(app)
  resp = client.get("/profiles")
  assert resp.status_code == 200
  assert len([WindowsAdapterProfile.model_validate(p) for p in resp.json()]) >= 1


@pytest.mark.contract
def test_attach_mock_contract():
  client = TestClient(app)
  resp = client.post("/attach", json=AttachWindowsAdapterRequest(
    session_id="win-contract", mode=WindowsAdapterMode.MOCK,
  ).model_dump(mode="json"))
  assert resp.status_code == 200
  data = resp.json()
  assert data["attached"]
  aid = data["adapter_id"]

  tree = client.get(f"/adapters/{aid}/ui-tree")
  assert tree.status_code == 200

  evidence = client.get(f"/adapters/{aid}/evidence")
  assert evidence.status_code == 200
  assert evidence.json()["ui_evidence"]["confidence"] > 0

  action = client.post(f"/adapters/{aid}/actions", json=WindowsActionExecutionRequest(
    action_type=WindowsActionType.CLICK, selector_key="draw",
  ).model_dump(mode="json"))
  assert action.status_code == 200
  client.post(f"/adapters/{aid}/detach")


@pytest.mark.contract
def test_preview_contract():
  client = TestClient(app)
  resp = client.post("/attach", json=AttachWindowsAdapterRequest(
    session_id="win-preview", mode=WindowsAdapterMode.MOCK,
  ).model_dump(mode="json"))
  aid = resp.json()["adapter_id"]
  preview = client.get(f"/adapters/{aid}/preview")
  assert preview.status_code == 200
  state = OperatorPreviewState.model_validate(preview.json())
  assert state.adapter_id == aid
  assert state.status == "ready"
  assert state.frame_kind == PreviewFrameKind.SYNTHETIC
  assert state.live_frame is not None
  assert state.live_frame.data_base64
  assert "not available" not in state.message.lower()
  client.post(f"/adapters/{aid}/detach")


@pytest.mark.contract
def test_pywinauto_check():
  client = TestClient(app)
  resp = client.get("/pywinauto/check")
  assert "available" in resp.json()
