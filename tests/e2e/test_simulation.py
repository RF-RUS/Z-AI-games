"""E2E simulation tests with mock adapters."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uno_adapter_windows.api import app as win_app
from uno_chat_intent.api import app as intent_app
from uno_chat_response.api import app as response_app
from uno_policy.api import app as policy_app

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.e2e
def test_mock_windows_uno_round():
  client = TestClient(win_app)
  attach = client.post("/attach", json={
    "session_id": "e2e-win",
    "mode": "mock",
    "profile_id": "local-mock-uno",
  })
  assert attach.status_code == 200
  aid = attach.json()["adapter_id"]
  tree = client.get(f"/adapters/{aid}/ui-tree")
  assert tree.status_code == 200


@pytest.mark.e2e
def test_chat_message_to_reply():
  dom = json.loads((FIXTURES / "dom_snapshot.json").read_text())
  chat_line = dom["chat_messages"][0]

  intent_client = TestClient(intent_app)
  intent_resp = intent_client.post("/detect", json={"raw_lines": [chat_line]})
  assert intent_resp.status_code == 200
  intent = intent_resp.json()
  assert intent["directed_at_bot"]

  reply_client = TestClient(response_app)
  reply_resp = reply_client.post("/reply", json={
    "session_id": "e2e-chat",
    "intent": intent,
    "correlation_id": "e2e-corr",
  })
  assert reply_resp.status_code == 200
  reply = reply_resp.json()

  guard_client = TestClient(policy_app)
  guard_resp = guard_client.post("/guard/chat", json=reply)
  assert guard_resp.status_code == 200
  assert guard_resp.json()["allowed"] is True
