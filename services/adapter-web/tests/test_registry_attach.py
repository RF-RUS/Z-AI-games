"""Failed attach must return structured diagnostics, not HTTP 500."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from uno_adapter_web.api import app
from uno_adapter_web.registry import attach_adapter
from uno_adapter_web.startup import PlaywrightStartupError, StartupStage
from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterRequest, WebStartupDiagnostics


@pytest.mark.asyncio
async def test_failed_attach_returns_null_adapter_id_with_diagnostics():
  diagnostics = WebStartupDiagnostics(
    failed_stage="page_goto",
    error_message="Playwright startup failed at stage=page_goto (60000ms): timeout",
    stage_timings_ms={"browser_launch": 1200, "page_goto": 60000},
    log_path="artifacts/sess/startup-failure-page_goto.json",
  )
  mock_adapter = AsyncMock()
  mock_adapter.attach.side_effect = PlaywrightStartupError(
    StartupStage.PAGE_GOTO,
    "timeout",
    elapsed_ms=60000,
  )
  mock_adapter.startup_diagnostics = diagnostics

  with patch("uno_adapter_web.registry.create_adapter", return_value=("aid-1", mock_adapter)):
    resp = await attach_adapter(
      AttachWebAdapterRequest(
        session_id="sess-1",
        profile_id="scuffed-uno-web",
        mode=AdapterMode.PLAYWRIGHT,
      )
    )

  assert resp.attached is False
  assert resp.adapter_id is None
  assert resp.startup_diagnostics is not None
  assert resp.startup_diagnostics.failed_stage == "page_goto"
  assert "page_goto" in resp.message


def test_attach_api_serializes_failed_response():
  diagnostics = WebStartupDiagnostics(
    failed_stage="page_goto",
    error_message="Playwright startup failed at stage=page_goto (60000ms): timeout",
    stage_timings_ms={"page_goto": 60000},
  )
  mock_adapter = AsyncMock()
  mock_adapter.attach = AsyncMock(return_value=False)
  mock_adapter.startup_diagnostics = diagnostics
  mock_adapter.detach = AsyncMock()

  with patch("uno_adapter_web.registry.create_adapter", return_value=("aid-1", mock_adapter)):
    client = TestClient(app)
    r = client.post(
      "/attach",
      json={
        "session_id": "sess-api",
        "profile_id": "scuffed-uno-web",
        "mode": "playwright",
      },
    )

  assert r.status_code == 200
  body = r.json()
  assert body["attached"] is False
  assert body["adapter_id"] is None
  assert body["startup_diagnostics"]["failed_stage"] == "page_goto"
