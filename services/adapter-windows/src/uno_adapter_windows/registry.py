from __future__ import annotations

import time
from typing import Protocol
from uuid import uuid4

from uno_adapter_windows.mock_adapter import MockWindowsAdapter
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.pywinauto_adapter import PywinautoWindowsAdapter
from uno_adapter_windows.rpa.driver.window_driver import UNUSABLE_WINDOW_ERROR
from uno_adapter_windows.runtime import STALE_WINDOW_ERROR, is_windows, pywinauto_available
from uno_schemas.adapter_windows import (
  AttachWindowsAdapterRequest,
  AttachWindowsAdapterResponse,
  WindowsActionExecutionRequest,
  WindowsActionExecutionResult,
  WindowsAdapterMode,
  WindowsEvidenceBundle,
)
from uno_shared.learned_zones import LearnedZoneStore
from uno_shared.logging import get_logger

logger = get_logger("adapter-windows")

# Shared zone store instance — file-backed, persists across adapter sessions
_zone_store = LearnedZoneStore()


class WindowsAdapterSession(Protocol):
  session_id: str
  profile_id: str
  mode: WindowsAdapterMode

  async def attach(self) -> bool: ...
  async def capture_ui_tree(self) -> dict: ...
  async def capture_evidence(self, adapter_id: str) -> WindowsEvidenceBundle: ...
  async def execute(self, req: WindowsActionExecutionRequest, correlation_id: str | None) -> WindowsActionExecutionResult: ...
  async def detach(self) -> None: ...


_adapters: dict[str, WindowsAdapterSession] = {}


def get_adapter(adapter_id: str) -> WindowsAdapterSession | None:
  return _adapters.get(adapter_id)


async def attach_adapter(req: AttachWindowsAdapterRequest) -> AttachWindowsAdapterResponse:
  profile = load_profile(req.profile_id)
  stage_start = time.time()
  # Derive game_id from profile for zone store lookup
  game_id = profile.game_type or req.profile_id
  try:
    if req.mode == WindowsAdapterMode.MOCK:
      adapter: WindowsAdapterSession = MockWindowsAdapter(
        req.session_id, req.profile_id, req.window_title or "UNO Mock Test Target"
      )
      backend = "mock"
    else:
      if not is_windows():
        raise RuntimeError("pywinauto real mode requires Windows")
      if not pywinauto_available():
        raise RuntimeError("pywinauto not installed. pip install pywinauto")
      adapter = PywinautoWindowsAdapter(
        req.session_id,
        profile,
        window_title=req.window_title,
        window_handle=req.window_handle,
        window_pid=req.window_pid,
        launch_test_target_flag=req.launch_test_target and req.window_handle is None,
        capture_screenshots=req.capture_screenshots,
        zone_store=_zone_store,
        game_id=game_id,
      )
      backend = profile.preferred_backend.value

    ok = await adapter.attach()
    aid = str(uuid4())
    if ok:
      if hasattr(adapter, "bind_adapter_id"):
        adapter.bind_adapter_id(aid)
      _adapters[aid] = adapter
    title = req.window_title or ""
    if ok and isinstance(adapter, PywinautoWindowsAdapter) and adapter._window:
      try:
        title = adapter._window.window_text() or title
      except Exception:
        pass
    if not title:
      title = profile.window.title_regex or ""
    message = "attached" if ok else "attach failed — window not found"
    if (
      not ok
      and req.window_handle is not None
      and isinstance(adapter, PywinautoWindowsAdapter)
      and adapter._state.message in (STALE_WINDOW_ERROR, UNUSABLE_WINDOW_ERROR)
    ):
      message = adapter._state.message or message
    if (
      not ok
      and req.mode == WindowsAdapterMode.PYWINAUTO
      and req.launch_test_target
      and isinstance(adapter, PywinautoWindowsAdapter)
      and adapter._proc is None
    ):
      message = "launch_test_target failed — test target script not found or failed to start"
    elif not ok and req.mode == WindowsAdapterMode.PYWINAUTO and hasattr(adapter, "_state"):
      state_msg = getattr(adapter, "_state", None)
      if state_msg and getattr(state_msg, "message", ""):
        message = state_msg.message or message

    duration_ms = int((time.time() - stage_start) * 1000)
    logger.info("attach_complete", session_id=req.session_id, adapter_type="windows",
                attached=ok, duration_ms=duration_ms, message=message, window_title=title)

    return AttachWindowsAdapterResponse(
      adapter_id=aid,
      session_id=req.session_id,
      attached=ok,
      mode=req.mode,
      profile_id=req.profile_id,
      window_title=title,
      backend=backend if ok else None,
      message=message,
    )
  except Exception as exc:
    duration_ms = int((time.time() - stage_start) * 1000)
    logger.error("attach_failed", session_id=req.session_id, adapter_type="windows",
                 duration_ms=duration_ms, error=str(exc))
    return AttachWindowsAdapterResponse(
      adapter_id=str(uuid4()),
      session_id=req.session_id,
      attached=False,
      mode=req.mode,
      profile_id=req.profile_id,
      message=str(exc),
    )
