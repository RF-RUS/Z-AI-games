"""Post-attach flow cycle failure diagnostics."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from uno_orchestrator.clients import binding_for
from uno_orchestrator.flow_controller import FlowController, RuntimeSession
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_orchestrator.recovery import decide_recovery, format_exception_message
from uno_schemas.orchestrator import (
  ErrorClass,
  FlowState,
  FlowStepName,
  RecoveryConfig,
  RecoveryMode,
  SessionSpec,
)
from uno_schemas.session import AdapterType, SessionConfig, SessionPhase


def test_format_exception_message_timeout_is_not_empty():
  assert format_exception_message(httpx.ReadTimeout("")) == "ReadTimeout"
  assert format_exception_message(TimeoutError()) == "TimeoutError"


def test_decide_recovery_includes_message():
  recovery = decide_recovery(
    ErrorClass.TRANSIENT,
    0,
    RecoveryConfig(max_retries=3),
    classify_all_permanent=False,
    fallback_to_mock=False,
    fallback_to_manual=True,
    message="ReadTimeout",
  )
  assert "ReadTimeout" in recovery.reason


@pytest.mark.asyncio
async def test_observe_timeout_marks_failed_step_and_keeps_active_on_retry():
  mock_client = AsyncMock()
  mock_client.capture_evidence = AsyncMock(side_effect=httpx.ReadTimeout(""))

  mock_registry = MagicMock()
  mock_registry.get_client = MagicMock(return_value=mock_client)

  with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=mock_registry):
    flow = FlowController()
    spec = SessionSpec(
      config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="a1"),
      recovery=RecoveryConfig(max_retries=3),
    )
    from uno_schemas.orchestrator import SessionDetail

    detail = SessionDetail(
      session_id="s1",
      flow_state=FlowState.ACTIVE,
      phase=SessionPhase.OBSERVE,
      correlation_id="c1",
      config=spec.config,
      adapter_bindings=[binding_for(AdapterType.WEB, "a1", "scuffed-uno-web")],
    )
    session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
    result = await flow.run_cycle(session)

    assert result["failed_step"] == FlowStepName.OBSERVE.value
    assert result["error"] == "ReadTimeout"
    assert detail.flow_state == FlowState.ACTIVE
    assert session.last_recovery.action == RecoveryMode.RETRY
    failed = [s for s in session.steps if not s.result.success]
    assert failed and failed[-1].step_name == FlowStepName.OBSERVE
    assert failed[-1].result.error == "ReadTimeout"


@pytest.mark.asyncio
async def test_web_start_warmup_transitions_to_active():
  orch = SessionOrchestrator()
  spec = SessionSpec(config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="a1"))
  detail = orch.create_session(spec)
  detail.adapter_bindings = [binding_for(AdapterType.WEB, "a1", "scuffed-uno-web")]

  mock_client = AsyncMock()
  mock_client.capture_evidence = AsyncMock(return_value=object())

  mock_registry = MagicMock()
  mock_registry.get_client = MagicMock(return_value=mock_client)
  orch._adapter_registry = mock_registry

  resp = await orch.start(detail.session_id)
  session = orch._sessions[detail.session_id]
  await session.warmup_task
  assert resp.flow_state == FlowState.ATTACHING
  assert detail.flow_state == FlowState.ACTIVE
  assert session.observe_ready is True
