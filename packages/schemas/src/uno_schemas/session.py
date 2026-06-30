"""Session orchestration and adapter contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from uno_schemas.chat import ChatMode
from uno_schemas.decision import StrategyId
from uno_schemas.ids import AdapterId, GameId, SessionId


class SessionPhase(StrEnum):
  IDLE = "idle"
  ATTACH = "attach"
  OBSERVE = "observe"
  DECIDE = "decide"
  EXECUTE = "execute"
  VERIFY = "verify"
  REPLAY = "replay"
  ERROR = "error"


class AdapterType(StrEnum):
  WEB = "web"
  WINDOWS = "windows"
  MOCK = "mock"


class SessionConfig(BaseModel):
  adapter_type: AdapterType
  adapter_id: AdapterId
  strategy_id: StrategyId = StrategyId.HEURISTIC
  chat_mode: ChatMode = ChatMode.DETECT_ONLY
  model_assist_enabled: bool = False
  active_model_id: str | None = None
  min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class SessionState(BaseModel):
  session_id: SessionId
  game_id: GameId | None = None
  phase: SessionPhase = SessionPhase.IDLE
  config: SessionConfig
  correlation_id: str
  error: str | None = None


class AttachAdapterRequest(BaseModel):
  session_id: SessionId
  adapter_type: AdapterType
  target_url: str | None = None
  window_title: str | None = None


class AttachAdapterResponse(BaseModel):
  session_id: SessionId
  adapter_id: AdapterId
  attached: bool
  message: str = ""
