"""Hard safety validation — blocks illegal and unsafe actions."""

from __future__ import annotations

import re
from typing import Any

from uno_schemas.chat import ChatReply
from uno_schemas.decision import DecisionResult, PolicyViolation, PolicyViolationType
from uno_schemas.game import LegalAction
from uno_shared.game_plugin import GameAction

TOXIC_PATTERNS = [
  re.compile(p, re.I)
  for p in [r"\bidiot\b", r"\bstupid\b", r"\bhate\b", r"\bkill\b"]
]

INTERNAL_LEAK_PATTERNS = [
  re.compile(p, re.I)
  for p in [r"my hand", r"hidden card", r"opponent.*has", r"model.*thinks", r"confidence.*\d"]
]


def _get_action_id(action) -> str:
  return getattr(action, 'action_id', '')


def _get_action_type(action) -> str:
  at = getattr(action, 'action_type', None)
  return at.value if hasattr(at, 'value') else str(at) if at else ''


def _get_action_card(action) -> Any:
  card = getattr(action, 'card', None)
  if card is None:
    payload = getattr(action, 'payload', {})
    card = payload.get('card')
  return card


def validate_decision(
  decision: DecisionResult,
  legal_actions: list[LegalAction | GameAction],
  min_confidence: float = 0.3,
  kill_switch_active: bool = False,
  dry_run: bool = False,
) -> tuple[bool, PolicyViolation | None]:
  # Kill switch: hard global halt. Every action is blocked until an operator
  # releases it (POST /guard/kill-switch {"active": false}).
  if kill_switch_active:
    return False, PolicyViolation(
      violation_type=PolicyViolationType.KILL_SWITCH,
      message="kill switch active — all actions halted",
      blocked_action=decision.chosen_action,
      correlation_id=decision.correlation_id,
    )

  legal_ids = {_get_action_id(a) for a in legal_actions}
  if _get_action_id(decision.chosen_action) not in legal_ids:
    chosen_type = _get_action_type(decision.chosen_action)
    chosen_card = _get_action_card(decision.chosen_action)
    matched = any(
      _get_action_type(a) == chosen_type
      and _get_action_card(a) == chosen_card
      for a in legal_actions
    )
    if not matched:
      return False, PolicyViolation(
        violation_type=PolicyViolationType.ILLEGAL_ACTION,
        message="chosen action not in legal set",
        blocked_action=decision.chosen_action,
        correlation_id=decision.correlation_id,
      )

  if decision.confidence < min_confidence:
    return False, PolicyViolation(
      violation_type=PolicyViolationType.LOW_CONFIDENCE,
      message=f"confidence {decision.confidence} below threshold {min_confidence}",
      blocked_action=decision.chosen_action,
      correlation_id=decision.correlation_id,
    )
  return True, None


def validate_chat_reply(reply: ChatReply, correlation_id: str) -> tuple[bool, list[str]]:
  violations: list[str] = []
  text = reply.text

  for pattern in TOXIC_PATTERNS:
    if pattern.search(text):
      violations.append("toxic content detected")

  for pattern in INTERNAL_LEAK_PATTERNS:
    if pattern.search(text):
      violations.append("internal reasoning or hidden info leak")

  if len(text) > 280:
    violations.append("reply too long — spam risk")

  return len(violations) == 0, violations
