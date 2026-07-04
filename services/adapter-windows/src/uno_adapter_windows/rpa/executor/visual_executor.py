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
    zone_store=None,
    game_id: str | None = None,
  ) -> None:
    self._window = window
    self._profile = profile
    self._backend = backend
    self._artifacts_dir = artifacts_dir
    self._state = state
    self._session_id = session_id
    self._bounds = bounds or window_bounds(window)
    self._client_bounds = self._resolve_client_bounds()
    self._zone_store = zone_store
    self._game_id = game_id

  def _resolve_client_bounds(self) -> dict[str, float] | None:
    """Get client area bounds (content-only, excluding title bar / borders)."""
    try:
      import ctypes
      from ctypes import wintypes
      handle = int(self._window.handle) if hasattr(self._window, "handle") else None
      if not handle:
        return None
      client_rect = wintypes.RECT()
      if not ctypes.windll.user32.GetClientRect(handle, ctypes.byref(client_rect)):
        return None
      wl = self._bounds["left"] if self._bounds else 0
      wt = self._bounds["top"] if self._bounds else 0
      return {
        "left": wl + float(client_rect.left),
        "top": wt + float(client_rect.top),
        "right": wl + float(client_rect.right),
        "bottom": wt + float(client_rect.bottom),
      }
    except Exception:
      return None

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

    # Grounded CV click: a screenshot-space target was supplied (detected card
    # coordinate). Click it directly — this is the path that plays the right card
    # on a canvas/Electron game where UIA has nothing to locate.
    if req.target_x is not None and req.target_y is not None:
      return await self._execute_grounded_click(action_id, req)

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
    from uno_adapter_windows.rpa.perception.target_locator import ResolutionTrace
    resolution_trace = ResolutionTrace()

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
    allowed_keys |= {"draw", "play_red_five", "choose_color"}

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
        client_bounds=self._client_bounds,
        game_id=self._game_id,
        zone_store=self._zone_store,
        trace=resolution_trace,
      )

    # ── Color chooser: detect color buttons and pick the right one ──
    if req.domain_action == "choose_color" or req.selector_key == "choose_color":
      color_buttons = self._find_color_buttons(nodes)
      chosen_color = self._extract_chosen_color(req)
      if color_buttons and chosen_color:
        color_target = self._pick_color_button(color_buttons, chosen_color)
        if color_target:
          target = color_target
          _audit.info(
            "color_chooser_detected adapter=windows session=%s color=%s button=%s",
            self._session_id, chosen_color, color_target.title or color_target.auto_id,
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
      "confidence=%.2f click=(%s,%s) success=%s error=%s resolution=%s",
      self._session_id, req.selector_key, req.domain_action,
      target.method.value if target else "none",
      target.confidence if target else 0.0,
      int(click_x), int(click_y),
      error is None, error, resolution_trace.summary(),
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

    # ── Phase 1: Record provisional observation (click dispatched) ──
    # This is a WEAK signal — only records that we attempted this action.
    # Does NOT promote confidence.  Verification comes next.
    if self._zone_store and self._game_id and target and req.selector_key:
      try:
        from uno_schemas.learned_zones import BoundingBox, Resolution
        res = Resolution(
          width=int(self._bounds.get("right", 0) - self._bounds.get("left", 0)),
          height=int(self._bounds.get("bottom", 0) - self._bounds.get("top", 0)),
        ) if self._bounds else Resolution(width=0, height=0)
        bb = BoundingBox(
          left=target.bounds["left"], top=target.bounds["top"],
          right=target.bounds["right"], bottom=target.bounds["bottom"],
        ) if target.bounds else BoundingBox(left=0, top=0, right=0, bottom=0)
        self._zone_store.record_provisional(
          game_id=self._game_id,
          profile_id=self._profile.profile_id,
          selector_key=req.selector_key,
          bounding_box=bb,
          click_point=target.click_point or {"x": click_x, "y": click_y},
          resolution=res,
          semantic_guess=req.domain_action,
        )
      except Exception:
        pass  # don't break execution if zone recording fails

    # ── Phase 2: Record verified outcome (after screenshot comparison) ──
    # This is the STRONG signal that promotes or demotes confidence.
    if self._zone_store and self._game_id and req.selector_key and verification.status not in ("skipped",):
      try:
        verified_success = success and verification.passed
        self._zone_store.record_verified_outcome(
          game_id=self._game_id,
          profile_id=self._profile.profile_id,
          selector_key=req.selector_key,
          success=verified_success,
        )
      except Exception:
        pass

    return result

  async def _screenshot_to_screen(self, sx: float, sy: float, frame_path: str | None) -> tuple[int, int]:
    """Map a SCREENSHOT-pixel point to an absolute SCREEN point.

    The captured frame corresponds to the window rectangle, so we scale by
    (window_size / frame_size) to survive DPI / capture scaling, then offset by
    the window origin. Falls back to a 1:1 offset if the frame size is unknown.
    """
    left = self._bounds.get("left", 0) if self._bounds else 0
    top = self._bounds.get("top", 0) if self._bounds else 0
    win_w = (self._bounds.get("right", 0) - left) if self._bounds else 0
    win_h = (self._bounds.get("bottom", 0) - top) if self._bounds else 0
    scale_x = scale_y = 1.0
    if frame_path:
      try:
        from PIL import Image
        with Image.open(frame_path) as im:
          fw, fh = im.size
        if fw > 0 and fh > 0 and win_w > 0 and win_h > 0:
          scale_x, scale_y = win_w / fw, win_h / fh
      except Exception:
        pass
    return int(left + sx * scale_x), int(top + sy * scale_y)

  async def _execute_grounded_click(
    self, action_id: str, req: WindowsActionExecutionRequest,
  ) -> VisualActionResult:
    start = time.perf_counter()
    before_path = after_path = None
    before_frame = after_frame = None
    if req.capture_screenshots:
      before_path = await self.capture_live_frame("before")
      if before_path:
        before_frame = screen_frame_from_path(before_path, self._session_id)

    screen_x, screen_y = await self._screenshot_to_screen(
      float(req.target_x), float(req.target_y), before_path,
    )
    self._state.set_status(WindowsRpaStatus.ACTING)
    error: str | None = None
    try:
      await ensure_focus(self._window)
      cx, cy = await humanized_move_and_click(screen_x, screen_y, self._bounds)
      screen_x, screen_y = int(cx), int(cy)
    except Exception as exc:
      error = str(exc)

    import logging
    logging.getLogger("adapter-windows.audit").info(
      "grounded_click adapter=windows session=%s domain=%s screenshot=(%s,%s) screen=(%s,%s) success=%s error=%s",
      self._session_id, req.domain_action, req.target_x, req.target_y,
      screen_x, screen_y, error is None, error,
    )

    self._state.set_status(WindowsRpaStatus.VERIFYING)
    verification = VerificationResult(passed=False, status="skipped")
    if req.capture_screenshots and not error:
      after_path = await self.capture_live_frame("after")
      if after_path:
        after_frame = screen_frame_from_path(after_path, self._session_id)
      verification = verify_screenshot_transition(before_path, after_path)

    self._state.set_status(WindowsRpaStatus.READY if error is None else WindowsRpaStatus.FAILED, error or "")
    target = UITarget(
      selector_key=req.selector_key or req.domain_action,
      label=f"cv:{req.domain_action}",
      method=TargetAcquisitionMethod.COORDINATE,
      confidence=0.7,
      bounds=None,
      click_point={"x": float(screen_x), "y": float(screen_y)},
    )
    result = VisualActionResult(
      action_id=action_id,
      domain_action=req.domain_action,
      target=target,
      confidence=0.7,
      success=error is None,
      uncertain=False,
      verification=verification,
      before_frame=before_frame,
      after_frame=after_frame,
      click_point={"x": float(screen_x), "y": float(screen_y)},
      latency_ms=int((time.perf_counter() - start) * 1000),
      error=error,
    )
    self._state.record_action(result, req.selector_key)
    self._state.automation_active = False
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

  def _find_color_buttons(self, nodes: list) -> list[UITarget]:
    """Scan UIA nodes for color chooser buttons (red, blue, green, yellow)."""
    from uno_adapter_windows.rpa.perception.target_locator import parse_color_buttons
    return parse_color_buttons(nodes)

  def _extract_chosen_color(self, req: WindowsActionExecutionRequest) -> str | None:
    """Extract the chosen color from the action request.

    Checks text field first, then falls back to domain_action parsing.
    """
    if req.text:
      color = req.text.lower().strip()
      if color in ("red", "blue", "green", "yellow"):
        return color
    # Try to extract from domain_action like "choose_color_red"
    if req.domain_action:
      for color in ("red", "blue", "green", "yellow"):
        if color in req.domain_action.lower():
          return color
    return None

  def _pick_color_button(self, buttons: list[UITarget], color: str) -> UITarget | None:
    """Pick the matching color button from detected buttons."""
    color = color.lower()
    for btn in buttons:
      btn_color = (btn.title or btn.auto_id or "").lower()
      if color in btn_color:
        return btn
    # Fallback: try semantic_guess
    for btn in buttons:
      if hasattr(btn, "semantic_guess") and color in (btn.semantic_guess or "").lower():
        return btn
    return None
