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
# ponytail: wall-clock cap on the UIA walk. Chromium/Electron UIA trees can be
# huge and enumerate slowly; without this the walk can exceed the orchestrator's
# HTTP timeout and stall the whole session with a ReadTimeout. Raise if a native
# app legitimately needs deeper walks.
UIA_WALK_BUDGET_S = 4.0
# Hard cap on the WHOLE walk coroutine. The budget above is only checked BETWEEN
# elements, so a single COM call (element.children()/rectangle() against a live,
# animating game window) can block the walk thread past the budget and the
# `await` sits on it forever — that is the "observe ReadTimeout after 1 minute"
# stall. wait_for releases the await even though the orphaned thread keeps
# running until the COM call returns (bounded: it dies when the call returns or
# the process restarts). Set just above the budget so a healthy walk finishes
# naturally first and only a genuinely hung call hits this cap.
UIA_WALK_HARD_TIMEOUT_S = 6.0
# Dedicated pool for the UIA tree walk. This is the load-bearing detail behind
# the 2026-08-28 "observe ReadTimeout" fix: `asyncio.wait_for(to_thread(_walk), 6s)`
# cancels the AWAIT but cannot KILL the walk thread — a hung UIA COM call keeps
# its worker blocked until Windows finally returns. The walk and the screenshot
# both used to run via `asyncio.to_thread` on the SAME default pool, so repeated
# hung walks piled up in that pool and the screenshot's to_thread queued behind
# them and starved — the whole evidence capture then blew the 20s backstop with
# no frame to perceive from (the "pcv=MISSING screenshot=NONE" cycle). Routing the
# walk through its OWN bounded pool isolates the slow/hung UIA work from the fast
# screenshot work: a hung walk can occupy at most max_workers dedicated threads
# and never touches the pool the screenshot draws from.
# 2026-08-29 (2nd leak wave): the real-UNO Electron window hangs the walk on
# EVERY cycle, so 2 workers filled up with leaked threads and the next walk
# waited in the queue past its 6s hard cap — the evidence bundle then lost its
# screenshot (>20s backstop). 6 workers absorb ~3 consecutive hung walks before
# a queue delay becomes visible. The real cure is skipping the walk entirely on
# match_automation=web_only profiles (see _snapshot / should_skip_uia_card_lookup),
# which makes this a safety margin, not a workaround.
_UIA_WALK_MAX_WORKERS = 6
_UIA_WALK_EXECUTOR = None
# Per-method budget for the pure GDI/ctypes screenshot paths (PrintWindow).
# Fast in practice (~50ms); bounded so an unresponsive window cannot stall the capture.
_PRINTWINDOW_BUDGET_S = 3.0
# Per-method budget for the COM/UIA-backed screenshot paths
# (pywinauto capture_as_image, PIL ImageGrab via window.rectangle()). These are
# the methods that hang against a live, animating GPU window, so they get a
# SHORTER cap than the PrintWindow methods: they are tried last anyway, and the
# sum of all four budgets must stay well below the 20s /evidence backstop in
# api.py. (The old budgets summed to 22s — over the backstop — which is exactly
# why a multi-method hang produced a frameless degraded bundle.)
_SCREENSHOT_COM_BUDGET_S = 2.0


def _get_uia_walk_executor():
  global _UIA_WALK_EXECUTOR
  if _UIA_WALK_EXECUTOR is None:
    from concurrent.futures import ThreadPoolExecutor
    _UIA_WALK_EXECUTOR = ThreadPoolExecutor(
      max_workers=_UIA_WALK_MAX_WORKERS, thread_name_prefix="uiawalk"
    )
  return _UIA_WALK_EXECUTOR
# Isolated pool for the SHORT COM window-meta calls (window_text / class_name /
# window.bounds fallback rectangle). A hung call leaks its thread until Windows
# eventually returns — with the UIA walk pool at max_workers=2, a leaked meta
# thread could queue the walk past its 6s hard cap. A separate, slightly larger
# pool isolates the two work classes; meta calls are cheap, so 4 workers absorbs
# a burst of leaks without delaying the tree walk.
_COM_META_EXECUTOR = None


def _get_com_meta_executor():
  global _COM_META_EXECUTOR
  if _COM_META_EXECUTOR is None:
    from concurrent.futures import ThreadPoolExecutor
    _COM_META_EXECUTOR = ThreadPoolExecutor(
      max_workers=4, thread_name_prefix="commeta"
    )
  return _COM_META_EXECUTOR
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
    deadline = time.perf_counter() + UIA_WALK_BUDGET_S

    def walk(element, depth: int) -> None:
      nonlocal truncated, sparse
      if len(nodes) >= MAX_NODES or time.perf_counter() >= deadline:
        # Out of node budget or time budget — stop here and return what we have.
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

  # Run the walk on the DEDICATED pool (see _UIA_WALK_EXECUTOR). A hung COM call
  # keeps its worker blocked even after the timeout below; isolating it here means
  # it can never starve the screenshot, which uses the default pool.
  loop = asyncio.get_running_loop()
  try:
    return await asyncio.wait_for(
      loop.run_in_executor(_get_uia_walk_executor(), _walk),
      timeout=UIA_WALK_HARD_TIMEOUT_S,
    )
  except asyncio.TimeoutError:
    # A single UIA COM call hung past the hard cap. Return an EMPTY (sparse,
    # truncated) tree rather than blocking the evidence capture forever: the
    # caller still gets a screenshot to perceive from, and the next cycle
    # retries the walk. Log at warning so an app that consistently hangs is
    # visible instead of silent.
    import logging
    logging.getLogger("adapter-windows").warning(
      "ui_tree_walk_timeout: returning empty tree (a UIA call hung >%ss)",
      UIA_WALK_HARD_TIMEOUT_S,
    )
    return [], True, True


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


def is_mostly_black(img, threshold: float = 8.0) -> bool:
  """True if the image is (near) uniformly black — the signature of a failed
  capture of a GPU-accelerated (Electron/Chromium/DirectX) window."""
  try:
    small = img.convert("RGB").resize((32, 32))
    px = list(small.getdata())
    if not px:
      return True
    mean = sum(r + g + b for r, g, b in px) / (len(px) * 3)
    return mean < threshold
  except Exception:
    return False


def _capture_via_printwindow(hwnd, flag: int):
  """Win32 PrintWindow → PIL Image. flag 0x2 = PW_RENDERFULLCONTENT (needed for
  Chromium/Electron/DWM-composited windows)."""
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
  width, height = rect.right - rect.left, rect.bottom - rect.top
  if width <= 0 or height <= 0:
    return None
  hdc_screen = ctypes.windll.user32.GetDC(0)
  hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_screen)
  hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
  ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)
  try:
    if ctypes.windll.user32.PrintWindow(hwnd, hdc_mem, flag) == 0:
      return None
    hdr = BITMAPINFOHEADER()
    hdr.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    hdr.biWidth, hdr.biHeight = width, -height
    hdr.biPlanes, hdr.biBitCount, hdr.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(width * height * 4)
    ctypes.windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, height, buf, ctypes.byref(hdr), 0)
    return Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")
  finally:
    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.user32.DeleteDC(hdc_mem)
    ctypes.windll.user32.ReleaseDC(0, hdc_screen)


def _bounded_call(fn, timeout_s: float):
  """Run a possibly-hung COM/UIA call in a throwaway thread with a hard join
  timeout. A hung call leaks its worker (it dies when Windows finally returns),
  but one leak per capture is bounded and — critically — the NEXT method still
  gets a chance, so a single hung call can never cost the whole screenshot.
  """
  import threading
  result: list = []
  exc: list = []
  done = threading.Event()

  def runner():
    try:
      result.append(fn())
    except Exception as e:  # noqa: BLE001 — surface to caller as None
      exc.append(e)
    finally:
      done.set()

  t = threading.Thread(target=runner, name="shot-method", daemon=True)
  t.start()
  if not done.wait(timeout_s):
    return None  # hung — abandon this method, its thread dies on its own schedule
  if exc:
    return None
  return result[0] if result else None


async def capture_window_screenshot(window, artifacts_dir: Path, label: str) -> str | None:
  """Capture a window screenshot, returning the FIRST non-black result.

  GPU-accelerated windows (Electron/Chromium, DirectX, Unity) return an all-black
  image from naive captures (pywinauto capture_as_image / plain PrintWindow). We
  therefore try several methods and skip any that come back black, preferring
  PrintWindow(PW_RENDERFULLCONTENT) and a screen-region grab which do capture DWM
  composited content. Falls back to the last available image if all look black.

  Each method runs through _bounded_call with a per-method budget: capture_as_image
  and window.rectangle() are COM/UIA calls that can hang against a live, animating
  window (the same hang class that stalls the UIA walk) — without the budget a
  single hung method would stall the WHOLE screenshot and the evidence capture
  would degrade to a frameless bundle again.
  """
  def _shot() -> str | None:
    hwnd = int(window.handle)

    def m_capture_as_image():
      return window.capture_as_image()

    def m_printwindow_full():
      return _capture_via_printwindow(hwnd, 0x00000002)  # PW_RENDERFULLCONTENT

    def m_imagegrab():
      from PIL import ImageGrab
      rect = window.rectangle()
      return ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))

    def m_printwindow_plain():
      return _capture_via_printwindow(hwnd, 0x00000000)

    # Per-method budget (s). Order matters as much as the budget:
    #
    # 1. The reliable, FAST pure-GDI/ctypes methods (PrintWindow) go FIRST. They
    #    capture DWM-composited content in ~50ms and do not depend on COM/UIA, so
    #    in the common case the loop returns after method 1 and never reaches a
    #    hang-prone COM call. capture_as_image (pywinauto) is COM/UIA-backed and
    #    is the step that stalls against a live, animating GPU window — it used
    #    to sit first, so a single COM hang cost a full 6s before the ~50ms GDI
    #    method that could have captured the frame was even tried, and the whole
    #    capture blew the 20s evidence backstop with no frame (screenshot=NONE).
    #
    # 2. Worst-case sum of every budget (3+3+2+2 = 10s) stays BELOW the 20s
    #    /evidence backstop in api.py, with headroom for the UIA tree walk
    #    (<=6s) that runs after the screenshot inside capture_evidence. The old
    #    budgets summed to 22s — over the backstop — so a multi-method hang was
    #    guaranteed to discard a capture that had already produced a frame.
    methods = [
      ("printwindow_full", m_printwindow_full, _PRINTWINDOW_BUDGET_S),
      ("printwindow_plain", m_printwindow_plain, _PRINTWINDOW_BUDGET_S),
      ("imagegrab", m_imagegrab, _SCREENSHOT_COM_BUDGET_S),
      ("capture_as_image", m_capture_as_image, _SCREENSHOT_COM_BUDGET_S),
    ]
    fallback = None
    for name, fn, budget in methods:
      try:
        img = _bounded_call(fn, budget)
      except Exception:
        continue
      if img is None:
        continue
      if fallback is None:
        fallback = img
      if not is_mostly_black(img):
        path = artifacts_dir / f"{label}-{int(time.time()*1000)}.png"
        img.save(path)
        return str(path)

    # Everything looked black — persist the last candidate anyway (diagnostic).
    if fallback is not None:
      path = artifacts_dir / f"{label}-{int(time.time()*1000)}.png"
      fallback.save(path)
      return str(path)
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
