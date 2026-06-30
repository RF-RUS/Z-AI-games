"""Chat domain models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from uno_schemas.ids import Confidence, SessionId, TimestampMs


class ChatMode(StrEnum):
  DISABLED = "disabled"
  DETECT_ONLY = "detect_only"
  MANUAL_APPROVE = "manual_approve"
  AUTO_REPLY = "auto_reply"


class ChatContext(StrEnum):
  GAMEPLAY = "gameplay"
  HELP = "help"
  SOCIAL = "social"
  SYSTEM = "system"
  UNKNOWN = "unknown"


class ChatMessage(BaseModel):
  message_id: str
  sender: str
  text: str
  timestamp_ms: TimestampMs
  is_bot: bool = False


class ChatIntent(BaseModel):
  directed_at_bot: bool
  reply_required: bool
  context: ChatContext
  confidence: Confidence
  trigger_message: ChatMessage
  reason: str = ""


class ChatReplyRequest(BaseModel):
  session_id: SessionId
  intent: ChatIntent
  recent_messages: list[ChatMessage] = Field(default_factory=list)
  use_model: bool = False
  correlation_id: str


class ChatReply(BaseModel):
  text: str
  approved: bool = True
  source: str = "template"
  confidence: Confidence = 1.0
  correlation_id: str


class ChatPolicyResult(BaseModel):
  allowed: bool
  reply: ChatReply | None = None
  violations: list[str] = Field(default_factory=list)
  correlation_id: str
