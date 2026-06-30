"""Orchestrator flow control and session lifecycle DTOs."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from uno_schemas.adapter_web import WebStartupDiagnostics
from uno_schemas.ids import AdapterId, GameId, ReplayId, SessionId
from uno_schemas.session import AdapterType, SessionConfig, SessionPhase


class FlowState(StrEnum):
  IDLE = "idle"
  ATTACHING = "attaching"
  ACTIVE = "active"
  PAUSED = "paused"
  DISABLED = "disabled"
  ERROR = "error"
  REPLAYING = "replaying"


class FlowStepName(StrEnum):
  OBSERVE = "observe"
  PERCEIVE = "perceive"
  LEGAL_ACTIONS = "legal_actions"
  DECIDE = "decide"
  GUARD = "guard"
  EXECUTE = "execute"
  RECORD = "record"
  MODEL_ADVISORY = "model_advisory"


class ErrorClass(StrEnum):
  TRANSIENT = "transient"
  PERMANENT = "permanent"
  POLICY_BLOCKED = "policy_blocked"
  PERCEPTION_LOW_CONFIDENCE = "perception_low_confidence"


class RecoveryMode(StrEnum):
  RETRY = "retry"
  FALLBACK_MOCK = "fallback_mock"
  FALLBACK_MANUAL = "fallback_manual"
  STOP = "stop"
  PAUSE = "pause"


class RecoveryConfig(BaseModel):
  max_retries: int = Field(default=3, ge=0, le=10)
  backoff_ms: int = Field(default=500, ge=0)
  fallback_to_mock: bool = True
  fallback_to_manual: bool = True
  step_timeout_seconds: float = Field(default=15.0, ge=1.0)


class SessionSpec(BaseModel):
  config: SessionConfig
  game_player_names: list[str] = Field(default_factory=lambda: ["Bot", "Opponent"])
  web_profile_id: str = "local-mock-uno"
  windows_profile_id: str = "local-mock-uno"
  target_url: str | None = None
  window_title: str | None = None
  automatic: bool = False
  recovery: RecoveryConfig = Field(default_factory=RecoveryConfig)


class AdapterBinding(BaseModel):
  adapter_type: AdapterType
  adapter_id: AdapterId | None = None
  attached: bool = False
  profile_id: str | None = None
  healthy: bool = True
  last_error: str | None = None


class StepResult(BaseModel):
  success: bool
  error: str | None = None
  error_class: ErrorClass | None = None
  latency_ms: int = Field(default=0, ge=0)
  retries: int = Field(default=0, ge=0)
  metadata: dict[str, str] = Field(default_factory=dict)


class FlowStep(BaseModel):
  step_id: str
  correlation_id: str
  step_name: FlowStepName
  phase: SessionPhase
  flow_state: FlowState
  result: StepResult
  timestamp_ms: int = Field(ge=0)


class RecoveryDecision(BaseModel):
  error_class: ErrorClass
  action: RecoveryMode
  reason: str
  retry_after_ms: int = Field(default=0, ge=0)


class OrchestratorMetrics(BaseModel):
  total_steps: int = 0
  successful_steps: int = 0
  failed_steps: int = 0
  retries: int = 0
  fallbacks: int = 0
  policy_blocks: int = 0
  model_advisory_calls: int = 0
  avg_step_latency_ms: float = 0.0


class StrategySnapshot(BaseModel):
  """Semantic strategy snapshot for operator visibility.

  Built by the orchestrator from latest observation + decision + steps.
  Provides operator-readable strategy state, not raw pipeline internals.
  """
  goal: str = ""
  detected_state: str = "unknown"
  hypothesis: str = ""
  next_action: str | None = None
  why_action: str | None = None
  confidence: float | None = None
  blocked_reason: str | None = None
  last_executed: str | None = None
  game_type: str | None = None
  verification: VerificationResult | None = None


class VerificationResult(BaseModel):
  """Action-aware coarse verification — state-based, not full semantic.

  Compares coarse screen states before and after action.
  Action category + family determine expected outcome:
  - category: navigation | in_game | unknown (broad grouping)
  - family: state_advance | state_may_advance | observability | in_game_effect | unknown
  """
  delivery_status: str = "unknown"  # delivered | failed | unknown
  outcome_status: str = "unknown"   # confirmed | not_confirmed | unknown
  expected_transition: str | None = None
  observed_transition: str | None = None
  action_category: str = "unknown"  # navigation | in_game | unknown
  action_family: str = "unknown"    # state_advance | state_may_advance | observability | in_game_effect | unknown
  observability_signals: list[str] | None = None  # unknown_to_known | confidence_increased | error_cleared
  evidence_strength: str | None = None  # none | weak | moderate | strong (observability family only)
  summary: str = ""


class OrchestratorStatus(BaseModel):
  session_id: SessionId
  flow_state: FlowState
  phase: SessionPhase
  game_id: GameId | None = None
  replay_id: ReplayId | None = None
  correlation_id: str
  adapter_bindings: list[AdapterBinding] = Field(default_factory=list)
  automatic: bool = False
  error: str | None = None
  last_recovery: RecoveryDecision | None = None
  attach_startup_diagnostics: WebStartupDiagnostics | None = None
  metrics: OrchestratorMetrics = Field(default_factory=OrchestratorMetrics)
  strategy_snapshot: StrategySnapshot | None = None


class SessionDetail(BaseModel):
  session_id: SessionId
  flow_state: FlowState
  phase: SessionPhase
  config: SessionConfig
  game_id: GameId | None = None
  replay_id: ReplayId | None = None
  correlation_id: str
  automatic: bool = False
  error: str | None = None
  attach_startup_diagnostics: WebStartupDiagnostics | None = None
  adapter_bindings: list[AdapterBinding] = Field(default_factory=list)
  metrics: OrchestratorMetrics = Field(default_factory=OrchestratorMetrics)
  executed_correlation_ids: list[str] = Field(default_factory=list)


class AttachAdapterBody(BaseModel):
  adapter_type: AdapterType | None = None
  profile_id: str | None = None
  target_url: str | None = None
  window_title: str | None = None
  window_handle: int | None = None
  window_pid: int | None = None
  launch_test_target: bool = False
  windows_use_pywinauto: bool = True
  cdp_url: str | None = None


class FlowControlResponse(BaseModel):
  session_id: SessionId
  flow_state: FlowState
  message: str = ""
