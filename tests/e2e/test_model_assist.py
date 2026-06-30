"""E2E model-assisted advisory flow (non-canonical)."""

import pytest
from fastapi.testclient import TestClient
from uno_model_runtime.api import app
from uno_schemas.model import ModelInvocationContext, ModelInvocationRequest, ModelUseCase


@pytest.mark.e2e
def test_chat_intent_advisory_e2e():
  client = TestClient(app)
  req = ModelInvocationRequest(
    context=ModelInvocationContext(use_case=ModelUseCase.CHAT_INTENT, correlation_id="e2e-ci-1"),
    profile_id="mock/uno-assistant",
    prompt_id="chat_intent",
    variables={"message": "hey bot, what card should I play?"},
    expect_json=True,
  )
  resp = client.post("/invoke", json=req.model_dump(mode="json"))
  assert resp.status_code == 200
  body = resp.json()
  assert body["structured"]["parse_success"]
  assert body["structured"]["parsed"]["directed_at_bot"] is True
  assert body["provider"] == "mock"
  assert body["prompt_id"] == "chat_intent"


@pytest.mark.e2e
def test_action_explanation_advisory_e2e():
  client = TestClient(app)
  req = ModelInvocationRequest(
    context=ModelInvocationContext(use_case=ModelUseCase.EXPLANATION, correlation_id="e2e-ex-1"),
    profile_id="mock/uno-assistant",
    prompt_id="action_explanation",
    variables={"action_type": "play", "card": "red 5"},
    expect_json=True,
  )
  resp = client.post("/invoke", json=req.model_dump(mode="json"))
  assert resp.status_code == 200
  summary = resp.json()["structured"]["parsed"]["summary"]
  assert "play" in summary.lower()
