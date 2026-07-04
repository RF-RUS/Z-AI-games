"""Windows adapter domain — generic desktop automation contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from uno_schemas.adapter_web import ReplayArtifactRef
from uno_schemas.ids import AdapterId, Confidence, SessionId, TimestampMs
from uno_schemas.perception import ScreenshotFrame, UiEvidence


class WindowsAdapterMode(StrEnum):
  MOCK = "mock"
  PYWINAUTO = "pywinauto"


class WindowsBackend(StrEnum):
  UIA = "uia"
  WIN32 = "win32"


class WindowMatcher(BaseModel):
  title_regex: str | None = None
  exclude_title_regex: str | None = None
  class_name: str | None = None
  process_name: str | None = None
  executable_hint: str | None = None


class ControlSelector(BaseModel):
  auto_id: str | None = None
  control_type: str | None = None
  title: str | None = None
  title_regex: str | None = None
  class_name: str | None = None
  path_hints: list[str] = Field(default_factory=list)


class WindowsAdapterProfile(BaseModel):
  profile_id: str
  display_name: str
  window: WindowMatcher
  game_type: str | None = None
  test_target_script: str | None = None
  preferred_backend: WindowsBackend = WindowsBackend.UIA
  fallback_backend: WindowsBackend | None = WindowsBackend.WIN32
  readiness_timeout_ms: int = Field(default=15000, ge=1000)
  selectors: dict[str, ControlSelector] = Field(default_factory=dict)
  chat_selectors: dict[str, ControlSelector] = Field(default_factory=dict)
  screenshot_crops: dict[str, dict[str, int]] = Field(default_factory=dict)
  action_mappings: dict[str, str] = Field(default_factory=dict)
  layout_targets: dict[str, dict[str, float | str]] = Field(default_factory=dict)
  match_automation: str | None = None
  notes: str = ""
  limitations: list[str] = Field(default_factory=list)


class UiNodeSnapshot(BaseModel):
  node_id: str
  control_type: str | None = None
  name: str | None = None
  auto_id: str | None = None
  class_name: str | None = None
  bounds: dict[str, float] | None = None
  enabled: bool | None = None
  visible: bool | None = None
  depth: int = 0


class WindowSnapshot(BaseModel):
  snapshot_id: str
  window_title: str
  class_name: str | None = None
  process_name: str | None = None
  backend: str = "uia"
  captured_at_ms: TimestampMs
  profile_id: str | None = None
  nodes: list[UiNodeSnapshot] = Field(default_factory=list)
  extracted: dict[str, Any] = Field(default_factory=dict)
  confidence: Confidence = 0.85
  truncated: bool = False
  sparse_tree: bool = False


class ControlEvidence(BaseModel):
  selector_key: str
  control_type: str | None = None
  name: str | None = None
  text: str | None = None
  auto_id: str | None = None
  confidence: Confidence = 0.8


class WindowsEvidenceBundle(BaseModel):
  adapter_id: AdapterId
  session_id: SessionId
  adapter_source: str = "windows"
  window_snapshot: WindowSnapshot
  ui_evidence: UiEvidence
  screenshot: ScreenshotFrame | None = None
  chat_messages: list[str] = Field(default_factory=list)
  controls: list[ControlEvidence] = Field(default_factory=list)
  correlation_id: str | None = None


class WindowsActionType(StrEnum):
  CLICK = "click"
  CLICK_INPUT = "click_input"
  TYPE = "type"
  SET_FOCUS = "set_focus"
  SEND_KEYS = "send_keys"


class WindowsActionExecutionRequest(BaseModel):
  action_type: WindowsActionType
  selector_key: str | None = None
  auto_id: str | None = None
  title: str | None = None
  text: str | None = None
  keys: str | None = None
  capture_screenshots: bool = False
  timeout_ms: int = Field(default=5000, ge=500)
  min_confidence: Confidence = 0.55
  allow_coordinate_fallback: bool = False
  domain_action: str = ""
  # Grounded CV target: click point in SCREENSHOT-pixel space (relative to the
  # captured window frame). When set, the executor clicks it directly instead of
  # running the UIA / static-layout cascade. Populated from screenshot card
  # detection. See visual_executor grounded-click path.
  target_x: int | None = None
  target_y: int | None = None


class WindowsActionExecutionResult(BaseModel):
  success: bool
  action_type: WindowsActionType
  target_metadata: dict[str, Any] = Field(default_factory=dict)
  error: str | None = None
  warnings: list[str] = Field(default_factory=list)
  duration_ms: int = Field(default=0, ge=0)
  screenshot_before: str | None = None
  screenshot_after: str | None = None
  click_point: dict[str, float] | None = None
  confidence: Confidence = 0.0
  uncertain: bool = False
  verification: VerificationResult | None = None
  domain_action: str = ""
  artifact_refs: list[ReplayArtifactRef] = Field(default_factory=list)
  correlation_id: str | None = None


class AttachWindowsAdapterRequest(BaseModel):
  session_id: SessionId
  profile_id: str = "local-mock-uno"
  mode: WindowsAdapterMode = WindowsAdapterMode.MOCK
  window_title: str | None = None
  window_handle: int | None = None
  window_pid: int | None = None
  launch_test_target: bool = False
  capture_screenshots: bool = True
  attended_rpa: bool = True
  correlation_id: str | None = None


class AttachWindowsAdapterResponse(BaseModel):
  adapter_id: AdapterId
  session_id: SessionId
  attached: bool
  mode: WindowsAdapterMode
  profile_id: str
  window_title: str = ""
  backend: str | None = None
  message: str = ""


class WindowCandidate(BaseModel):
  handle: int
  title: str = ""
  pid: int | None = None
  process_name: str | None = None
  class_name: str | None = None
  is_visible: bool = True
  is_focused: bool = False
  is_browser_host: bool = False
  attach_warning: str | None = None


class WindowsRpaStatus(StrEnum):
  LOADING = "loading"
  OFFLINE = "offline"
  ATTACHED = "attached"
  SEARCHING = "searching"
  READY = "ready"
  ACTING = "acting"
  VERIFYING = "verifying"
  UNCERTAIN = "uncertain"
  FAILED = "failed"
  PAUSED = "paused"
  STOPPED = "stopped"


class PreviewFrameKind(StrEnum):
  """How the operator preview frame was produced."""

  LIVE = "live"
  SYNTHETIC = "synthetic"
  NONE = "none"


class TargetAcquisitionMethod(StrEnum):
  UIA = "uia"
  IMAGE = "image"
  OCR = "ocr"
  COORDINATE = "coordinate"


class WindowAttachment(BaseModel):
  window_title: str = ""
  class_name: str | None = None
  process_name: str | None = None
  backend: str = "uia"
  bounds: dict[str, float] | None = None
  dpi_scale: float = 1.0
  focused: bool = True
  window_handle: int | None = None
  expected_title: str | None = None
  live_title: str | None = None
  is_browser_host: bool = False
  attach_warning: str | None = None


class UiaTreeDiagnostics(BaseModel):
  node_count: int = 0
  named_node_count: int = 0
  actionable_control_count: int = 0
  document_actionable_count: int = 0
  button_count: int = 0
  document_count: int = 0
  sparse_tree: bool = False
  canvas_like: bool = False
  uia_actionable: bool = True
  message: str = ""
  recommended_action: str = ""


class ScreenFrame(BaseModel):
  frame_id: str
  path: str
  captured_at_ms: int = Field(ge=0)
  width: int = 0
  height: int = 0
  data_base64: str | None = None


class UITarget(BaseModel):
  selector_key: str
  label: str = ""
  method: TargetAcquisitionMethod = TargetAcquisitionMethod.UIA
  confidence: Confidence = 0.0
  bounds: dict[str, float] | None = None
  click_point: dict[str, float] | None = None
  auto_id: str | None = None
  title: str | None = None


class UITargetSet(BaseModel):
  targets: list[UITarget] = Field(default_factory=list)
  sparse_tree: bool = False


class VisualActionRequest(BaseModel):
  domain_action: str = ""
  selector_key: str | None = None
  action_type: WindowsActionType = WindowsActionType.CLICK_INPUT
  text: str | None = None
  keys: str | None = None
  min_confidence: Confidence = 0.55
  allow_coordinate_fallback: bool = False
  capture_screenshots: bool = True
  timeout_ms: int = Field(default=5000, ge=500)


class VerificationResult(BaseModel):
  passed: bool
  status: str = "unknown"
  change_ratio: float = 0.0
  notes: str = ""


class VisualActionResult(BaseModel):
  action_id: str
  domain_action: str = ""
  target: UITarget | None = None
  confidence: Confidence = 0.0
  success: bool = False
  uncertain: bool = False
  verification: VerificationResult | None = None
  before_frame: ScreenFrame | None = None
  after_frame: ScreenFrame | None = None
  click_point: dict[str, float] | None = None
  latency_ms: int = 0
  error: str | None = None


class WindowsRpaActionRecord(BaseModel):
  action_id: str
  domain_action: str = ""
  selector_key: str | None = None
  confidence: Confidence = 0.0
  success: bool = False
  uncertain: bool = False
  verification_status: str = ""
  before_screenshot: str | None = None
  after_screenshot: str | None = None
  click_point: dict[str, float] | None = None
  latency_ms: int = 0
  timestamp_ms: int = 0
  error: str | None = None


class WindowsRpaMetrics(BaseModel):
  target_acquisition_success_total: int = 0
  target_acquisition_failure_total: int = 0
  verification_failure_total: int = 0
  uncertain_action_total: int = 0
  focus_loss_total: int = 0
  median_click_latency_ms: float = 0.0


class OperatorPreviewState(BaseModel):
  adapter_id: str
  session_id: str = ""
  status: WindowsRpaStatus = WindowsRpaStatus.OFFLINE
  automation_active: bool = False
  attachment: WindowAttachment | None = None
  live_frame: ScreenFrame | None = None
  frame_kind: PreviewFrameKind = PreviewFrameKind.NONE
  current_action: str | None = None
  current_target: UITarget | None = None
  planned_action: str | None = None
  confidence: Confidence = 0.0
  recent_actions: list[WindowsRpaActionRecord] = Field(default_factory=list)
  recent_frames: list[ScreenFrame] = Field(default_factory=list)
  metrics: WindowsRpaMetrics = Field(default_factory=WindowsRpaMetrics)
  message: str = ""
  attach_warning: str | None = None
  uia_diagnostics: UiaTreeDiagnostics | None = None
