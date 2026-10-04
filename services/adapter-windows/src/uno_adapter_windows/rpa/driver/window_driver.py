"""Low-level window attachment helpers."""

from __future__ import annotations

import asyncio
import time

from uno_adapter_windows.browser_attach import is_browser_host
from uno_schemas.adapter_windows import WindowAttachment

MIN_USABLE_WINDOW_PX = 50
UNUSABLE_WINDOW_ERROR = (
  "Selected game window is not visibly attachable (zero-sized, minimized, or hidden window bounds)"
)


def bounds_size(bounds: dict[str, float] | None) -> tuple[float, float]:
  if not bounds:
    return 0.0, 0.0
  return bounds["right"] - bounds["left"], bounds["bottom"] - bounds["top"]


def bounds_are_usable(bounds: dict[str, float] | None, min_px: float = MIN_USABLE_WINDOW_PX) -> bool:
  width, height = bounds_size(bounds)
  return width >= min_px and height >= min_px


def win32_bounds_for_handle(handle: int) -> dict[str, float] | None:
  try:
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    if ctypes.windll.user32.GetWindowRect(handle, ctypes.byref(rect)):
      return {
        "left": float(rect.left),
        "top": float(rect.top),
        "right": float(rect.right),
        "bottom": float(rect.bottom),
      }
  except Exception:
    return None
  return None


def read_window_bounds(window, *, window_handle: int | None = None) -> dict[str, float] | None:
  handle = window_handle
  if handle is None and hasattr(window, "handle"):
    try:
      handle = int(window.handle)
    except Exception:
      handle = None
  # Pure-ctypes GetWindowRect FIRST: this function is called from the async event
  # loop on the evidence path (via _apply_fixed_size BEFORE the screenshot), and
  # window.rectangle() is a pywinauto COM call that has been observed to hang
  # against the live animating UNO (Electron) window. A hang there blocks the
  # WHOLE loop, so the 20s /evidence backstop (an asyncio.wait_for on the same
  # loop) cannot fire and the orchestrator sees a ReadTimeout with no frame.
  # GetWindowRect is a plain user32 call that does not go through COM and returns
  # the same outer rectangle.
  bounds: dict[str, float] | None = None
  if handle is not None:
    bounds = win32_bounds_for_handle(handle)
  if not bounds_are_usable(bounds):
    try:
      rect = window.rectangle()
      bounds = {
        "left": float(rect.left),
        "top": float(rect.top),
        "right": float(rect.right),
        "bottom": float(rect.bottom),
      }
    except Exception:
      bounds = None
  return bounds


def window_bounds(window, *, window_handle: int | None = None) -> dict[str, float] | None:
  return read_window_bounds(window, window_handle=window_handle)


def _prepare_window_sync(window, *, is_browser_host: bool) -> None:
  try:
    if hasattr(window, "restore"):
      window.restore()
    elif hasattr(window, "show"):
      window.show()
  except Exception:
    pass
  try:
    if is_browser_host and hasattr(window, "maximize"):
      window.maximize()
  except Exception:
    pass
  try:
    window.set_focus()
  except Exception:
    pass


async def prepare_attached_window(
  window,
  *,
  is_browser_host: bool = False,
  window_handle: int | None = None,
) -> dict[str, float] | None:
  def _run() -> dict[str, float] | None:
    _prepare_window_sync(window, is_browser_host=is_browser_host)
    time.sleep(0.2)
    return read_window_bounds(window, window_handle=window_handle)

  return await asyncio.to_thread(_run)


async def ensure_window_usable(
  window,
  *,
  window_handle: int | None = None,
  is_browser_host: bool = False,
) -> dict[str, float]:
  bounds = await prepare_attached_window(
    window,
    is_browser_host=is_browser_host,
    window_handle=window_handle,
  )
  if not bounds_are_usable(bounds):
    raise RuntimeError(UNUSABLE_WINDOW_ERROR)
  return bounds


def window_attachment(
  window,
  backend: str,
  process_name: str | None = None,
  *,
  window_handle: int | None = None,
  expected_title: str | None = None,
  bounds: dict[str, float] | None = None,
) -> WindowAttachment:
  title = ""
  class_name = None
  focused = True
  try:
    title = window.window_text()
    class_name = window.class_name()
    focused = window.has_focus() if hasattr(window, "has_focus") else True
    if window_handle is None and hasattr(window, "handle"):
      window_handle = int(window.handle)
  except Exception:
    pass
  resolved_bounds = bounds or read_window_bounds(window, window_handle=window_handle)
  return WindowAttachment(
    window_title=title,
    class_name=class_name,
    process_name=process_name,
    backend=backend,
    bounds=resolved_bounds,
    dpi_scale=1.0,
    focused=focused,
    window_handle=window_handle,
    expected_title=expected_title,
    live_title=title,
    is_browser_host=is_browser_host(process_name, class_name),
  )


# Budget for the pre-click COM set_focus call. window.set_focus() is a pywinauto
# COM call with NO timeout of its own: on the live animating UNO (Electron) window
# it was observed to hang long enough to consume the entire 12s execute deadline
# ("execution exceeded 12s deadline", no click delivered). The focus attempt is
# best-effort anyway (the click path clamps to screen coords), so a bounded
# attempt that falls through is strictly better than an unbounded one.
_FOCUS_BUDGET_S = 3.0


async def ensure_focus(window) -> None:
  def _focus():
    try:
      window.set_focus()
    except Exception:
      pass

  try:
    # Offload to the dedicated COM-meta pool: a hung set_focus leaks its worker
    # until Windows returns, and this runs on the default pool that the
    # screenshot shares — a leaked focus thread would starve the frame capture.
    from uno_adapter_windows.runtime import _get_com_meta_executor
    loop = asyncio.get_running_loop()
    await asyncio.wait_for(
      loop.run_in_executor(_get_com_meta_executor(), _focus),
      timeout=_FOCUS_BUDGET_S,
    )
  except Exception:
    import logging
    logging.getLogger("adapter-windows").warning(
      "ensure_focus_timeout: set_focus hung >%ss — clicking without focus",
      _FOCUS_BUDGET_S,
    )


async def window_still_valid(window, expected_title: str | None = None) -> bool:
  def _check() -> bool:
    try:
      if not window.exists():
        return False
      if expected_title and expected_title not in window.window_text():
        return False
      return True
    except Exception:
      return False

  return await asyncio.to_thread(_check)


def clamp_point_to_bounds(x: float, y: float, bounds: dict[str, float] | None) -> tuple[int, int]:
  if not bounds:
    return int(x), int(y)
  left, top, right, bottom = bounds["left"], bounds["top"], bounds["right"], bounds["bottom"]
  cx = max(left + 2, min(right - 2, x))
  cy = max(top + 2, min(bottom - 2, y))
  return int(cx), int(cy)


def set_window_size_keep_position(window, width: int, height: int) -> dict[str, float] | None:
  """Resize the window to an exact size, keeping its current top-left corner.

  WHY THIS EXISTS (2026-08-27): the VLM and the heuristic both emit coordinates
  in *frame* pixels, and the executor clamps clicks to the window bounds captured
  at attach. If the game window drifts in size after attach (the user maximises
  it, the game resizes to a borderless/fullscreen mode, a display-mode change),
  the frame and the click bounds no longer agree and a "confirmed" click lands on
  the wrong card — exactly the class of confidently-wrong perception this repo
  keeps fixing. Forcing a fixed outer rectangle at attach (and re-asserting it
  before an action) keeps frame size, capture rect, and click bounds locked to one
  coordinate system. Only the size is changed, never the position, so the window
  does not jump around the screen (which would itself trigger a DWM recomposite).

  Implemented with user32.SetWindowPos (SWP_NOZORDER) rather than a pywinauto
  call: the win32 DialogWrapper exposes no set_rectangle, and Unity windows have
  been verified to honour SetWindowPos size changes.
  """
  try:
    import ctypes
    from ctypes import wintypes

    handle = None
    if window_handle_of(window) is not None:
      handle = window_handle_of(window)
    if handle is None:
      return None
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(handle, ctypes.byref(rect)):
      return None
    SWP_NOZORDER = 0x0004
    ctypes.windll.user32.SetWindowPos(
      handle, 0, int(rect.left), int(rect.top), int(width), int(height), SWP_NOZORDER
    )
    return None
  except Exception:
    return None


def window_handle_of(window) -> int | None:
  try:
    return int(window.handle) if hasattr(window, "handle") else None
  except Exception:
    return None


def assert_window_size(
  window,
  fixed_size: dict | None,
) -> None:
  """Apply a profile's `fixed_size` ({width, height}) if present. Best-effort."""
  if not fixed_size:
    return
  width = fixed_size.get("width")
  height = fixed_size.get("height")
  if not width or not height:
    return
  set_window_size_keep_position(window, int(width), int(height))
