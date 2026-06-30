"""Orchestrator web attach regression tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from uno_orchestrator.orchestrator import SessionOrchestrator, WebAttachFailedError
from uno_schemas.orchestrator import AttachAdapterBody, RecoveryConfig, RecoveryMode, SessionSpec
from uno_schemas.session import AdapterType, SessionConfig
from uno_shared.adapter_protocol import (
  AdapterRetryPolicy,
  GenericAttachRequest,
  GenericAttachResponse,
)

WEB_POLICY = AdapterRetryPolicy(
    max_retries=0, retry_on_transient=False, fallback_to_mock=False,
    fallback_to_manual=True, supports_launch_retry=False, classify_all_permanent=True,
)


def _make_registry_mock(attach_return_value):
  mock_client = AsyncMock()
  mock_client.attach = AsyncMock(return_value=attach_return_value)
  mock_client.detach = AsyncMock()
  mock_client.capture_evidence = AsyncMock()
  mock_client.normalize_attach_request = MagicMock(return_value=GenericAttachRequest(
    session_id="mock", profile_id="mock", adapter_type="web",
  ))
  mock_client.get_retry_policy = MagicMock(return_value=WEB_POLICY)
  mock_registry = MagicMock()
  mock_registry.get_client = MagicMock(return_value=mock_client)
  mock_registry.get_retry_policy = MagicMock(return_value=WEB_POLICY)
  return mock_registry, mock_client


@pytest.mark.asyncio
async def test_web_attach_success_binds_web_adapter():
  orch = SessionOrchestrator()
  resp = GenericAttachResponse(
    adapter_id="web-1",
    session_id="sess-web",
    attached=True,
    message="attached",
    extra={},
  )
  mock_registry, mock_client = _make_registry_mock(resp)
  orch._adapter_registry = mock_registry

  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
    web_profile_id="scuffed-uno-web",
    recovery=RecoveryConfig(max_retries=0),
  )
  detail = await orch.create_session_with_game(spec)
  body = AttachAdapterBody(adapter_type=AdapterType.WEB, profile_id="scuffed-uno-web")
  detail = await orch.attach_adapter(detail.session_id, body)

  assert len(detail.adapter_bindings) == 1
  assert detail.adapter_bindings[0].adapter_type == AdapterType.WEB
  assert detail.adapter_bindings[0].adapter_id == "web-1"
  assert detail.adapter_bindings[0].profile_id == "scuffed-uno-web"
  mock_client.attach.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_attach_failure_does_not_fallback_to_mock():
  orch = SessionOrchestrator()
  resp = GenericAttachResponse(
    adapter_id=None,
    session_id="sess-web-fail",
    attached=False,
    message="Playwright startup failed at stage=page_goto",
    extra={"startup_diagnostics": {"failed_stage": "page_goto", "error_message": "Playwright startup failed at stage=page_goto (60000ms): timeout", "stage_timings_ms": {"browser_launch": 1200, "context_page": 80, "page_goto": 60000}, "log_path": "artifacts/sess/startup-failure-page_goto.json"}},
  )
  mock_registry, mock_client = _make_registry_mock(resp)
  orch._adapter_registry = mock_registry

  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
    web_profile_id="scuffed-uno-web",
    recovery=RecoveryConfig(max_retries=0, fallback_to_mock=True),
  )
  detail = await orch.create_session_with_game(spec)
  body = AttachAdapterBody(adapter_type=AdapterType.WEB, profile_id="scuffed-uno-web")

  with pytest.raises(WebAttachFailedError, match="page_goto"):
    await orch.attach_adapter(detail.session_id, body)

  refreshed = orch.get_session(detail.session_id)
  assert refreshed is not None
  assert refreshed.adapter_bindings == []
  assert refreshed.error is not None
  assert "page_goto" in refreshed.error
  assert refreshed.attach_startup_diagnostics is not None
  assert refreshed.attach_startup_diagnostics.failed_stage == "page_goto"
  assert refreshed.metrics.fallbacks == 0
  assert refreshed.metrics.retries == 0
  status = orch.status(detail.session_id)
  assert status.last_recovery is not None
  assert status.last_recovery.action == RecoveryMode.STOP
  assert status.attach_startup_diagnostics is not None
  assert status.attach_startup_diagnostics.failed_stage == "page_goto"


@pytest.mark.asyncio
async def test_web_attach_uses_playwright_mode_not_mock():
  orch = SessionOrchestrator()
  resp = GenericAttachResponse(
    adapter_id="web-2",
    session_id="sess-web-mode",
    attached=True,
    message="attached",
  )
  mock_registry, mock_client = _make_registry_mock(resp)
  orch._adapter_registry = mock_registry

  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
    web_profile_id="scuffed-uno-web",
  )
  detail = await orch.create_session_with_game(spec)
  await orch.attach_adapter(
    detail.session_id,
    AttachAdapterBody(adapter_type=AdapterType.WEB, profile_id="scuffed-uno-web"),
  )
  req = mock_client.normalize_attach_request.call_args
  assert req.kwargs["profile_id"] == "scuffed-uno-web"
  assert req.kwargs["target_url"] is None


@pytest.mark.asyncio
async def test_web_attach_passes_target_url_when_provided():
  orch = SessionOrchestrator()
  resp = GenericAttachResponse(
    adapter_id="web-3",
    session_id="sess-url",
    attached=True,
    message="attached",
  )
  mock_registry, mock_client = _make_registry_mock(resp)
  orch._adapter_registry = mock_registry

  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
    web_profile_id="scuffed-uno-web",
  )
  detail = await orch.create_session_with_game(spec)
  await orch.attach_adapter(
    detail.session_id,
    AttachAdapterBody(
      adapter_type=AdapterType.WEB,
      profile_id="scuffed-uno-web",
      target_url="https://scuffeduno.online/",
    ),
  )
  req = mock_client.normalize_attach_request.call_args
  assert req.kwargs["target_url"] == "https://scuffeduno.online/"
