"""Explicit flow state transitions."""

from __future__ import annotations

from uno_schemas.orchestrator import FlowState

_ALLOWED: dict[FlowState, set[FlowState]] = {
  FlowState.IDLE: {FlowState.ATTACHING, FlowState.ACTIVE, FlowState.DISABLED, FlowState.REPLAYING},
  FlowState.ATTACHING: {FlowState.IDLE, FlowState.ACTIVE, FlowState.ERROR},
  FlowState.ACTIVE: {FlowState.PAUSED, FlowState.IDLE, FlowState.ERROR, FlowState.DISABLED},
  FlowState.PAUSED: {FlowState.ACTIVE, FlowState.IDLE, FlowState.ERROR, FlowState.DISABLED},
  FlowState.ERROR: {FlowState.IDLE, FlowState.PAUSED, FlowState.ACTIVE, FlowState.DISABLED},
  FlowState.DISABLED: {FlowState.IDLE},
  FlowState.REPLAYING: {FlowState.IDLE, FlowState.PAUSED},
}


class InvalidTransition(Exception):
  pass


def can_transition(current: FlowState, target: FlowState) -> bool:
  return target in _ALLOWED.get(current, set())


def transition(current: FlowState, target: FlowState) -> FlowState:
  if not can_transition(current, target):
    raise InvalidTransition(f"{current.value} -> {target.value}")
  return target
