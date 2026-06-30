"""Smoke tests — services boot and health."""

import pytest
from fastapi.testclient import TestClient
from uno_config.api import app as config_app
from uno_core.api import app as core_app
from uno_model_registry.api import app as registry_app
from uno_schemas.api import HealthStatus


@pytest.mark.smoke
def test_uno_core_health():
  client = TestClient(core_app)
  resp = client.get("/health")
  assert resp.status_code == 200
  assert resp.json()["status"] == HealthStatus.HEALTHY.value


@pytest.mark.smoke
def test_config_loads():
  client = TestClient(config_app)
  resp = client.get("/config")
  assert resp.status_code == 200
  assert "features" in resp.json()


@pytest.mark.smoke
def test_model_registry_init():
  client = TestClient(registry_app)
  resp = client.get("/models")
  assert resp.status_code == 200
  assert len(resp.json()) >= 1


@pytest.mark.smoke
def test_model_runtime_smoke():
  from uno_model_runtime.api import app as runtime_app
  client = TestClient(runtime_app)
  assert client.get("/providers/mock/health").json()["healthy"]
  resp = client.post("/benchmark/run", json={"dataset": "chat_intent", "profile_id": "mock/uno-assistant"})
  assert resp.status_code == 200
  assert resp.json()["success_rate"] > 0


@pytest.mark.smoke
def test_orchestrator_api_smoke():
  from uno_orchestrator.api import app as orch_app
  from uno_schemas.orchestrator import SessionSpec
  from uno_schemas.session import AdapterType, SessionConfig
  client = TestClient(orch_app)
  spec = SessionSpec(config=SessionConfig(adapter_type=AdapterType.MOCK, adapter_id="pending"))
  assert client.post("/sessions", json=spec.model_dump(mode="json")).status_code == 200


@pytest.mark.smoke
def test_create_game_smoke():
  client = TestClient(core_app)
  resp = client.post("/games", json={"player_names": ["A", "B"], "seed": 1})
  assert resp.status_code == 200
  assert "game_id" in resp.json()
