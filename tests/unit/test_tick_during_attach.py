"""Tick must not mutate session while attach is in progress."""

import pytest
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.orchestrator import FlowState, SessionSpec
from uno_schemas.session import AdapterType, SessionConfig


@pytest.mark.asyncio
async def test_tick_skips_while_attaching():
  orch = SessionOrchestrator()
  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
    web_profile_id="scuffed-uno-web",
  )
  detail = orch.create_session(spec)
  detail.flow_state = FlowState.ATTACHING
  session = orch._sessions[detail.session_id]

  result = await orch.run_tick(detail.session_id)

  assert result["skipped"] is True
  assert result["reason"] == "observe warmup in progress"
