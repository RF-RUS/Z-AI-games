"""Orchestrator state machine and recovery unit tests."""

import httpx
import pytest
from uno_orchestrator.recovery import classify_error, decide_recovery
from uno_orchestrator.state_machine import InvalidTransition, can_transition, transition
from uno_schemas.orchestrator import ErrorClass, FlowState, RecoveryConfig, RecoveryMode


def test_idle_to_active():
  assert can_transition(FlowState.IDLE, FlowState.ACTIVE)
  assert transition(FlowState.IDLE, FlowState.ACTIVE) == FlowState.ACTIVE


def test_invalid_transition():
  assert not can_transition(FlowState.DISABLED, FlowState.ACTIVE)
  with pytest.raises(InvalidTransition):
    transition(FlowState.DISABLED, FlowState.ACTIVE)


def test_classify_transient_timeout():
  assert classify_error(httpx.TimeoutException("t")) == ErrorClass.TRANSIENT


def test_recovery_policy_block_retries():
  d = decide_recovery(ErrorClass.POLICY_BLOCKED, 0, RecoveryConfig())
  assert d.action == RecoveryMode.RETRY


def test_recovery_retries_transient():
  d = decide_recovery(ErrorClass.TRANSIENT, 0, RecoveryConfig(max_retries=3))
  assert d.action == RecoveryMode.RETRY
