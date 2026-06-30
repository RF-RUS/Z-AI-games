"""Invocation orchestration with safe fallback to mock."""

from __future__ import annotations

from uno_model_runtime.prompts_registry import resolve_prompt
from uno_model_runtime.providers import MockProvider, get_provider
from uno_schemas.model import (
  ModelInvocationRequest,
  ModelInvocationResponse,
  ModelProfile,
  ModelProviderType,
)
from uno_shared.logging import get_logger

logger = get_logger("model-runtime")


async def invoke_with_fallback(profile: ModelProfile, req: ModelInvocationRequest) -> ModelInvocationResponse:
  prompt = req.prompt
  if not prompt:
    resolution = resolve_prompt(
      req.context.use_case,
      req.variables,
      req.prompt_id,
      req.prompt_version,
    )
    prompt = resolution.rendered_prompt
    req.prompt_id = resolution.prompt_id
    req.prompt_version = resolution.version
    if resolution.expected_output_schema:
      req.expect_json = True

  provider = get_provider(profile.provider)
  try:
    resp = await provider.invoke(profile, prompt, req)
    logger.info(
      "model_invoke",
      profile_id=profile.profile_id,
      provider=profile.provider.value,
      use_case=req.context.use_case.value,
      prompt_id=req.prompt_id,
      prompt_version=req.prompt_version,
      latency_ms=resp.latency_ms,
      correlation_id=req.context.correlation_id,
    )
    return resp
  except Exception as exc:
    logger.warning("model_invoke_failed", error=str(exc), profile_id=profile.profile_id)
    if profile.provider != ModelProviderType.MOCK:
      fallback = ModelProfile(
        profile_id=profile.profile_id, display_name="fallback", provider=ModelProviderType.MOCK,
      )
      resp = await MockProvider().invoke(fallback, prompt, req)
      resp.fallback_used = True
      resp.error = str(exc)
      return resp
    raise
