"""Orchestrator integration tests with in-process services."""

import pytest
from fastapi.testclient import TestClient
from uno_orchestrator.in_process_clients import InProcessClients, setup_in_process_adapter_registry
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.orchestrator import AttachAdapterBody, SessionSpec
from uno_schemas.session import AdapterType, SessionConfig

setup_in_process_adapter_registry()


@pytest.fixture
def orchestrator() -> SessionOrchestrator:
  return SessionOrchestrator(clients=InProcessClients())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_full_cycle_mock(orchestrator: SessionOrchestrator):
  import asyncio
  spec = SessionSpec(config=SessionConfig(adapter_type=AdapterType.MOCK, adapter_id="pending"))
  detail = await orchestrator.create_session_with_game(spec)
  await orchestrator.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=AdapterType.MOCK))
  await orchestrator.start(detail.session_id)
  for _ in range(20):
    await asyncio.sleep(0.1)
    status = orchestrator.status(detail.session_id)
    if status and status.flow_state.value == "active":
      break
  result = await orchestrator.run_tick(detail.session_id)
  assert "correlation_id" in result
  assert orchestrator.status(detail.session_id) is not None
  assert len(orchestrator.get_steps(detail.session_id)) >= 5


@pytest.mark.integration
def test_orchestrator_api_contract():
  from uno_orchestrator.api import app
  client = TestClient(app)
  spec = SessionSpec(config=SessionConfig(adapter_type=AdapterType.MOCK, adapter_id="pending"))
  created = client.post("/sessions", json=spec.model_dump(mode="json"))
  assert created.status_code == 200
  sid = created.json()["session_id"]
  assert client.get(f"/sessions/{sid}").status_code == 200
  assert client.get(f"/sessions/{sid}/status").status_code == 200
