"""Pywinauto-backed visual attended RPA adapter."""

from __future__ import annotations

import asyncio
import time

# Hard cap for the window meta (window_text/class_name) COM calls offloaded to
# the UIA-walk pool in _snapshot(). Kept small so a stuck meta call adds at most
# this much to the evidence capture; the 20s /evidence backstop then still has
# room to fire.
_WINDOW_META_BUDGET_S = 3.0

from uno_adapter_windows.browser_attach import is_browser_host, verify_browser_attach
from uno_adapter_windows.extraction import build_window_snapshot, window_snapshot_to_ui_evidence
from uno_adapter_windows.rpa.driver.window_driver import (
  bounds_are_usable,
  ensure_window_usable,
  read_window_bounds,
  window_attachment,
)
from uno_adapter_windows.rpa.executor.visual_executor import VisualRpaExecutor
from uno_adapter_windows.rpa.session_state import RpaSessionState, screen_frame_from_path
from uno_adapter_windows.runtime import (
  ARTIFACTS_DIR,
  capture_window_screenshot,
  extract_ui_tree,
  find_window,
  launch_test_target,
)
from uno_adapter_windows.uia_actionability import analyze_uia_tree
from uno_schemas.adapter_web import ReplayArtifactRef, ReplayArtifactType
from uno_schemas.adapter_windows import (
  OperatorPreviewState,
  WindowsActionExecutionRequest,
  WindowsActionExecutionResult,
  WindowsAdapterMode,
  WindowsAdapterProfile,
  WindowsEvidenceBundle,
  WindowsRpaStatus,
)
from uno_schemas.perception import ScreenshotFrame
from uno_shared.logging import get_logger

logger = get_logger("adapter-windows")


class PywinautoWindowsAdapter:
  def __init__(
    self,
    session_id: str,
    profile: WindowsAdapterProfile,
    window_title: str | None = None,
    window_handle: int | None = None,
    window_pid: int | None = None,
    launch_test_target_flag: bool = False,
    capture_screenshots: bool = True,
    zone_store=None,
    game_id: str | None = None,
  ) -> None:
    self.session_id = session_id
    self.profile = profile
    self.profile_id = profile.profile_id
    self.window_title_hint = window_title
    self.window_handle = window_handle
    self.window_pid = window_pid
    self.capture_screenshots = capture_screenshots
    self._window = None
    self._backend = profile.preferred_backend.value
    self._proc = None
    self.attached = False
    self._adapter_id = ""
    self._zone_store = zone_store
    self._game_id = game_id
    self.artifacts_dir = ARTIFACTS_DIR / session_id
    self.artifacts_dir.mkdir(parents=True, exist_ok=True)
    self._state = RpaSessionState("", session_id)
    self._executor: VisualRpaExecutor | None = None
    if launch_test_target_flag and window_handle is None:
      self._proc = launch_test_target(profile)
      if self._proc is None:
        self._state.set_status(
          WindowsRpaStatus.FAILED,
          f"launch_test_target failed — script not found for profile {profile.profile_id}",
        )
      else:
        time.sleep(0.5)

  def bind_adapter_id(self, adapter_id: str) -> None:
    self._adapter_id = adapter_id
    self._state.adapter_id = adapter_id

  async def attach(self) -> bool:
    stages = []
    self._state.set_status(WindowsRpaStatus.LOADING, "searching for window")

    # Stage 1: resolve_window
    stage_start = time.time()
    try:
      self._window, self._backend = await find_window(
        self.profile,
        self.window_title_hint,
        window_handle=self.window_handle,
        window_pid=self.window_pid,
      )
      stages.append({"stage_name": "resolve_window", "duration_ms": int((time.time() - stage_start) * 1000), "status": "ok"})
    except RuntimeError as exc:
      msg = str(exc)
      error_code = "WINDOW_NOT_FOUND" if "not found" in msg.lower() else (
        "HANDLE_INVALID" if "stale" in msg.lower() or "unusable" in msg.lower() else "RESOLVE_FAILED"
      )
      stages.append({"stage_name": "resolve_window", "duration_ms": int((time.time() - stage_start) * 1000), "status": "error", "error_code": error_code, "error_message": msg})
      self._state.set_status(WindowsRpaStatus.FAILED, msg)
      return False

    self.attached = self._window is not None
    if not self.attached:
      stages.append({"stage_name": "resolve_window", "duration_ms": int((time.time() - stage_start) * 1000), "status": "error", "error_code": "WINDOW_NOT_FOUND", "error_message": "window not found"})
      self._state.set_status(WindowsRpaStatus.FAILED, "window not found")
      return False

    # Stage 2: validate_handle
    stage_start = time.time()
    process_name = self.profile.window.process_name
    class_name = None
    try:
      from uno_adapter_windows.runtime import _process_name_for_pid
      process_name = _process_name_for_pid(self._window.process_id()) or process_name
      class_name = self._window.class_name()
    except Exception as exc:
      stages.append({"stage_name": "validate_handle", "duration_ms": int((time.time() - stage_start) * 1000), "status": "error", "error_code": "HANDLE_VALIDATION_FAILED", "error_message": str(exc)})
      self._state.set_status(WindowsRpaStatus.FAILED, str(exc))
      self.attached = False
      return False

    is_browser = is_browser_host(process_name, class_name)
    try:
      bounds = await ensure_window_usable(
        self._window,
        window_handle=self.window_handle,
        is_browser_host=is_browser,
      )
    except RuntimeError as exc:
      stages.append({"stage_name": "validate_handle", "duration_ms": int((time.time() - stage_start) * 1000), "status": "error", "error_code": "HANDLE_INVALID", "error_message": str(exc)})
      self._state.set_status(WindowsRpaStatus.FAILED, str(exc))
      self.attached = False
      return False
    stages.append({"stage_name": "validate_handle", "duration_ms": int((time.time() - stage_start) * 1000), "status": "ok"})

    # Stage 3: attach_adapter
    stage_start = time.time()
    self._state.attachment = window_attachment(
      self._window,
      self._backend,
      process_name,
      window_handle=self.window_handle,
      expected_title=self.window_title_hint,
      bounds=bounds,
    )
    await self._verify_browser_attach()
    self._executor = VisualRpaExecutor(
      self._window, self.profile, self._backend, self.artifacts_dir, self._state, self.session_id,
      bounds=bounds, zone_store=self._zone_store, game_id=self._game_id,
    )
    stages.append({"stage_name": "attach_adapter", "duration_ms": int((time.time() - stage_start) * 1000), "status": "ok"})

    if self._state.attach_warning:
      self._state.set_status(WindowsRpaStatus.UNCERTAIN, self._state.attach_warning)
    else:
      self._state.set_status(WindowsRpaStatus.ATTACHED, "window attached")

    # Stage 4: waiting_for_frame
    stage_start = time.time()
    if self._executor:
      try:
        await self._executor.capture_live_frame("attach")
        stages.append({"stage_name": "waiting_for_frame", "duration_ms": int((time.time() - stage_start) * 1000), "status": "ok"})
        if not self._state.attach_warning:
          self._state.set_status(WindowsRpaStatus.READY)
      except Exception as exc:
        stages.append({"stage_name": "waiting_for_frame", "duration_ms": int((time.time() - stage_start) * 1000), "status": "error", "error_code": "FRAME_CAPTURE_FAILED", "error_message": str(exc)})
    else:
      stages.append({"stage_name": "waiting_for_frame", "duration_ms": int((time.time() - stage_start) * 1000), "status": "skipped"})

    # Log attach summary
    total_ms = sum(s["duration_ms"] for s in stages)
    final_status = "ok" if self.attached else "error"
    logger.info("attach_summary", session_id=self.session_id, adapter_type="windows",
                total_duration_ms=total_ms, final_status=final_status, stages=stages)

    return self.attached

  def get_preview_state(self) -> OperatorPreviewState:
    return self._state.to_preview()

  async def refresh_attach_diagnostics(self) -> None:
    if not self.attached or not self._window:
      return
    if self._state.attachment:
      bounds = read_window_bounds(self._window, window_handle=self.window_handle)
      if bounds_are_usable(bounds):
        self._state.attachment.bounds = bounds
        if self._executor:
          self._executor._bounds = bounds
    await self._verify_browser_attach()

  async def _verify_browser_attach(self) -> None:
    if not self._window or not self._state.attachment:
      return
    # web_only (canvas/GPU content): the walk can never surface the in-game
    # controls and on the real UNO window it hangs every cycle — skip it and
    # verify the browser titles on an empty tree (the title checks don't need
    # nodes).
    web_only = getattr(self.profile, "match_automation", None) == "web_only"
    live_title = self._state.attachment.live_title or ""
    # window_text() is a COM call — run it off the loop with a budget (see
    # _snapshot). A hang here must never block the event loop.
    try:
      from uno_adapter_windows.runtime import _get_com_meta_executor
      loop = asyncio.get_running_loop()
      text = await asyncio.wait_for(
        loop.run_in_executor(_get_com_meta_executor(), self._window.window_text),
        timeout=_WINDOW_META_BUDGET_S,
      )
      if text:
        live_title = text
    except Exception:
      pass
    if web_only:
      nodes: list = []
      sparse = True
    else:
      nodes, _, sparse = await extract_ui_tree(self._window, self._backend)
    is_browser = bool(self._state.attachment.is_browser_host)
    diagnostics = analyze_uia_tree(nodes, sparse_tree=sparse, is_browser_host=is_browser)
    self._state.uia_diagnostics = diagnostics
    warning, _detail = verify_browser_attach(
      self.window_title_hint or self._state.attachment.expected_title,
      live_title,
      nodes,
      process_name=self._state.attachment.process_name,
      class_name=self._state.attachment.class_name,
    )
    self._state.attachment.live_title = live_title
    self._state.attachment.attach_warning = warning
    self._state.attach_warning = warning

  async def capture_ui_tree(self) -> dict:
    snap = await self._snapshot()
    return snap.model_dump()

  async def capture_evidence(self, adapter_id: str) -> WindowsEvidenceBundle:
    # ponytail: screenshot FIRST — it is the primary perception input and is
    # fast (~100ms). The UIA tree walk is secondary (confidence/chat text) and
    # is the step that can hang on a live animating game window; putting it
    # second means a hung walk can no longer gate the frame the agent reads.
    screenshot = await self._capture_screenshot_frame()
    snap = await self._snapshot()
    return WindowsEvidenceBundle(
      adapter_id=adapter_id,
      session_id=self.session_id,
      window_snapshot=snap,
      ui_evidence=window_snapshot_to_ui_evidence(snap),
      screenshot=screenshot,
      chat_messages=snap.extracted.get("chat_messages", []),
    )

  async def _capture_screenshot_frame(self) -> ScreenshotFrame | None:
    if not self.capture_screenshots or not self._window:
      return None
    if self._executor:
      path = await self._executor.capture_live_frame("evidence")
    else:
      path = await capture_window_screenshot(self._window, self.artifacts_dir, "evidence")
    if not path:
      return None
    frame = screen_frame_from_path(path, self.session_id)
    return ScreenshotFrame(
      frame_id=frame.frame_id,
      session_id=self.session_id,
      width=frame.width,
      height=frame.height,
      path=path,
      data_base64=frame.data_base64,
      captured_at_ms=frame.captured_at_ms,
    )

  async def _snapshot(self):
    title = self.window_title_hint or self.profile.window.title_regex or "unknown"
    class_name = None
    process_name = self.profile.window.process_name
    nodes = []
    truncated = sparse = True
    if self._window:
      # 2026-08-29: match_automation="web_only" means the game content is
      # canvas/GPU-drawn — UIA cannot see cards or buttons, so a walk here only
      # hangs (6s hard cap per cycle on the real UNO window) and leaks worker
      # threads into the walk pool. The screenshot is the ONLY useful signal;
      # skip the walk (and the COM window_text/class_name meta calls that feed
      # nothing downstream) entirely.
      if getattr(self.profile, "match_automation", None) != "web_only":
        # window_text()/class_name() are pywinauto COM calls. They used to run
        # synchronously inside this coroutine — a hang on the live animating UNO
        # window blocked the WHOLE event loop, so the 20s /evidence backstop
        # (asyncio.wait_for on the same loop) could never fire and the orchestrator
        # observed an opaque ReadTimeout with no frame. Offload to the dedicated
        # COM-meta pool (separate from the UIA-walk pool) with a small cap: a stuck
        # call leaks a thread but can never stall the walk or the screenshot.
        try:
          from uno_adapter_windows.runtime import _get_com_meta_executor
          loop = asyncio.get_running_loop()
          title, class_name = await asyncio.wait_for(
            loop.run_in_executor(_get_com_meta_executor(), self._window_meta),
            timeout=_WINDOW_META_BUDGET_S,
          )
        except Exception:
          pass
        nodes, truncated, sparse = await extract_ui_tree(self._window, self._backend)
    return build_window_snapshot(
      self.profile, nodes, title, self._backend, class_name, process_name, truncated, sparse
    )

  def _window_meta(self) -> tuple[str, str | None]:
    title = None
    class_name = None
    try:
      title = self._window.window_text() or None
    except Exception:
      pass
    try:
      class_name = self._window.class_name() or None
    except Exception:
      pass
    return (title or self.window_title_hint or self.profile.window.title_regex or "unknown"), class_name

  async def execute(
    self, req: WindowsActionExecutionRequest, correlation_id: str | None = None
  ) -> WindowsActionExecutionResult:
    if not self._window or not self.attached or not self._executor:
      return WindowsActionExecutionResult(
        success=False,
        action_type=req.action_type,
        error="not attached",
        correlation_id=correlation_id,
        uncertain=True,
      )

    req = req.model_copy(update={"capture_screenshots": req.capture_screenshots or True})
    visual = await self._executor.execute_request(req)
    artifacts: list[ReplayArtifactRef] = []
    if visual.before_frame:
      artifacts.append(ReplayArtifactRef(
        artifact_id=visual.action_id + "-before",
        artifact_type=ReplayArtifactType.SCREENSHOT,
        path=visual.before_frame.path,
      ))
    if visual.after_frame:
      artifacts.append(ReplayArtifactRef(
        artifact_id=visual.action_id + "-after",
        artifact_type=ReplayArtifactType.SCREENSHOT,
        path=visual.after_frame.path,
      ))

    return WindowsActionExecutionResult(
      success=visual.success,
      action_type=req.action_type,
      target_metadata={
        "selector_key": req.selector_key,
        "domain_action": visual.domain_action,
        "method": visual.target.method.value if visual.target else None,
        "backend": self._backend,
      },
      error=visual.error,
      warnings=[visual.verification.notes] if visual.verification and visual.verification.notes else [],
      duration_ms=visual.latency_ms,
      screenshot_before=visual.before_frame.path if visual.before_frame else None,
      screenshot_after=visual.after_frame.path if visual.after_frame else None,
      click_point=visual.click_point,
      confidence=visual.confidence,
      uncertain=visual.uncertain,
      verification=visual.verification,
      domain_action=visual.domain_action,
      artifact_refs=artifacts,
      correlation_id=correlation_id,
    )

  async def detach(self) -> None:
    self._state.set_status(WindowsRpaStatus.STOPPED)
    if self._proc:
      self._proc.terminate()
      self._proc = None
    self.attached = False
    self._window = None
    self._executor = None

  @property
  def mode(self) -> WindowsAdapterMode:
    return WindowsAdapterMode.PYWINAUTO

  @property
  def backend(self) -> str:
    return self._backend
