"""Visual RPA execution pipeline: locate -> act -> verify."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from uno_adapter_windows.rpa.driver.input_driver import (
  humanized_move_and_click,
  press_keys,
  type_text,
)
from uno_adapter_windows.rpa.driver.window_driver import (
  clamp_point_to_bounds,
  ensure_focus,
  window_bounds,
)
from uno_adapter_windows.rpa.perception.target_locator import locate_selector
from uno_adapter_windows.rpa.session_state import RpaSessionState, screen_frame_from_path
from uno_adapter_windows.rpa.verification.ui_verifier import verify_screenshot_transition
from uno_adapter_windows.runtime import capture_window_screenshot, extract_ui_tree
from uno_adapter_windows.uia_actionability import (
  analyze_uia_tree,
  browser_match_card_message,
  missing_target_message,
  should_skip_uia_card_lookup,
)
from uno_schemas.adapter_windows import (
  TargetAcquisitionMethod,
  UITarget,
  VerificationResult,
  VisualActionRequest,
  VisualActionResult,
  WindowsActionExecutionRequest,
  WindowsActionType,
  WindowsAdapterProfile,
  WindowsRpaStatus,
)


class VisualRpaExecutor:
  def __init__(
    self,
    window,
    profile: WindowsAdapterProfile,
    backend: str,
    artifacts_dir: Path,
    state: RpaSessionState,
    session_id: str,
    bounds: dict[str, float] | None = None,
  ) -> None:
    self._window = window
    self._profile = profile
    self._backend = backend
    self._artifacts_dir = artifacts_dir
    self._state = state
    self._session_id = session_id
    self._bounds = bounds or window_bounds(window)

  async def capture_live_frame(self, label: str = "live") -> str | None:
    path = await capture_window_screenshot(self._window, self._artifacts_dir, label)
    if path:
      frame = screen_frame_from_path(path, self._session_id)
      self._state.push_frame(frame)
    return path

  async def execute_request(
    self,
    req: WindowsActionExecutionRequest,
  ) -> VisualActionResult:
    action_id = str(uuid4())
    domain = req.domain_action or req.selector_key or req.action_type.value
    self._state.automation_active = True
    self._state.planned_action = domain
    self._state.set_status(WindowsRpaStatus.SEARCHING)

    vreq = VisualActionRequest(
      domain_action=domain,
      selector_key=req.selector_key,
      action_type=req.action_type,
      text=req.text,
      keys=req.keys,
      min_confidence=req.min_confidence,
      allow_coordinate_fallback=req.allow_coordinate_fallback,
      capture_screenshots=req.capture_screenshots,
      timeout_ms=req.timeout_ms,
    )
    return await self._execute_visual(action_id, vreq)

  async def _execute_visual(self, action_id: str, req: VisualActionRequest) -> VisualActionResult:
    start = time.perf_counter()
    before_path = after_path = None
    before_frame = after_frame = None

    if req.capture_screenshots:
      before_path = await self.capture_live_frame("before")
      if before_path:
        before_frame = screen_frame_from_path(before_path, self._session_id)

    nodes, _, sparse = await extract_ui_tree(self._window, self._backend)
    is_browser = bool(self._state.attachment and self._state.attachment.is_browser_host)
    diagnostics = analyze_uia_tree(nodes, sparse_tree=sparse, is_browser_host=is_browser)
    self._state.uia_diagnostics = diagnostics
    skip_uia = should_skip_uia_card_lookup(
      is_browser,
      req.selector_key,
      match_automation=getattr(self._profile, "match_automation", None),
    )

    allowed_keys = set(self._profile.selectors.keys()) | set(self._profile.action_mappings.keys())
    allowed_keys |= {"draw", "play_red_five"}

    import logging
    _audit = logging.getLogger("adapter-windows.audit")

    if req.selector_key and req.selector_key not in allowed_keys:
      err = f"selector_key '{req.selector_key}' not in profile allowlist"
      _audit.warning(
        "action_rejected adapter=windows session=%s selector_key=%s reason=%s",
        self._session_id, req.selector_key, err,
      )
      self._state.set_status(WindowsRpaStatus.UNCERTAIN, err)
      return VisualActionResult(
        action_id=action_id,
        domain_action=req.domain_action,
        target=None,
        confidence=0.0,
        success=False,
        uncertain=True,
        verification=VerificationResult(passed=False, status="rejected", notes=err),
        before_frame=before_frame,
        latency_ms=int((time.perf_counter() - start) * 1000),
        error=err,
      )

    target: UITarget | None = None
    if req.selector_key and not skip_uia:
      target = locate_selector(
        req.selector_key,
        self._profile,
        nodes,
        allow_coordinate_fallback=req.allow_coordinate_fallback,
        window_bounds=self._bounds,
      )

    self._state.current_action = req.domain_action
    self._state.current_target = target
    self._state.confidence = target.confidence if target else 0.0

    if not target:
      if skip_uia:
        err = browser_match_card_message(diagnostics)
      else:
        err = missing_target_message(
          diagnostics,
          req.selector_key,
          is_browser_host=is_browser,
        )
      self._state.set_status(WindowsRpaStatus.UNCERTAIN, err)
      return VisualActionResult(
        action_id=action_id,
        domain_action=req.domain_action,
        target=None,
        confidence=0.0,
        success=False,
        uncertain=True,
        verification=VerificationResult(passed=False, status="not_found", notes=err),
        before_frame=before_frame,
        latency_ms=int((time.perf_counter() - start) * 1000),
        error=err,
      )

    if target.confidence < req.min_confidence:
      self._state.set_status(
        WindowsRpaStatus.UNCERTAIN,
        f"target confidence {target.confidence:.2f} below threshold {req.min_confidence:.2f}",
      )
      return VisualActionResult(
        action_id=action_id,
        domain_action=req.domain_action,
        target=target,
        confidence=target.confidence,
        success=False,
        uncertain=True,
        verification=VerificationResult(passed=False, status="low_confidence", notes="refused to click"),
        before_frame=before_frame,
        latency_ms=int((time.perf_counter() - start) * 1000),
        error="confidence below threshold",
      )

    if not target.click_point:
      return VisualActionResult(
        action_id=action_id,
        domain_action=req.domain_action,
        target=target,
        confidence=target.confidence,
        success=False,
        uncertain=True,
        before_frame=before_frame,
        latency_ms=int((time.perf_counter() - start) * 1000),
        error="no click point",
      )

    self._state.set_status(WindowsRpaStatus.ACTING)
    await ensure_focus(self._window)
    click_x, click_y = target.click_point["x"], target.click_point["y"]
    error: str | None = None
    try:
      if req.action_type in (WindowsActionType.CLICK, WindowsActionType.CLICK_INPUT):
        if target.method == TargetAcquisitionMethod.UIA and target.title:
          await self._click_uia_element(target)
        else:
          cx, cy = await humanized_move_and_click(click_x, click_y, self._bounds)
          click_x, click_y = float(cx), float(cy)
      elif req.action_type == WindowsActionType.TYPE:
        await self._click_uia_element(target)
        await type_text(req.text or "")
      elif req.action_type == WindowsActionType.SEND_KEYS:
        await ensure_focus(self._window)
        await press_keys(req.keys or "")
      elif req.action_type == WindowsActionType.SET_FOCUS:
        await self._click_uia_element(target)
      else:
        cx, cy = await humanized_move_and_click(click_x, click_y, self._bounds)
        click_x, click_y = float(cx), float(cy)
    except Exception as exc:
      error = str(exc)

    _audit.info(
      "action_executed adapter=windows session=%s selector_key=%s domain=%s method=%s "
      "confidence=%.2f click=(%s,%s) success=%s error=%s",
      self._session_id, req.selector_key, req.domain_action,
      target.method.value if target else "none",
      target.confidence if target else 0.0,
      int(click_x), int(click_y),
      error is None, error,
    )

    self._state.set_status(WindowsRpaStatus.VERIFYING)
    verification = VerificationResult(passed=False, status="skipped")
    if req.capture_screenshots and not error:
      after_path = await self.capture_live_frame("after")
      if after_path:
        after_frame = screen_frame_from_path(after_path, self._session_id)
      verification = verify_screenshot_transition(before_path, after_path)

    success = error is None
    uncertain = error is None and target.confidence < 0.7
    if error:
      self._state.set_status(WindowsRpaStatus.FAILED, error)
    elif uncertain:
      self._state.set_status(WindowsRpaStatus.UNCERTAIN, verification.notes or "low target confidence")
    elif not verification.passed and verification.status not in ("skipped",):
      self._state.set_status(WindowsRpaStatus.READY, verification.notes or "action completed")
    else:
      self._state.set_status(WindowsRpaStatus.READY)

    result = VisualActionResult(
      action_id=action_id,
      domain_action=req.domain_action,
      target=target,
      confidence=target.confidence,
      success=success,
      uncertain=uncertain,
      verification=verification,
      before_frame=before_frame,
      after_frame=after_frame,
      click_point={"x": click_x, "y": click_y},
      latency_ms=int((time.perf_counter() - start) * 1000),
      error=error,
    )
    self._state.record_action(result, req.selector_key)
    self._state.automation_active = False
    self._state.current_action = None
    return result

  async def _click_uia_element(self, target: UITarget) -> None:
    allowed_titles = set()
    allowed_auto_ids = set()
    for sel in self._profile.selectors.values():
      if sel.title:
        allowed_titles.add(sel.title)
      if sel.auto_id:
        allowed_auto_ids.add(sel.auto_id)
    for title in self._profile.action_mappings.values():
      if title:
        allowed_titles.add(title)

    def _click():
      w = self._window
      el = None
      if target.auto_id and target.auto_id in allowed_auto_ids:
        el = w.child_window(auto_id=target.auto_id, found_index=0)
      elif target.title and target.title in allowed_titles:
        el = w.child_window(title=target.title, found_index=0)
      if el:
        el.click_input()
        return
      if target.click_point:
        x, y = target.click_point["x"], target.click_point["y"]
        cx, cy = clamp_point_to_bounds(x, y, self._bounds)
        from pywinauto import mouse
        mouse.click(button="left", coords=(cx, cy))

    import asyncio
    await asyncio.to_thread(_click)
