"""Windows adapter e2e tests."""

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from uno_adapter_windows.api import app
from uno_adapter_windows.runtime import is_windows, pywinauto_available
from uno_schemas.adapter_windows import AttachWindowsAdapterRequest, WindowsAdapterMode


@pytest.mark.e2e
def test_mock_windows_round():
  client = TestClient(app)
  attach = client.post("/attach", json=AttachWindowsAdapterRequest(
    session_id="e2e-win", mode=WindowsAdapterMode.MOCK,
  ).model_dump(mode="json"))
  assert attach.json()["attached"]
  aid = attach.json()["adapter_id"]
  assert client.get(f"/adapters/{aid}/evidence").json()["chat_messages"]
  client.post(f"/adapters/{aid}/detach")


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(not is_windows() or not pywinauto_available(), reason="Windows+pywinauto required")
async def test_pywinauto_local_target(windows_test_app):
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    attach = await client.post("/attach", json=AttachWindowsAdapterRequest(
      session_id="e2e-pw-win",
      mode=WindowsAdapterMode.PYWINAUTO,
      profile_id="local-mock-uno",
      window_title="UNO Mock Test Target",
    ).model_dump(mode="json"))
    data = attach.json()
    if not data["attached"]:
      pytest.skip(f"window not attached: {data.get('message')}")
    aid = data["adapter_id"]
    evidence = (await client.get(f"/adapters/{aid}/evidence")).json()
    assert evidence["window_snapshot"]["window_title"]
    await client.post(f"/adapters/{aid}/detach")


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(not is_windows() or not pywinauto_available(), reason="Windows+pywinauto required")
async def test_pywinauto_chat_pipeline(windows_test_app):
  from uno_chat_intent.api import app as intent_app
  from uno_perception.api import app as perception_app

  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    attach = await client.post("/attach", json=AttachWindowsAdapterRequest(
      session_id="e2e-chat-win", mode=WindowsAdapterMode.PYWINAUTO, profile_id="local-mock-uno",
      window_title="UNO Mock Test Target",
    ).model_dump(mode="json"))
    if not attach.json()["attached"]:
      pytest.skip("target window not found")
    aid = attach.json()["adapter_id"]
    evidence = (await client.get(f"/adapters/{aid}/evidence")).json()

  obs = TestClient(perception_app).post("/perceive", json={
    "session_id": "e2e-chat-win", "ui": evidence["ui_evidence"],
  }).json()
  chat = obs.get("visible_chat") or evidence.get("chat_messages", [])
  if not chat:
    pytest.skip("no chat evidence from UIA tree (sparse tree)")
  intent = TestClient(intent_app).post("/detect", json={"raw_lines": chat}).json()
  assert intent["directed_at_bot"]

  async with AsyncClient(transport=transport, base_url="http://test") as client:
    await client.post(f"/adapters/{aid}/detach")
