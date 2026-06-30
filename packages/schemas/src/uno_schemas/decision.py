"""Decision domain models — game-agnostic.

DecisionRequest and DecisionResult accept both LegalAction (UNO-specific)
and GameAction (game-agnostic) via Union types. This enables incremental
migration from UNO-specific to game-agnostic decision layer.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field
from uno_shared.game_plugin import GameAction

from uno_schemas.game import LegalAction
from uno_schemas.ids import Confidence, SessionId
from uno_schemas.perception import Observation


class StrategyId(StrEnum):
  HEURISTIC = "heuristic"
  RANDOM = "random"
  MODEL_ASSIST = "model_assist"


class DecisionRequest(BaseModel):
  session_id: SessionId
  observation: Observation
  legal_actions: list[LegalAction | GameAction] = Field(default_factory=list)
  strategy_id: StrategyId = StrategyId.HEURISTIC
  use_model_assist: bool = False
  model_profile_id: str | None = None
  correlation_id: str
  game_type: str | None = None


class DecisionCandidate(BaseModel):
  action: LegalAction | GameAction
  score: float
  reason: str = ""


class DecisionExplanation(BaseModel):
  summary: str
  candidates: list[DecisionCandidate] = Field(default_factory=list)
  model_used: bool = False
  model_id: str | None = None


class DecisionResult(BaseModel):
  chosen_action: LegalAction | GameAction
  confidence: Confidence
  explanation: DecisionExplanation
  correlation_id: str


class PolicyViolationType(StrEnum):
  ILLEGAL_ACTION = "illegal_action"
  LOW_CONFIDENCE = "low_confidence"
  UNSAFE_CHAT = "unsafe_chat"
  RATE_LIMIT = "rate_limit"
  INTERNAL_LEAK = "internal_leak"


class PolicyViolation(BaseModel):
  violation_type: PolicyViolationType
  message: str
  blocked_action: LegalAction | GameAction | None = None
  correlation_id: str | None = None
