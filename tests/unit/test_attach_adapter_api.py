"""Attach adapter API returns session detail with diagnostics on failure."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from uno_orchestrator.api import app, orchestrator
from uno_orchestrator.orchestrator import WebAttachFailedError
from uno_schemas.adapter_web import WebStartupDiagnostics
from uno_schemas.session import AdapterType


@pytest.fixture
def client():
  orchestrator._sessions.clear()
  return TestClient(app)


def test_attach_adapter_502_includes_session_with_diagnostics(client):
  detail = orchestrator.create_session(
    __import__("uno_schemas.orchestrator", fromlist=["SessionSpec"]).SessionSpec(
      config=__import__("uno_schemas.session", fromlist=["SessionConfig"]).SessionConfig(
        adapter_type=AdapterType.WEB,
        adapter_id="pending",
      ),
      web_profile_id="scuffed-uno-web",
    )
  )
  diagnostics = WebStartupDiagnostics(
    failed_stage="page_goto",
    error_message="Playwright startup failed at stage=page_goto (60000ms): timeout",
    stage_timings_ms={"page_goto": 60000},
  )

  async def fail_attach(session_id, body):
    session = orchestrator._require(session_id)
    session.detail.attach_startup_diagnostics = diagnostics
    session.detail.error = diagnostics.error_message
    raise WebAttachFailedError(diagnostics.error_message, diagnostics)

  orchestrator.attach_adapter = AsyncMock(side_effect=fail_attach)

  r = client.post(
    f"/sessions/{detail.session_id}/attach-adapter",
    json={"adapter_type": "web", "profile_id": "scuffed-uno-web"},
  )

  assert r.status_code == 502
  body = r.json()
  assert "session" in body["detail"]
  assert body["detail"]["session"]["attach_startup_diagnostics"]["failed_stage"] == "page_goto"
