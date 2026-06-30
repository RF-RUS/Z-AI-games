"""Web adapter domain — generic browser automation contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from uno_schemas.ids import AdapterId, Confidence, SessionId, TimestampMs
from uno_schemas.perception import DomEvidence, Observation, ScreenshotFrame


class AdapterMode(StrEnum):
  MOCK = "mock"
  PLAYWRIGHT = "playwright"


class ProfileSelector(BaseModel):
  primary: str
  fallbacks: list[str] = Field(default_factory=list)
  attribute: str | None = None


class ProfileHealthConfig(BaseModel):
  """Required/optional selector keys for drift health checks."""
  required: list[str] = Field(default_factory=list)
  optional: list[str] = Field(default_factory=list)


class SelectorMatchStatus(StrEnum):
  PASS_PRIMARY = "pass_primary"
  PASS_FALLBACK = "pass_fallback"
  FAIL = "fail"
  SKIP = "skip"


class ProfileHealthStatus(StrEnum):
  HEALTHY = "healthy"
  DEGRADED = "degraded"
  BROKEN = "broken"


class SelectorCheckResult(BaseModel):
  selector_name: str
  tier: str = "required"
  selector_type: str = "css"
  primary: str
  primary_matched: bool = False
  fallback_results: list[dict[str, bool | int | str]] = Field(default_factory=list)
  winning_selector: str | None = None
  winning_level: str | None = None
  match_count: int = 0
  status: SelectorMatchStatus = SelectorMatchStatus.FAIL
  latency_ms: int = Field(default=0, ge=0)
  notes: str = ""


class ProfileHealthReport(BaseModel):
  run_id: str
  profile_id: str
  target_url: str
  page_title: str = ""
  status: ProfileHealthStatus
  timestamp_ms: int = Field(ge=0)
  correlation_id: str | None = None
  trace_id: str | None = None
  source: str = "manual"
  selector_results: list[SelectorCheckResult] = Field(default_factory=list)
  fallback_usage_count: int = 0
  required_failure_count: int = 0
  dom_signature: str = ""
  screenshot_path: str | None = None
  report_path: str | None = None
  skipped: bool = False
  skip_reason: str | None = None
  remediation: ProfileHealthRemediation | None = None
  metadata: dict[str, str] = Field(default_factory=dict)


class ProfileHealthAlertSeverity(StrEnum):
  INFO = "info"
  WARNING = "warning"
  CRITICAL = "critical"


class ProfileHealthRemediation(BaseModel):
  runbook_path: str
  summary: str
  next_actions: list[str] = Field(default_factory=list)
  suspected_selectors: list[str] = Field(default_factory=list)


class ProfileHealthAlert(BaseModel):
  alert_id: str
  profile_id: str
  severity: ProfileHealthAlertSeverity
  alert_type: str
  message: str
  timestamp_ms: int = Field(ge=0)
  run_id: str | None = None
  correlation_id: str | None = None
  details: dict[str, str | int | float] = Field(default_factory=dict)
  remediation: ProfileHealthRemediation | None = None


class ProfileHealthHistoryEntry(BaseModel):
  run_id: str
  correlation_id: str | None = None
  timestamp_ms: int = Field(ge=0)
  status: ProfileHealthStatus
  required_failure_count: int = 0
  fallback_usage_count: int = 0
  report_path: str | None = None
  screenshot_path: str | None = None
  dom_signature: str = ""
  source: str = "manual"


class ProfileHealthSummary(BaseModel):
  profile_id: str
  latest_status: ProfileHealthStatus | None = None
  latest_run_id: str | None = None
  latest_correlation_id: str | None = None
  latest_timestamp_ms: int | None = None
  latest_report_path: str | None = None
  latest_screenshot_path: str | None = None
  consecutive_degraded: int = 0
  consecutive_broken: int = 0
  fallback_usage_ratio: float = 0.0
  selector_drift_counts: dict[str, int] = Field(default_factory=dict)
  recent_runs: list[ProfileHealthHistoryEntry] = Field(default_factory=list)
  active_alerts: list[ProfileHealthAlert] = Field(default_factory=list)
  runbook_path: str = "docs/runbooks/real-unoh-web-profile.md"
  metrics: dict[str, float | int | str] = Field(default_factory=dict)


class WebAdapterProfile(BaseModel):
  profile_id: str
  display_name: str
  launch_url: str
  allowed_domains: list[str] = Field(default_factory=list)
  game_type: str | None = None
  readiness_selector: str | None = None
  readiness_timeout_ms: int = Field(default=15000, ge=1000)
  selectors: dict[str, ProfileSelector] = Field(default_factory=dict)
  screenshot_crops: dict[str, dict[str, int]] = Field(default_factory=dict)
  action_mappings: dict[str, str] = Field(default_factory=dict)
  health: ProfileHealthConfig | None = None
  canvas_selector: str | None = None
  lobby_selectors: dict[str, ProfileSelector] = Field(default_factory=dict)
  layout_targets: dict[str, dict[str, float | str]] = Field(default_factory=dict)
  match_automation: str = "dom"
  goto_timeout_ms: int | None = None
  goto_wait_until: str = "domcontentloaded"
  browser_launch_timeout_ms: int | None = None
  browser_executable_path: str | None = None
  browser_channel: str | None = None
  bootstrap_on_attach: bool = True
  readiness_required: bool = True
  block_consent_scripts: bool = False
  notes: str = ""
  limitations: list[str] = Field(default_factory=list)


class DomNodeEvidence(BaseModel):
  selector: str
  tag: str | None = None
  text: str | None = None
  test_id: str | None = None
  attributes: dict[str, str] = Field(default_factory=dict)
  bbox: dict[str, float] | None = None


class DomSnapshot(BaseModel):
  snapshot_id: str
  url: str
  captured_at_ms: TimestampMs
  profile_id: str | None = None
  nodes: list[DomNodeEvidence] = Field(default_factory=list)
  extracted: dict[str, Any] = Field(default_factory=dict)
  confidence: Confidence = 0.85


class WebActionType(StrEnum):
  CLICK = "click"
  CLICK_COORDINATE = "click_coordinate"
  TYPE = "type"
  PRESS = "press"
  SELECT = "select"


class WebAutomationMode(StrEnum):
  LOBBY_HTML = "lobby_html"
  CANVAS_COORDINATE = "canvas_coordinate"
  UNKNOWN = "unknown"


class NavigationResponseRecord(BaseModel):
  url: str
  status: int | None = None
  ok: bool = False


class RequestFailureRecord(BaseModel):
  url: str
  failure: str = ""
  resource_type: str = ""


class NetworkReachabilityCheck(BaseModel):
  url: str
  reachable: bool = False
  status_code: int | None = None
  final_url: str | None = None
  elapsed_ms: int = 0
  error: str | None = None
  content_length: int | None = None


class PageGotoDiagnostics(BaseModel):
  requested_url: str = ""
  final_url: str | None = None
  page_title: str | None = None
  document_ready_state: str | None = None
  content_preview: str | None = None
  content_length: int | None = None
  wait_until: str = "domcontentloaded"
  browser_launch_mode: str = "bundled_chromium"
  navigation_responses: list[NavigationResponseRecord] = Field(default_factory=list)
  request_failures: list[RequestFailureRecord] = Field(default_factory=list)
  console_errors: list[str] = Field(default_factory=list)
  network_reachability: NetworkReachabilityCheck | None = None


class WebStartupDiagnostics(BaseModel):
  failed_stage: str | None = None
  error_message: str = ""
  stage_timings_ms: dict[str, int] = Field(default_factory=dict)
  screenshot_path: str | None = None
  trace_path: str | None = None
  log_path: str | None = None
  url: str | None = None
  profile_id: str | None = None
  page_goto: PageGotoDiagnostics | None = None


class WebPageDiagnostics(BaseModel):
  automation_mode: WebAutomationMode = WebAutomationMode.UNKNOWN
  canvas_detected: bool = False
  canvas_bounds: dict[str, float] | None = None
  lobby_control_count: int = 0
  uia_actionable_in_match: bool = False
  message: str = ""
  recommended_action: str = ""


class ActionExecutionRequest(BaseModel):
  action_type: WebActionType
  selector: str | None = None
  selector_key: str | None = None
  domain_action: str | None = None
  text: str | None = None
  key: str | None = None
  click_x: float | None = None
  click_y: float | None = None
  coordinate_reference: str = "canvas"
  timeout_ms: int = Field(default=5000, ge=500)


class ActionExecutionResult(BaseModel):
  success: bool
  action_type: WebActionType
  selector: str | None = None
  selector_key: str | None = None
  click_point: dict[str, float] | None = None
  canvas_bounds: dict[str, float] | None = None
  diagnostics: WebPageDiagnostics | None = None
  error: str | None = None
  duration_ms: int = Field(default=0, ge=0)
  screenshot_path: str | None = None
  correlation_id: str | None = None


class AttachWebAdapterRequest(BaseModel):
  session_id: SessionId
  profile_id: str = "local-mock-uno"
  url: str | None = None
  mode: AdapterMode = AdapterMode.MOCK
  headless: bool = True
  record_trace: bool = False
  correlation_id: str | None = None
  cdp_url: str | None = None


class AttachWebAdapterResponse(BaseModel):
  adapter_id: AdapterId | None = None
  session_id: SessionId
  attached: bool
  mode: AdapterMode
  profile_id: str
  url: str
  message: str = ""
  startup_diagnostics: WebStartupDiagnostics | None = None


class AdapterEvidenceBundle(BaseModel):
  adapter_id: AdapterId
  session_id: SessionId
  dom_snapshot: DomSnapshot
  dom_evidence: DomEvidence
  screenshot: ScreenshotFrame | None = None
  chat_messages: list[str] = Field(default_factory=list)
  correlation_id: str | None = None


class ReplayArtifactType(StrEnum):
  SCREENSHOT = "screenshot"
  DOM_SNAPSHOT = "dom_snapshot"
  TRACE = "trace"
  OBSERVATION = "observation"
  ACTION_RESULT = "action_result"


class ReplayArtifactRef(BaseModel):
  artifact_id: str
  artifact_type: ReplayArtifactType
  path: str | None = None
  mime_type: str | None = None
  correlation_id: str | None = None
  event_sequence: int | None = None
  observation_id: str | None = None
  metadata: dict[str, str] = Field(default_factory=dict)


class ObservationArtifactBundle(BaseModel):
  observation_id: str
  session_id: SessionId
  screenshot: ScreenshotFrame | None = None
  dom_snapshot: DomSnapshot | None = None
  observation: Observation | None = None
  artifacts: list[ReplayArtifactRef] = Field(default_factory=list)
  correlation_id: str | None = None


from uno_schemas.game import DomainEvent


class ReplayDetail(BaseModel):
  replay_id: str
  game_id: str
  session_id: str
  events: list[DomainEvent] = Field(default_factory=list)
  artifacts: list[ReplayArtifactRef] = Field(default_factory=list)
  observations: list[ObservationArtifactBundle] = Field(default_factory=list)
  metadata: dict[str, Any] = Field(default_factory=dict)
