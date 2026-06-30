"""Model runtime and benchmark tests."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from uno_model_runtime.benchmark_runner import load_dataset, run_benchmark
from uno_model_runtime.prompts_registry import resolve_prompt
from uno_model_runtime.providers import MockProvider, _parse_structured
from uno_schemas.model import (
  BenchmarkRunRequest,
  ModelInvocationContext,
  ModelInvocationRequest,
  ModelProfile,
  ModelProviderType,
  ModelUseCase,
)


def test_resolve_chat_intent_prompt():
  r = resolve_prompt(ModelUseCase.CHAT_INTENT, {"message": "hey bot"})
  assert "hey bot" in r.rendered_prompt
  assert r.prompt_id == "chat_intent"


def test_parse_structured_json():
  s = _parse_structured('{"directed_at_bot": true}', True)
  assert s.parse_success and s.parsed["directed_at_bot"]


@pytest.mark.asyncio
async def test_mock_provider_chat_intent():
  profile = ModelProfile(profile_id="mock/test", display_name="t", provider=ModelProviderType.MOCK)
  req = ModelInvocationRequest(
    context=ModelInvocationContext(use_case=ModelUseCase.CHAT_INTENT, correlation_id="c1"),
    variables={"message": "hey bot?"},
    expect_json=True,
  )
  resp = await MockProvider().invoke(profile, "test", req)
  assert resp.structured and resp.structured.parsed["directed_at_bot"]


def test_load_chat_intent_dataset():
  cases = load_dataset("chat_intent")
  assert len(cases) >= 3


@pytest.mark.asyncio
async def test_benchmark_mock_chat_intent():
  profile = ModelProfile(profile_id="mock/uno-assistant", display_name="m", provider=ModelProviderType.MOCK)
  result = await run_benchmark("chat_intent", profile)
  assert result.samples >= 3
  assert result.success_rate > 0


@pytest.mark.contract
def test_invoke_api_contract():
  from uno_model_runtime.api import app
  client = TestClient(app)
  resp = client.post("/invoke", json=ModelInvocationRequest(
    context=ModelInvocationContext(use_case=ModelUseCase.CHAT_INTENT, correlation_id="api-1"),
    profile_id="mock/uno-assistant",
    prompt_id="chat_intent",
    variables={"message": "hey bot what are rules?"},
    expect_json=True,
  ).model_dump(mode="json"))
  assert resp.status_code == 200
  data = resp.json()
  assert data["structured"]["parse_success"]


@pytest.mark.contract
def test_benchmark_api_contract():
  from uno_model_runtime.api import app
  client = TestClient(app)
  resp = client.post("/benchmark/run", json=BenchmarkRunRequest(dataset="chat_intent").model_dump())
  assert resp.status_code == 200
  assert resp.json()["samples"] >= 3


@pytest.mark.asyncio
async def test_openai_provider_with_mock_http():
  from uno_model_runtime.providers import OpenAICompatibleProvider
  profile = ModelProfile(
    profile_id="test/llama", display_name="t", provider=ModelProviderType.LLAMA_CPP_OPENAI,
    base_url="http://fake/v1", model_name="m", supports_json_mode=True,
  )
  req = ModelInvocationRequest(
    context=ModelInvocationContext(use_case=ModelUseCase.CHAT_INTENT, correlation_id="h1"),
    variables={"message": "hey bot"},
    expect_json=True,
  )
  fake_resp = AsyncMock()
  fake_resp.raise_for_status = lambda: None
  fake_resp.json = lambda: {
    "choices": [{"message": {"content": '{"directed_at_bot": true, "reply_required": true, "confidence": 0.9}'}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
  }
  with patch("httpx.AsyncClient.post", return_value=fake_resp):
    provider = OpenAICompatibleProvider(ModelProviderType.LLAMA_CPP_OPENAI)
    resp = await provider.invoke(profile, "prompt", req)
  assert resp.structured.parse_success
