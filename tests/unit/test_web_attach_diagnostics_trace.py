"""Web attach diagnostics propagation across orchestrator checkpoints."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from uno_orchestrator.orchestrator import SessionOrchestrator, WebAttachFailedError
from uno_orchestrator.web_attach_trace import parse_attach_web_http_response
from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterResponse, WebStartupDiagnostics
from uno_schemas.orchestrator import AttachAdapterBody, RecoveryConfig, SessionSpec
from uno_schemas.session import AdapterType, SessionConfig
from uno_shared.adapter_protocol import AdapterRetryPolicy, GenericAttachResponse

WEB_POLICY = AdapterRetryPolicy(
    max_retries=0, retry_on_transient=False, fallback_to_mock=False,
    fallback_to_manual=True, supports_launch_retry=False, classify_all_permanent=True,
)


def _make_web_mock_registry(client):
  mock_registry = MagicMock()
  mock_registry.get_client = MagicMock(return_value=client)
  mock_registry.get_retry_policy = MagicMock(return_value=WEB_POLICY)
  return mock_registry


def test_parse_attach_web_http_response_reads_failed_attach_body():
  body = AttachWebAdapterResponse(
    adapter_id=None,
    session_id="sess-1",
    attached=False,
    mode=AdapterMode.PLAYWRIGHT,
    profile_id="scuffed-uno-web",
    url="https://scuffeduno.online/",
    message="Playwright startup failed at stage=page_goto (60000ms): timeout",
    startup_diagnostics=WebStartupDiagnostics(
      failed_stage="page_goto",
      error_message="Playwright startup failed at stage=page_goto (60000ms): timeout",
      stage_timings_ms={"page_goto": 60000},
    ),
  ).model_dump_json()

  parsed = parse_attach_web_http_response(body)

  assert parsed is not None
  assert parsed.attached is False
  assert parsed.startup_diagnostics is not None
  assert parsed.startup_diagnostics.failed_stage == "page_goto"


def test_parse_attach_web_http_response_extracts_nested_diagnostics_from_partial_json():
  body = """
  {
    "adapter_id": null,
    "session_id": "sess-2",
    "attached": false,
    "mode": "playwright",
    "profile_id": "scuffed-uno-web",
    "url": "https://scuffeduno.online/",
    "message": "failed",
    "startup_diagnostics": {
      "failed_stage": "browser_launch",
      "error_message": "launch failed",
      "stage_timings_ms": {"browser_launch": 1200}
    }
  }
  """

  parsed = parse_attach_web_http_response(body)

  assert parsed is not None
  assert parsed.startup_diagnostics is not None
  assert parsed.startup_diagnostics.failed_stage == "browser_launch"


@pytest.mark.asyncio
async def test_clients_attach_web_returns_structured_failure_without_http_error():
  from uno_orchestrator.clients import ServiceClients

  class FakeResponse:
    status_code = 500
    text = AttachWebAdapterResponse(
      adapter_id=None,
      session_id="sess-3",
      attached=False,
      mode=AdapterMode.PLAYWRIGHT,
      profile_id="scuffed-uno-web",
      url="https://scuffeduno.online/",
      message="Playwright startup failed at stage=page_goto (60000ms): timeout",
      startup_diagnostics=WebStartupDiagnostics(
        failed_stage="page_goto",
        error_message="Playwright startup failed at stage=page_goto (60000ms): timeout",
      ),
    ).model_dump_json()

    def raise_for_status(self):
      raise httpx.HTTPStatusError("500", request=httpx.Request("POST", "http://test/attach"), response=httpx.Response(500))

  class FakeClient:
    async def __aenter__(self):
      return self

    async def __aexit__(self, *args):
      return False

    async def post(self, *args, **kwargs):
      return FakeResponse()

  clients = ServiceClients()
  clients.attach_web = ServiceClients.attach_web.__get__(clients, ServiceClients)
  import uno_orchestrator.clients as clients_module

  original_client = clients_module.httpx.AsyncClient
  clients_module.httpx.AsyncClient = lambda **kwargs: FakeClient()
  try:
    resp = await clients.attach_web(
      __import__("uno_schemas.adapter_web", fromlist=["AttachWebAdapterRequest"]).AttachWebAdapterRequest(
        session_id="sess-3",
        profile_id="scuffed-uno-web",
        mode=AdapterMode.PLAYWRIGHT,
      )
    )
  finally:
    clients_module.httpx.AsyncClient = original_client

  assert resp.attached is False
  assert resp.startup_diagnostics is not None
  assert resp.startup_diagnostics.failed_stage == "page_goto"


@pytest.mark.asyncio
async def test_web_attach_http_error_does_not_clear_existing_diagnostics():
  orch = SessionOrchestrator()
  existing = WebStartupDiagnostics(
    failed_stage="readiness_wait",
    error_message="Playwright startup failed at stage=readiness_wait (5000ms): selector missing",
    stage_timings_ms={"readiness_wait": 5000},
  )
  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
    web_profile_id="scuffed-uno-web",
    recovery=RecoveryConfig(max_retries=0),
  )
  detail = await orch.create_session_with_game(spec)
  detail.attach_startup_diagnostics = existing

  mock_client = AsyncMock()
  mock_client.attach = AsyncMock(side_effect=httpx.ConnectError("All connection attempts failed"))
  mock_client.detach = AsyncMock()
  mock_registry = _make_web_mock_registry(mock_client)
  orch._adapter_registry = mock_registry

  with pytest.raises(httpx.ConnectError):
    await orch.attach_adapter(
      detail.session_id,
      AttachAdapterBody(adapter_type=AdapterType.WEB, profile_id="scuffed-uno-web"),
    )

  refreshed = orch.get_session(detail.session_id)
  assert refreshed is not None
  assert refreshed.attach_startup_diagnostics is not None
  assert refreshed.attach_startup_diagnostics.failed_stage == "readiness_wait"


@pytest.mark.asyncio
async def test_failed_web_attach_persists_diagnostics_to_status():
  orch = SessionOrchestrator()
  resp = GenericAttachResponse(
    adapter_id=None,
    session_id="sess-status",
    attached=False,
    message="Playwright startup failed at stage=page_goto",
    extra={"startup_diagnostics": {"failed_stage": "page_goto", "error_message": "Playwright startup failed at stage=page_goto (60000ms): timeout", "stage_timings_ms": {"page_goto": 60000}}},
  )
  mock_client = AsyncMock()
  mock_client.attach = AsyncMock(return_value=resp)
  mock_client.detach = AsyncMock()
  mock_registry = _make_web_mock_registry(mock_client)
  orch._adapter_registry = mock_registry

  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
    web_profile_id="scuffed-uno-web",
    recovery=RecoveryConfig(max_retries=0),
  )
  detail = await orch.create_session_with_game(spec)

  with pytest.raises(WebAttachFailedError):
    await orch.attach_adapter(
      detail.session_id,
      AttachAdapterBody(adapter_type=AdapterType.WEB, profile_id="scuffed-uno-web"),
    )

  status = orch.status(detail.session_id)
  assert status is not None
  assert status.attach_startup_diagnostics is not None
  assert status.attach_startup_diagnostics.failed_stage == "page_goto"
