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
    handle = int(window.handle)
  bounds: dict[str, float] | None = None
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
  if not bounds_are_usable(bounds) and handle is not None:
    bounds = win32_bounds_for_handle(handle) or bounds
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


async def ensure_focus(window) -> None:
  def _focus():
    try:
      window.set_focus()
    except Exception:
      pass

  await asyncio.to_thread(_focus)


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
