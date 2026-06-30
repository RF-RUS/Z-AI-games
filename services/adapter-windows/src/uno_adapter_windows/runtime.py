"""Pywinauto runtime utilities."""

from __future__ import annotations

import asyncio
import base64
import re
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from uno_adapter_windows.browser_attach import browser_candidate_warning
from uno_schemas.adapter_windows import (
  UiNodeSnapshot,
  WindowCandidate,
  WindowsAdapterProfile,
)

ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "artifacts"
MAX_NODES = 200
STALE_WINDOW_ERROR = "Selected game window is no longer available"


def is_windows() -> bool:
  return sys.platform == "win32"


def pywinauto_available() -> bool:
  if not is_windows():
    return False
  try:
    import pywinauto  # noqa: F401
    return True
  except ImportError:
    return False


def launch_test_target(profile: WindowsAdapterProfile) -> subprocess.Popen | None:
  if not profile.test_target_script:
    return None
  script = Path(__file__).resolve().parents[2] / profile.test_target_script
  if not script.exists():
    return None
  return subprocess.Popen([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _process_name_for_pid(pid: int | None) -> str | None:
  if not pid or sys.platform != "win32":
    return None
  try:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
      return None
    buf = ctypes.create_unicode_buffer(512)
    size = wintypes.DWORD(len(buf))
    try:
      if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
        return Path(buf.value).name
    finally:
      kernel32.CloseHandle(handle)
  except Exception:
    return None
  return None


async def list_window_candidates() -> list[WindowCandidate]:
  if not pywinauto_available():
    return []

  def _list_win32() -> list[WindowCandidate]:
    """Enumerate windows using Win32 API directly.

    pywinauto.Desktop(backend="uia").windows() does NOT enumerate
    some protected/game processes (e.g. UNO.exe). Win32 EnumWindows
    enumerates all top-level visible windows regardless of UIA support.
    """
    import ctypes
    from ctypes import wintypes

    EnumWindows = ctypes.windll.user32.EnumWindows
    GetWindowTextW = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId

    out: list[WindowCandidate] = []
    seen_handles: set[int] = set()

    def _enum_callback(hwnd, _lparam):
      try:
        pid = ctypes.c_ulong()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = GetWindowTextLengthW(hwnd)
        if length <= 0:
          return True  # skip empty titles
        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if not title.strip():
          return True

        handle = int(hwnd)
        if handle in seen_handles:
          return True
        seen_handles.add(handle)

        pid_val = pid.value
        process_name = _process_name_for_pid(pid_val)
        # Get class name — may fail for protected processes
        try:
          class_name_buf = ctypes.create_unicode_buffer(256)
          ctypes.windll.user32.GetClassNameW(hwnd, class_name_buf, 256)
          class_name = class_name_buf.value
        except Exception:
          class_name = ""

        is_visible = bool(IsWindowVisible(hwnd))
        if not is_visible:
          return True  # skip invisible windows

        out.append(WindowCandidate(
          handle=handle,
          title=title,
          pid=pid_val,
          process_name=process_name,
          class_name=class_name,
          is_visible=True,
          is_focused=False,
          is_browser_host=browser_candidate_warning(process_name, class_name) is not None,
          attach_warning=browser_candidate_warning(process_name, class_name),
        ))
      except Exception:
        pass
      return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    EnumWindows(WNDENUMPROC(_enum_callback), 0)

    out.sort(key=lambda c: c.title.lower())
    return out[:100]

  return await asyncio.to_thread(_list_win32)


def _connect_handle(backend: str, handle: int, pid: int | None):
  from pywinauto import Application

  app = Application(backend=backend).connect(handle=handle)
  win = app.window(handle=handle)
  if not win.exists():
    raise RuntimeError(STALE_WINDOW_ERROR)
  if pid is not None and win.process_id() != pid:
    raise RuntimeError(STALE_WINDOW_ERROR)
  return win


async def connect_window_by_handle(
  profile: WindowsAdapterProfile,
  handle: int,
  pid: int | None = None,
) -> tuple[object, str]:
  backends = [profile.preferred_backend.value]
  if profile.fallback_backend:
    backends.append(profile.fallback_backend.value)
  last_error: Exception | None = None
  for backend in backends:
    try:
      win = await asyncio.to_thread(_connect_handle, backend, handle, pid)
      return win, backend
    except Exception as exc:
      last_error = exc
  if isinstance(last_error, RuntimeError) and str(last_error) == STALE_WINDOW_ERROR:
    raise last_error
  raise RuntimeError(STALE_WINDOW_ERROR) from last_error


def _node_from_element(element, depth: int, node_idx: list[int]) -> UiNodeSnapshot | None:
  try:
    node_idx[0] += 1
    rect = element.rectangle()
    return UiNodeSnapshot(
      node_id=f"n{node_idx[0]}",
      control_type=getattr(element, "friendly_class_name", lambda: None)() or element.element_info.control_type,
      name=element.window_text() or None,
      auto_id=getattr(element.element_info, "automation_id", None) or None,
      class_name=element.class_name(),
      bounds={"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
      enabled=element.is_enabled() if hasattr(element, "is_enabled") else None,
      visible=element.is_visible() if hasattr(element, "is_visible") else None,
      depth=depth,
    )
  except Exception:
    return None


async def extract_ui_tree(window, backend: str) -> tuple[list[UiNodeSnapshot], bool, bool]:
  def _walk() -> tuple[list[UiNodeSnapshot], bool, bool]:
    nodes: list[UiNodeSnapshot] = []
    truncated = False
    sparse = True
    node_idx = [0]

    def walk(element, depth: int) -> None:
      nonlocal truncated, sparse
      if len(nodes) >= MAX_NODES:
        truncated = True
        return
      node = _node_from_element(element, depth, node_idx)
      if node:
        nodes.append(node)
        if node.name or node.auto_id:
          sparse = False
      try:
        for child in element.children():
          walk(child, depth + 1)
          if truncated:
            return
      except Exception:
        pass

    try:
      walk(window, 0)
    except Exception:
      sparse = True
    return nodes, truncated, sparse

  return await asyncio.to_thread(_walk)


async def find_window(
  profile: WindowsAdapterProfile,
  title_hint: str | None = None,
  *,
  window_handle: int | None = None,
  window_pid: int | None = None,
):
  if window_handle is not None:
    return await connect_window_by_handle(profile, window_handle, window_pid)

  backends = [profile.preferred_backend.value]
  if profile.fallback_backend:
    backends.append(profile.fallback_backend.value)

  deadline = time.time() + profile.readiness_timeout_ms / 1000
  last_error: Exception | None = None
  while time.time() < deadline:
    for backend in backends:
      try:
        win = await _find_with_backend(profile, backend, title_hint)
        if win:
          return win, backend
      except Exception as exc:
        last_error = exc
    await asyncio.sleep(0.25)
  raise RuntimeError(f"window not found: {last_error}")


async def _find_with_backend(profile: WindowsAdapterProfile, backend: str, title_hint: str | None):
  def _find():
    from pywinauto import Desktop
    desktop = Desktop(backend=backend)
    candidates = []
    for w in desktop.windows():
      title = w.window_text()
      if not title:
        continue
      if profile.window.exclude_title_regex and re.search(profile.window.exclude_title_regex, title, re.I):
        continue
      if title_hint and title_hint not in title:
        continue
      if title_hint and title_hint in title:
        candidates.append(w)
        continue
      if profile.window.title_regex and re.search(profile.window.title_regex, title, re.I):
        if profile.window.class_name and w.class_name() != profile.window.class_name:
          continue
        candidates.append(w)
    if not candidates:
      return None
    for w in candidates:
      try:
        if w.has_focus():
          return w
      except Exception:
        pass
    return candidates[0]

  return await asyncio.to_thread(_find)


async def capture_window_screenshot(window, artifacts_dir: Path, label: str) -> str | None:
  """Capture screenshot of a window. Tries multiple backends for compatibility.

  Priority order:
  1. pywinauto capture_as_image (works for standard Win32 windows)
  2. PIL ImageGrab (screen region capture)
  3. Win32 PrintWindow (works for some protected windows)
  4. Win32 BitBlt (works for Unity/DirectX/OpenGL games)
  """
  def _shot() -> str | None:
    hwnd = int(window.handle)

    # Method 1: pywinauto capture_as_image
    try:
      img = window.capture_as_image()
      path = artifacts_dir / f"{label}-{int(time.time()*1000)}.png"
      img.save(path)
      return str(path)
    except Exception:
      pass

    # Method 2: PIL ImageGrab (screen region)
    try:
      from PIL import ImageGrab
      rect = window.rectangle()
      img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
      path = artifacts_dir / f"{label}-{int(time.time()*1000)}.png"
      img.save(path)
      return str(path)
    except Exception:
      pass

    # Method 3: Win32 PrintWindow (works for some protected windows)
    try:
      import ctypes
      import ctypes.wintypes
      from ctypes import Structure, c_long, c_ulong, c_ushort

      from PIL import Image

      class BITMAPINFOHEADER(Structure):
        _fields_ = [
          ("biSize", c_ulong), ("biWidth", c_long), ("biHeight", c_long),
          ("biPlanes", c_ushort), ("biBitCount", c_ushort), ("biCompression", c_ulong),
          ("biSizeImage", c_ulong), ("biXPelsPerMeter", c_long),
          ("biYPelsPerMeter", c_long), ("biClrUsed", c_ulong), ("biClrImportant", c_ulong),
        ]

      rect = ctypes.wintypes.RECT()
      ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
      width = rect.right - rect.left
      height = rect.bottom - rect.top
      if width <= 0 or height <= 0:
        return None

      hdc_screen = ctypes.windll.user32.GetDC(0)
      hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_screen)
      hBitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
      ctypes.windll.gdi32.SelectObject(hdc_mem, hBitmap)

      # Try PrintWindow first
      for flags in (0x00000002, 0x00000000):
        result = ctypes.windll.user32.PrintWindow(hwnd, hdc_mem, flags)
        if result != 0:
          bmpinfo = BITMAPINFOHEADER()
          bmpinfo.biSize = ctypes.sizeof(BITMAPINFOHEADER)
          bmpinfo.biWidth = width
          bmpinfo.biHeight = -height
          bmpinfo.biPlanes = 1
          bmpinfo.biBitCount = 32
          bmpinfo.biCompression = 0
          buf = ctypes.create_string_buffer(width * height * 4)
          ctypes.windll.gdi32.GetDIBits(hdc_mem, hBitmap, 0, height, buf, ctypes.byref(bmpinfo), 0)
          img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")
          ctypes.windll.gdi32.DeleteObject(hBitmap)
          ctypes.windll.user32.DeleteDC(hdc_mem)
          ctypes.windll.user32.ReleaseDC(0, hdc_screen)
          path = artifacts_dir / f"{label}-{int(time.time()*1000)}.png"
          img.save(path)
          return str(path)

      # Method 4: BitBlt (works for Unity/DirectX/OpenGL games)
      result = ctypes.windll.gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, rect.left, rect.top, 0x00CC0020)
      if result:
        bmpinfo = BITMAPINFOHEADER()
        bmpinfo.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmpinfo.biWidth = width
        bmpinfo.biHeight = -height
        bmpinfo.biPlanes = 1
        bmpinfo.biBitCount = 32
        bmpinfo.biCompression = 0
        buf = ctypes.create_string_buffer(width * height * 4)
        ctypes.windll.gdi32.GetDIBits(hdc_mem, hBitmap, 0, height, buf, ctypes.byref(bmpinfo), 0)
        img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")
        ctypes.windll.gdi32.DeleteObject(hBitmap)
        ctypes.windll.user32.DeleteDC(hdc_mem)
        ctypes.windll.user32.ReleaseDC(0, hdc_screen)
        path = artifacts_dir / f"{label}-{int(time.time()*1000)}.png"
        img.save(path)
        return str(path)

      ctypes.windll.gdi32.DeleteObject(hBitmap)
      ctypes.windll.user32.DeleteDC(hdc_mem)
      ctypes.windll.user32.ReleaseDC(0, hdc_screen)
    except Exception:
      pass

    return None

  return await asyncio.to_thread(_shot)


def screenshot_frame_from_path(session_id: str, path: str) -> dict:
  from uno_schemas.perception import ScreenshotFrame
  raw = Path(path).read_bytes()
  return ScreenshotFrame(
    frame_id=str(uuid4()),
    session_id=session_id,
    width=800,
    height=600,
    path=path,
    data_base64=base64.b64encode(raw).decode("ascii"),
    captured_at_ms=int(time.time() * 1000),
  ).model_dump()
