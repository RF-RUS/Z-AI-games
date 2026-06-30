"""Registry and runtime contract tests."""

import pytest
from fastapi.testclient import TestClient
from uno_model_registry.api import app as registry_app
from uno_model_runtime.api import app as runtime_app
from uno_schemas.model import ModelUseCase


@pytest.mark.contract
def test_registry_profiles_and_route():
  client = TestClient(registry_app)
  assert client.get("/profiles").status_code == 200
  r = client.post("/route", json={"use_case": ModelUseCase.EXPLANATION.value})
  assert r.status_code == 200
  assert "profile_id" in r.json()


@pytest.mark.smoke
def test_runtime_prompts_and_health():
  client = TestClient(runtime_app)
  assert client.get("/prompts").status_code == 200
  assert client.get("/providers/mock/health").json()["healthy"]
