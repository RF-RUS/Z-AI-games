"""Full-operator evaluation tests."""

import pytest
from uno_orchestrator.evaluation_runner import load_operator_dataset, run_operator_evaluation
from uno_orchestrator.in_process_clients import InProcessClients, setup_in_process_adapter_registry
from uno_orchestrator.orchestrator import SessionOrchestrator

setup_in_process_adapter_registry()


def test_load_full_operator_dataset():
  cases = load_operator_dataset("full_operator")
  assert len(cases) >= 10


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_full_operator_evaluation_sample():
  clients = InProcessClients()
  result = await run_operator_evaluation("full_operator_smoke", orchestrator=SessionOrchestrator(clients=clients))
  assert result.scenarios >= 2
  assert result.success_rate >= 0.5
