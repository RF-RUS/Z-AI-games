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


def _describe(exc: Exception) -> str:
  """Human-readable exception description that is never empty.

  httpx transport errors (ReadTimeout, ConnectError, RemoteProtocolError...) have
  an EMPTY str(), so logging str(exc) alone produced `model_invoke_failed error=`
  with no clue why the real provider died - and because we then fall back to the
  MOCK provider and return 200 OK, the failure was completely invisible. Always
  include the type, and the target request when httpx attaches one.
  """
  msg = str(exc).strip()
  request = getattr(exc, "request", None)
  target = f" on {request.method} {request.url}" if request is not None else ""
  return f"{type(exc).__name__}{target}: {msg}" if msg else f"{type(exc).__name__}{target}"


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

  # Sampling params the caller left unset come from the PROFILE, not from a
  # schema constant: profiles encode per-model budgets (a thinking VLM needs a
  # much larger completion budget than a text model).
  if req.max_tokens is None:
    req.max_tokens = profile.max_tokens_default

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
    detail = _describe(exc)
    logger.warning(
      "model_invoke_failed",
      error=detail,
      profile_id=profile.profile_id,
      provider=profile.provider.value,
      use_case=req.context.use_case.value,
      has_image=bool(req.image_base64),
      timeout_seconds=profile.timeout_seconds,
    )
    if profile.provider != ModelProviderType.MOCK:
      fallback = ModelProfile(
        profile_id=profile.profile_id, display_name="fallback", provider=ModelProviderType.MOCK,
      )
      resp = await MockProvider().invoke(fallback, prompt, req)
      resp.fallback_used = True
      resp.error = detail
      return resp
    raise
