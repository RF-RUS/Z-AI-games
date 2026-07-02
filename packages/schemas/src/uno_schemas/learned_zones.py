"""Learned interactive zones and operator clarification contracts.

Learned zones are persistent priors about where interactive UI elements live on
the screen for a given game, resolution, and (optionally) screen fingerprint.
They accumulate across sessions from successful/failed probes and operator
clarifications, and are reused as coordinate priors so the agent does not have
to rediscover the same UI every match.

Clarifications are short operator questions raised by the agent when it cannot
reliably understand a screen region or choose an action. The operator's answer
is folded back into learned zones, closing the discovery loop.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from uno_schemas.ids import Confidence, GameId, SessionId, TimestampMs


class ZoneType(StrEnum):
  """Semantic type of an interactive screen region."""

  BUTTON = "button"
  CARD = "card"
  CHAT = "chat"
  INPUT = "input"
  MODAL = "modal"
  END_TURN = "end_turn"
  LOBBY_CONTROL = "lobby_control"
  UNKNOWN = "unknown"


class Clickability(StrEnum):
  """Whether a zone is clickable. ``CONDITIONAL`` = needs the right game state."""

  CLICKABLE = "clickable"
  NON_CLICKABLE = "non_clickable"
  CONDITIONAL = "conditional"


class BoundingBox(BaseModel):
  left: float
  top: float
  right: float
  bottom: float

  @property
  def width(self) -> float:
    return self.right - self.left

  @property
  def height(self) -> float:
    return self.bottom - self.top

  @property
  def center(self) -> dict[str, float]:
    return {"x": (self.left + self.right) / 2, "y": (self.top + self.bottom) / 2}


class Resolution(BaseModel):
  # 0 is allowed as an "unknown" sentinel for a freshly-created empty map;
  # a real zone always carries a positive resolution.
  width: int = Field(ge=0)
  height: int = Field(ge=0)


class LearnedZone(BaseModel):
  """A single learned interactive zone, persisted across sessions.

  Identification: ``game_id`` + ``screen_fingerprint`` (when available) +
  ``resolution`` + ``bounding_box``. A label such as ``draw_button`` or
  ``play_card`` connects the zone to a domain action so the agent can resolve
  an action to coordinates without UIA/DOM support.
  """

  zone_id: str
  game_id: GameId
  screen_fingerprint: str | None = None
  resolution: Resolution
  bounding_box: BoundingBox
  click_point: dict[str, float]
  label: str = ""
  semantic_guess: str = ""
  zone_type: ZoneType = ZoneType.UNKNOWN
  clickability: Clickability = Clickability.CONDITIONAL
  clickability_score: Confidence = 0.5
  last_verified_result: str | None = None  # "success" | "failure" | None
  success_count: int = 0
  failure_count: int = 0
  created_at_ms: TimestampMs
  updated_at_ms: TimestampMs
  profile_id: str | None = None
  source: str = "discovered"  # "discovered" | "operator" | "probe"

  @property
  def total_probes(self) -> int:
    return self.success_count + self.failure_count

  @property
  def empirical_success_rate(self) -> float:
    n = self.total_probes
    return self.success_count / n if n > 0 else 0.0


class LearnedZoneMap(BaseModel):
  """All learned zones for a game at a given resolution."""

  game_id: GameId
  resolution: Resolution
  zones: list[LearnedZone] = Field(default_factory=list)
  updated_at_ms: TimestampMs = 0


class ClarificationStatus(StrEnum):
  PENDING = "pending"
  ANSWERED = "answered"
  EXPIRED = "expired"
  CANCELLED = "cancelled"


class ClarificationKind(StrEnum):
  """What the agent is uncertain about."""

  REGION_LABEL = "region_label"  # "what is this screen region?"
  ACTION = "action"  # "which action should I take?"
  SCREEN_STATE = "screen_state"  # "where am I in the game flow?"
  CONFIRM_CLICK = "confirm_click"  # "should I click here?"


class Clarification(BaseModel):
  """A short question from the agent to the operator.

  Carries enough evidence (a screenshot path and an optional target region) for
  the operator to answer without leaving the Control Center. The chosen option
  (or free-text answer) is folded back into a learned zone or screen-state prior.
  """

  question_id: str
  session_id: SessionId
  kind: ClarificationKind
  question: str
  options: list[str] = Field(default_factory=list)
  region: BoundingBox | None = None
  evidence_screenshot_path: str | None = None
  status: ClarificationStatus = ClarificationStatus.PENDING
  created_at_ms: TimestampMs
  answered_at_ms: TimestampMs | None = None
  # The chosen option (from ``options``) or a free-text answer.
  answer: str | None = None
  # Free-form metadata captured with the answer (e.g. the label assigned to a
  # region, the zone_type, whether the region is clickable).
  answer_metadata: dict[str, Any] = Field(default_factory=dict)


class ClarificationAnswer(BaseModel):
  """Operator's answer to a clarification."""

  answer: str
  zone_type: ZoneType | None = None
  clickability: Clickability | None = None
  label: str | None = None
  resume_session: bool = True
