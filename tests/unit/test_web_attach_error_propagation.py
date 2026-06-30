"""Web attach error propagation and recovery behavior."""

import pytest
from uno_orchestrator.recovery import decide_attach_recovery, decide_recovery
from uno_schemas.orchestrator import ErrorClass, RecoveryConfig, RecoveryMode
from uno_schemas.session import AdapterType


def test_decide_recovery_web_never_falls_back_to_mock():
  recovery = decide_recovery(
    ErrorClass.PERMANENT,
    retry_count=99,
    config=RecoveryConfig(fallback_to_mock=True),
    classify_all_permanent=True,
    fallback_to_mock=False,
    fallback_to_manual=True,
  )
  assert recovery.action == RecoveryMode.STOP
  assert recovery.action != RecoveryMode.FALLBACK_MOCK


def test_decide_attach_recovery_uses_exact_backend_message():
  msg = "Playwright startup failed at stage=page_goto (60000ms): timeout"
  recovery = decide_attach_recovery(ErrorClass.PERMANENT, msg, AdapterType.WEB)
  assert recovery.action == RecoveryMode.STOP
  assert recovery.reason == msg


@pytest.mark.asyncio
async def test_tick_without_adapter_preserves_web_attach_error():

  from uno_orchestrator.orchestrator import SessionOrchestrator
  from uno_schemas.orchestrator import SessionSpec
  from uno_schemas.session import SessionConfig

  orch = SessionOrchestrator()
  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
    web_profile_id="scuffed-uno-web",
    recovery=RecoveryConfig(fallback_to_mock=True),
  )
  detail = await orch.create_session_with_game(spec)
  attach_error = "Playwright startup failed at stage=browser_launch (1200ms): launch failed"
  detail.error = attach_error
  detail.flow_state = "error"
  session = orch._sessions[detail.session_id]
  session.last_recovery = decide_attach_recovery(ErrorClass.PERMANENT, attach_error, AdapterType.WEB)

  result = await orch.run_tick(detail.session_id)

  assert "error" in result
  assert orch.get_session(detail.session_id).error == attach_error
  status = orch.status(detail.session_id)
  assert status.last_recovery is not None
  assert status.last_recovery.action == RecoveryMode.STOP
  assert attach_error in (status.last_recovery.reason or "")
  assert status.last_recovery.action != RecoveryMode.FALLBACK_MOCK
