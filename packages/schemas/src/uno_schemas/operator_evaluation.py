"""End-to-end operator evaluation schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from uno_schemas.session import AdapterType


class OperatorScenario(BaseModel):
  scenario_id: str
  description: str
  adapter_type: AdapterType = AdapterType.MOCK
  max_ticks: int = Field(default=1, ge=1, le=20)
  min_confidence: float = Field(default=0.3, ge=0.0, le=1.0)
  model_assist: bool = False
  initial_state: dict = Field(default_factory=dict)
  expected: dict = Field(default_factory=dict)
  scoring_weights: dict[str, float] = Field(default_factory=lambda: {
    "legal_action": 0.4,
    "policy_pass": 0.3,
    "flow_complete": 0.2,
    "no_error": 0.1,
  })
  tags: list[str] = Field(default_factory=list)


class OperatorScenarioResult(BaseModel):
  scenario_id: str
  success: bool
  score: float
  ticks_run: int
  legal_action_ok: bool = False
  policy_pass_ok: bool = False
  flow_complete_ok: bool = False
  error: str | None = None
  failure_reason: str | None = None
  flow_steps: int = 0
  metadata: dict[str, str] = Field(default_factory=dict)


class OperatorEvaluationRun(BaseModel):
  run_id: str
  mode: str = "full_operator"
  dataset: str
  profile_id: str | None = None
  scenarios: int = 0
  success_rate: float = 0.0
  avg_score: float = 0.0
  avg_ticks: float = 0.0
  policy_accept_rate: float = 0.0
  case_results: list[OperatorScenarioResult] = Field(default_factory=list)
  metadata: dict[str, str] = Field(default_factory=dict)
