"""In-memory operator preview and action history."""

from __future__ import annotations

import statistics
import time
from uuid import uuid4

from uno_schemas.adapter_windows import (
  OperatorPreviewState,
  PreviewFrameKind,
  ScreenFrame,
  UiaTreeDiagnostics,
  UITarget,
  VisualActionResult,
  WindowAttachment,
  WindowsRpaActionRecord,
  WindowsRpaMetrics,
  WindowsRpaStatus,
)


class RpaSessionState:
  def __init__(self, adapter_id: str, session_id: str) -> None:
    self.adapter_id = adapter_id
    self.session_id = session_id
    self.status = WindowsRpaStatus.LOADING
    self.automation_active = False
    self.attachment: WindowAttachment | None = None
    self.live_frame: ScreenFrame | None = None
    self.frame_kind: PreviewFrameKind = PreviewFrameKind.NONE
    self.current_action: str | None = None
    self.current_target: UITarget | None = None
    self.planned_action: str | None = None
    self.confidence: float = 0.0
    self.message = ""
    self.attach_warning: str | None = None
    self.uia_diagnostics: UiaTreeDiagnostics | None = None
    self._actions: list[WindowsRpaActionRecord] = []
    self._frames: list[ScreenFrame] = []
    self._latencies: list[int] = []
    self.metrics = WindowsRpaMetrics()

  def set_status(self, status: WindowsRpaStatus, message: str = "") -> None:
    self.status = status
    if message:
      self.message = message

  def push_frame(self, frame: ScreenFrame, *, kind: PreviewFrameKind = PreviewFrameKind.LIVE) -> None:
    self.live_frame = frame
    self.frame_kind = kind
    self._frames.append(frame)
    self._frames = self._frames[-20:]

  def push_synthetic_frame(self, frame: ScreenFrame) -> None:
    self.push_frame(frame, kind=PreviewFrameKind.SYNTHETIC)

  def record_action(self, result: VisualActionResult, selector_key: str | None) -> None:
    rec = WindowsRpaActionRecord(
      action_id=result.action_id,
      domain_action=result.domain_action,
      selector_key=selector_key,
      confidence=result.confidence,
      success=result.success,
      uncertain=result.uncertain,
      verification_status=result.verification.status if result.verification else "",
      before_screenshot=result.before_frame.path if result.before_frame else None,
      after_screenshot=result.after_frame.path if result.after_frame else None,
      click_point=result.click_point,
      latency_ms=result.latency_ms,
      timestamp_ms=int(time.time() * 1000),
      error=result.error,
    )
    self._actions.append(rec)
    self._actions = self._actions[-50:]
    self._latencies.append(result.latency_ms)
    self._latencies = self._latencies[-100:]
    if result.success:
      self.metrics.target_acquisition_success_total += 1
    else:
      self.metrics.target_acquisition_failure_total += 1
    if result.uncertain:
      self.metrics.uncertain_action_total += 1
    if result.verification and not result.verification.passed:
      self.metrics.verification_failure_total += 1
    if self._latencies:
      self.metrics.median_click_latency_ms = float(statistics.median(self._latencies))

  def to_preview(self) -> OperatorPreviewState:
    return OperatorPreviewState(
      adapter_id=self.adapter_id,
      session_id=self.session_id,
      status=self.status,
      automation_active=self.automation_active,
      attachment=self.attachment,
      live_frame=self.live_frame,
      frame_kind=self.frame_kind,
      current_action=self.current_action,
      current_target=self.current_target,
      planned_action=self.planned_action,
      confidence=self.confidence,
      recent_actions=list(reversed(self._actions[-10:])),
      recent_frames=list(reversed(self._frames[-6:])),
      metrics=self.metrics,
      message=self.message,
      attach_warning=self.attach_warning,
      uia_diagnostics=self.uia_diagnostics,
    )


def screen_frame_from_path(path: str, session_id: str, width: int = 0, height: int = 0) -> ScreenFrame:
  import base64
  from pathlib import Path

  p = Path(path)
  raw = p.read_bytes()
  w, h = width, height
  if w <= 0 or h <= 0:
    try:
      from PIL import Image

      with Image.open(p) as img:
        w, h = img.size
    except Exception:
      w, h = max(w, 1), max(h, 1)
  return ScreenFrame(
    frame_id=str(uuid4()),
    path=path,
    captured_at_ms=int(time.time() * 1000),
    width=w,
    height=h,
    data_base64=base64.b64encode(raw).decode("ascii"),
  )
