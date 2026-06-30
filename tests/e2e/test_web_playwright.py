"""Playwright real-mode tests against local deterministic test target."""

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from uno_adapter_web.api import app
from uno_adapter_web.runtime import playwright_available
from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterRequest


@pytest.mark.e2e
def test_mock_web_uno_round():
  client = TestClient(app)
  attach = client.post("/attach", json=AttachWebAdapterRequest(
    session_id="e2e-web", mode=AdapterMode.MOCK, profile_id="local-mock-uno",
  ).model_dump(mode="json"))
  assert attach.status_code == 200
  aid = attach.json()["adapter_id"]
  dom = client.get(f"/adapters/{aid}/dom")
  assert dom.status_code == 200
  assert "top_card" in dom.json()
  client.post(f"/adapters/{aid}/detach")


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(not playwright_available(), reason="Playwright not installed")
async def test_playwright_local_target(web_test_server):
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    attach = await client.post("/attach", json=AttachWebAdapterRequest(
      session_id="e2e-pw",
      mode=AdapterMode.PLAYWRIGHT,
      profile_id="local-mock-uno",
      url=web_test_server,
      headless=True,
    ).model_dump(mode="json"))
    assert attach.status_code == 200
    data = attach.json()
    assert data["attached"] is True, data.get("message")
    aid = data["adapter_id"]

    evidence = (await client.get(f"/adapters/{aid}/evidence")).json()
    assert evidence["dom_snapshot"]["extracted"].get("top_card")
    assert evidence.get("chat_messages")

    await client.post(f"/adapters/{aid}/detach")


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(not playwright_available(), reason="Playwright not installed")
async def test_playwright_full_pipeline(web_test_server):
  from uno_chat_intent.api import app as intent_app
  from uno_chat_response.api import app as response_app
  from uno_perception.api import app as perception_app
  from uno_policy.api import app as policy_app

  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as a:
    attach = await a.post("/attach", json=AttachWebAdapterRequest(
      session_id="e2e-full", mode=AdapterMode.PLAYWRIGHT, profile_id="local-mock-uno", url=web_test_server,
    ).model_dump(mode="json"))
    aid = attach.json()["adapter_id"]
    evidence = (await a.get(f"/adapters/{aid}/evidence")).json()

  p = TestClient(perception_app)
  obs = p.post("/perceive", json={"session_id": "e2e-full", "dom": evidence["dom_evidence"]}).json()

  chat_lines = obs.get("visible_chat") or evidence.get("chat_messages", [])
  assert chat_lines

  intent = TestClient(intent_app).post("/detect", json={"raw_lines": chat_lines}).json()
  assert intent["directed_at_bot"]

  reply = TestClient(response_app).post("/reply", json={
    "session_id": "e2e-full", "intent": intent, "correlation_id": "e2e-chat",
  }).json()
  guard = TestClient(policy_app).post("/guard/chat", json=reply).json()
  assert guard["allowed"] is True

  async with AsyncClient(transport=transport, base_url="http://test") as a:
    await a.post(f"/adapters/{aid}/detach")
