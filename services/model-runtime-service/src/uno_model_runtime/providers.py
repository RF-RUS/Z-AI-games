"""Model provider abstraction — OpenAI-compatible HTTP clients."""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod

import httpx
from uno_schemas.model import (
  ModelInvocationRequest,
  ModelInvocationResponse,
  ModelProfile,
  ModelProviderHealth,
  ModelProviderType,
  StructuredModelOutput,
)


class ModelProvider(ABC):
  provider_type: ModelProviderType

  @abstractmethod
  async def invoke(self, profile: ModelProfile, prompt: str, req: ModelInvocationRequest) -> ModelInvocationResponse: ...

  @abstractmethod
  async def health(self, profile: ModelProfile) -> ModelProviderHealth: ...


def _parse_structured(text: str, expect_json: bool) -> StructuredModelOutput:
  if not expect_json:
    return StructuredModelOutput(raw=text, parse_success=True)
  try:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
      parsed = json.loads(text[start : end + 1])
      return StructuredModelOutput(raw=text, parsed=parsed, parse_success=True)
  except json.JSONDecodeError:
    pass
  return StructuredModelOutput(raw=text, parse_success=False, warnings=["json parse failed"])


class MockProvider(ModelProvider):
  provider_type = ModelProviderType.MOCK

  async def invoke(self, profile: ModelProfile, prompt: str, req: ModelInvocationRequest) -> ModelInvocationResponse:
    start = time.perf_counter()
    use_case = req.context.use_case.value
    text = self._mock_output(use_case, prompt, req)
    structured = _parse_structured(text, req.expect_json)
    return ModelInvocationResponse(
      profile_id=profile.profile_id,
      provider=self.provider_type,
      prompt_id=req.prompt_id,
      prompt_version=req.prompt_version,
      text=text,
      structured=structured,
      confidence=0.85 if structured.parse_success else 0.5,
      latency_ms=int((time.perf_counter() - start) * 1000),
      correlation_id=req.context.correlation_id,
      usage={"prompt_tokens": len(prompt.split()), "completion_tokens": len(text.split())},
    )

  def _mock_output(self, use_case: str, prompt: str, req: ModelInvocationRequest) -> str:
    if use_case == "chat_intent":
      msg = req.variables.get("message", "")
      directed = "bot" in msg.lower() or "@" in msg
      return json.dumps({
        "directed_at_bot": directed,
        "reply_required": directed and "?" in msg,
        "confidence": 0.9 if directed else 0.3,
      })
    if use_case == "explanation":
      action = req.variables.get("action_type", "action")
      card = req.variables.get("card", "")
      return json.dumps({"summary": f"Playing {action} {card}".strip(), "confidence": 0.8})
    if use_case == "policy_advice":
      actions_text = req.variables.get("legal_actions", "")
      lines = [l.strip() for l in actions_text.strip().split("\n") if l.strip()]
      # Pick first play action, or first action overall
      chosen_idx = 0
      for line in lines:
        if "play" in line.lower():
          idx_str = line.split(":")[0].strip()
          if idx_str.isdigit():
            chosen_idx = int(idx_str)
            break
      return json.dumps({
        "action_index": chosen_idx,
        "confidence": 0.8,
        "reasoning": f"Mock AI chose action {chosen_idx} based on available options",
      })
    if use_case == "perception_dispute":
      a = req.variables.get("evidence_a", "")
      b = req.variables.get("evidence_b", "")
      if a.strip().lower() == b.strip().lower():
        return json.dumps({"resolution_class": "agree", "confidence": 0.95})
      return json.dumps({"resolution_class": "insufficient_confidence", "confidence": 0.4})
    if use_case == "chat_reply":
      return json.dumps({"best_index": 0, "confidence": 0.7})
    return json.dumps({"text": f"[mock] {prompt[:120]}"})

  async def health(self, profile: ModelProfile) -> ModelProviderHealth:
    return ModelProviderHealth(provider=self.provider_type, healthy=True, latency_ms=1, model_ids=[profile.profile_id])


class OpenAICompatibleProvider(ModelProvider):
  def __init__(self, provider_type: ModelProviderType) -> None:
    self.provider_type = provider_type

  async def invoke(self, profile: ModelProfile, prompt: str, req: ModelInvocationRequest) -> ModelInvocationResponse:
    start = time.perf_counter()
    base = (profile.base_url or "").rstrip("/")
    api_key = os.getenv(profile.api_key_env, "not-needed")
    body: dict = {
      "model": profile.model_name or profile.profile_id,
      "messages": [{"role": "user", "content": prompt}],
      "max_tokens": req.max_tokens,
      "temperature": req.temperature,
      "stream": False,
    }
    if req.expect_json and profile.supports_json_mode:
      body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=profile.timeout_seconds) as client:
      resp = await client.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=body,
      )
      resp.raise_for_status()
      data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    structured = _parse_structured(text, req.expect_json)
    return ModelInvocationResponse(
      profile_id=profile.profile_id,
      provider=self.provider_type,
      prompt_id=req.prompt_id,
      prompt_version=req.prompt_version,
      text=text,
      structured=structured,
      confidence=0.75 if structured.parse_success else 0.5,
      latency_ms=int((time.perf_counter() - start) * 1000),
      correlation_id=req.context.correlation_id,
      usage={k: int(v) for k, v in usage.items() if isinstance(v, (int, float))},
    )

  async def health(self, profile: ModelProfile) -> ModelProviderHealth:
    base = (profile.base_url or "").rstrip("/")
    start = time.perf_counter()
    try:
      async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{base}/models")
        resp.raise_for_status()
        data = resp.json()
      ids = [m.get("id", "") for m in data.get("data", [])]
      return ModelProviderHealth(
        provider=self.provider_type,
        healthy=True,
        latency_ms=int((time.perf_counter() - start) * 1000),
        model_ids=ids[:10],
      )
    except Exception as exc:
      return ModelProviderHealth(provider=self.provider_type, healthy=False, error=str(exc))


def get_provider(provider_type: ModelProviderType) -> ModelProvider:
  return {
    ModelProviderType.MOCK: MockProvider(),
    ModelProviderType.LLAMA_CPP_OPENAI: OpenAICompatibleProvider(ModelProviderType.LLAMA_CPP_OPENAI),
    ModelProviderType.VLLM_OPENAI: OpenAICompatibleProvider(ModelProviderType.VLLM_OPENAI),
  }[provider_type]
