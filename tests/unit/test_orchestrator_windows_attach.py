"""Orchestrator Windows attach regression tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.orchestrator import AttachAdapterBody, RecoveryConfig, SessionSpec
from uno_schemas.session import AdapterType, SessionConfig
from uno_shared.adapter_protocol import (
  AdapterRetryPolicy,
  GenericAttachRequest,
  GenericAttachResponse,
)

WINDOWS_POLICY = AdapterRetryPolicy(
    max_retries=3, retry_on_transient=True, fallback_to_mock=True,
    fallback_to_manual=True, supports_launch_retry=True, classify_all_permanent=False,
)

NO_RETRY_POLICY = AdapterRetryPolicy(
    max_retries=0, retry_on_transient=False, fallback_to_mock=True,
    fallback_to_manual=True, supports_launch_retry=True, classify_all_permanent=False,
)


def _make_registry_mock(attach_value):
  mock_client = AsyncMock()
  if callable(attach_value):
    mock_client.attach = AsyncMock(side_effect=attach_value)
  else:
    mock_client.attach = AsyncMock(return_value=attach_value)
  mock_client.detach = AsyncMock()
  mock_client.capture_evidence = AsyncMock()
  mock_client.normalize_attach_request = MagicMock(return_value=GenericAttachRequest(
    session_id="mock", profile_id="mock", adapter_type="windows",
  ))
  mock_client.get_retry_policy = MagicMock(return_value=WINDOWS_POLICY)
  mock_registry = MagicMock()
  mock_registry.get_client = MagicMock(return_value=mock_client)
  mock_registry.get_retry_policy = MagicMock(return_value=WINDOWS_POLICY)
  return mock_registry, mock_client


@pytest.mark.asyncio
async def test_do_attach_windows_returns_windows_binding():
  orch = SessionOrchestrator()
  resp = GenericAttachResponse(
    adapter_id="win-adapter-1",
    session_id="sess-1",
    attached=True,
    message="attached",
  )
  mock_registry, mock_client = _make_registry_mock(resp)
  orch._adapter_registry = mock_registry

  body = AttachAdapterBody(
    adapter_type=AdapterType.WINDOWS,
    profile_id="local-mock-uno",
    windows_use_pywinauto=False,
  )
  binding = await orch._do_attach("sess-1", AdapterType.WINDOWS, "local-mock-uno", body)
  assert binding.adapter_type == AdapterType.WINDOWS
  assert binding.adapter_id == "win-adapter-1"
  mock_client.attach.assert_awaited_once()


@pytest.mark.asyncio
async def test_do_attach_windows_raises_when_not_attached():
  orch = SessionOrchestrator()
  resp = GenericAttachResponse(
    adapter_id="win-adapter-2",
    session_id="sess-2",
    attached=False,
    message="window not found",
  )
  mock_registry, mock_client = _make_registry_mock(resp)
  orch._adapter_registry = mock_registry

  body = AttachAdapterBody(adapter_type=AdapterType.WINDOWS, profile_id="local-mock-uno")
  with pytest.raises(RuntimeError, match="window not found"):
    await orch._do_attach("sess-2", AdapterType.WINDOWS, "local-mock-uno", body)


@pytest.mark.asyncio
async def test_orchestrator_forwards_selected_window_handle():
  orch = SessionOrchestrator()
  resp = GenericAttachResponse(
    adapter_id="win-handle",
    session_id="sess-handle",
    attached=True,
    message="attached",
  )
  mock_registry, mock_client = _make_registry_mock(resp)
  orch._adapter_registry = mock_registry

  body = AttachAdapterBody(
    adapter_type=AdapterType.WINDOWS,
    profile_id="real-uno-desktop",
    windows_use_pywinauto=True,
    launch_test_target=True,
    window_handle=123456,
    window_title="UNO Championship",
    window_pid=4242,
  )
  await orch._do_attach("sess-handle", AdapterType.WINDOWS, "real-uno-desktop", body)
  req = mock_client.normalize_attach_request.call_args
  assert req.kwargs["window_handle"] == 123456
  assert req.kwargs["window_title"] == "UNO Championship"
  assert req.kwargs["window_pid"] == 4242


@pytest.mark.asyncio
async def test_orchestrator_skips_launch_for_real_uno_profile():
  orch = SessionOrchestrator()
  resp = GenericAttachResponse(
    adapter_id="real-win",
    session_id="sess-real",
    attached=True,
    message="attached",
  )
  mock_registry, mock_client = _make_registry_mock(resp)
  orch._adapter_registry = mock_registry

  body = AttachAdapterBody(
    adapter_type=AdapterType.WINDOWS,
    profile_id="real-uno-desktop",
    windows_use_pywinauto=True,
    launch_test_target=True,
  )
  await orch._do_attach("sess-real", AdapterType.WINDOWS, "real-uno-desktop", body)
  req = mock_client.normalize_attach_request.call_args
  assert req.kwargs["launch_test_target"] is True
  assert req.kwargs["profile_id"] == "real-uno-desktop"


@pytest.mark.asyncio
async def test_attach_windows_pywinauto_fallback_to_windows_mock():
  orch = SessionOrchestrator()
  call_count = [0]

  async def attach_side_effect(req):
    call_count[0] += 1
    if call_count[0] <= 2:
      return GenericAttachResponse(
        adapter_id=None,
        session_id=req.session_id,
        attached=False,
        message="window not found",
      )
    return GenericAttachResponse(
      adapter_id="win-mock-fallback",
      session_id=req.session_id,
      attached=True,
      message="attached",
    )

  mock_registry, mock_client = _make_registry_mock(attach_side_effect)
  mock_registry.get_retry_policy = MagicMock(return_value=NO_RETRY_POLICY)
  mock_client.get_retry_policy = MagicMock(return_value=NO_RETRY_POLICY)
  orch._adapter_registry = mock_registry

  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WINDOWS, adapter_id="pending"),
    windows_profile_id="local-mock-uno",
    recovery=RecoveryConfig(max_retries=0),
  )
  detail = await orch.create_session_with_game(spec)
  body = AttachAdapterBody(
    adapter_type=AdapterType.WINDOWS,
    profile_id="local-mock-uno",
    windows_use_pywinauto=True,
    launch_test_target=False,
  )
  detail = await orch.attach_adapter(detail.session_id, body)
  binding = detail.adapter_bindings[0]

  assert binding.adapter_type == AdapterType.WINDOWS
  assert binding.adapter_id == "win-mock-fallback"
  assert detail.metrics.fallbacks == 1
  assert detail.metrics.retries == 0
  status = orch.status(detail.session_id)
  assert status.last_recovery is not None
  assert status.last_recovery.action.value == "fallback_mock"
