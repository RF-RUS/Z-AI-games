"""Canonical UNO game domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from uno_schemas.ids import Confidence, EventId, GameId, ReplayId, SessionId, TimestampMs


class CardColor(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    WILD = "wild"


class CardValue(StrEnum):
    ZERO = "0"
    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    SKIP = "skip"
    REVERSE = "reverse"
    DRAW_TWO = "draw_two"
    WILD = "wild"
    WILD_DRAW_FOUR = "wild_draw_four"


class Card(BaseModel):
  color: CardColor
  value: CardValue

  def matches(self, other: Card) -> bool:
    if self.color == CardColor.WILD or other.color == CardColor.WILD:
      return True
    return self.color == other.color or self.value == other.value


class PlayerRef(BaseModel):
  player_id: str
  display_name: str
  seat: int = Field(ge=0)


class HandView(BaseModel):
  player_id: str
  cards: list[Card]
  confidence: Confidence = 1.0


class PublicTableState(BaseModel):
  top_card: Card
  draw_pile_count: int = Field(ge=0)
  discard_pile_count: int = Field(ge=0)
  current_player_id: str
  direction: int = Field(description="1 clockwise, -1 counter-clockwise")
  pending_draw: int = Field(default=0, ge=0)


class PrivatePlayerState(BaseModel):
  player_id: str
  hand_size: int = Field(ge=0)
  said_uno: bool = False
  is_bot: bool = False


class PendingEffect(StrEnum):
  NONE = "none"
  DRAW_STACK = "draw_stack"
  WILD_COLOR_CHOICE = "wild_color_choice"
  CHALLENGE_DRAW_FOUR = "challenge_draw_four"
  CHALLENGE_UNO = "challenge_uno"


class ActionType(StrEnum):
  PLAY_CARD = "play_card"
  DRAW_CARD = "draw_card"
  PASS = "pass"
  CHOOSE_COLOR = "choose_color"
  CALL_UNO = "call_uno"
  CHALLENGE = "challenge"
  ACCEPT_PENALTY = "accept_penalty"


class LegalAction(BaseModel):
  action_type: ActionType
  player_id: str
  card: Card | None = None
  chosen_color: CardColor | None = None
  action_id: str


class Command(BaseModel):
  command_id: str
  session_id: SessionId
  game_id: GameId
  action: LegalAction
  correlation_id: str
  issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventType(StrEnum):
  GAME_STARTED = "game_started"
  ACTION_EXECUTED = "action_executed"      # generic — any game action
  CARD_PLAYED = "card_played"
  CARD_DRAWN = "card_drawn"
  COLOR_CHOSEN = "color_chosen"
  DIRECTION_REVERSED = "direction_reversed"
  UNO_CALLED = "uno_called"
  UNO_CHALLENGED = "uno_challenged"
  DRAW_PENALTY_APPLIED = "draw_penalty_applied"
  TURN_SKIPPED = "turn_skipped"
  PLAYER_WON = "player_won"
  GAME_ENDED = "game_ended"


class DomainEvent(BaseModel):
  event_id: EventId
  event_type: EventType
  game_id: GameId
  session_id: SessionId | None = None
  sequence: int = Field(ge=0)
  timestamp_ms: TimestampMs
  payload: dict[str, Any] = Field(default_factory=dict)
  correlation_id: str | None = None


class ReplayEnvelope(BaseModel):
  replay_id: ReplayId
  game_id: GameId
  session_id: SessionId
  events: list[DomainEvent]
  metadata: dict[str, Any] = Field(default_factory=dict)
  created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
