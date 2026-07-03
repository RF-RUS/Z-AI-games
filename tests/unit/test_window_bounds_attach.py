"""Window bounds usability after explicit handle attach."""

from unittest.mock import MagicMock, patch

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.pywinauto_adapter import PywinautoWindowsAdapter
from uno_adapter_windows.rpa.driver.window_driver import (
  UNUSABLE_WINDOW_ERROR,
  bounds_are_usable,
  prepare_attached_window,
  read_window_bounds,
  win32_bounds_for_handle,
)
from uno_schemas.adapter_windows import WindowsRpaStatus


def test_bounds_are_usable_rejects_zero_rectangle():
  assert not bounds_are_usable({"left": 0, "top": 0, "right": 0, "bottom": 0})
  assert bounds_are_usable({"left": 10, "top": 20, "right": 800, "bottom": 600})


def test_read_window_bounds_falls_back_to_win32_handle():
  window = MagicMock()
  rect = MagicMock(left=0, top=0, right=0, bottom=0)
  window.rectangle.return_value = rect
  window.handle = 12345

  with patch(
    "uno_adapter_windows.rpa.driver.window_driver.win32_bounds_for_handle",
    return_value={"left": 100.0, "top": 50.0, "right": 900.0, "bottom": 700.0},
  ) as win32_bounds:
    bounds = read_window_bounds(window, window_handle=12345)

  assert bounds_are_usable(bounds)
  win32_bounds.assert_called_once_with(12345)


@pytest.mark.asyncio
async def test_prepare_attached_window_restores_browser_host():
  window = MagicMock()
  window.handle = 42
  rect = MagicMock(left=100, top=50, right=900, bottom=700)
  window.rectangle.return_value = rect

  with patch("uno_adapter_windows.rpa.driver.window_driver.time.sleep"):
    bounds = await prepare_attached_window(window, is_browser_host=True, window_handle=42)

  window.restore.assert_called_once()
  window.maximize.assert_called_once()
  window.set_focus.assert_called_once()
  assert bounds_are_usable(bounds)


@pytest.mark.asyncio
async def test_attach_fails_when_bounds_stay_zero():
  profile = load_profile("real-uno-desktop")
  window = MagicMock()
  window.window_text.return_value = "Scuffed Uno | Main Menu - Google Chrome"
  window.class_name.return_value = "Chrome_WidgetWin_1"
  window.process_id.return_value = 4242
  window.handle = 123456

  adapter = PywinautoWindowsAdapter(
    "sess-zero-bounds",
    profile,
    window_title="Scuffed Uno | Main Menu - Google Chrome",
    window_handle=123456,
    window_pid=4242,
  )

  with patch("uno_adapter_windows.pywinauto_adapter.find_window", return_value=(window, "uia")):
    with patch(
      "uno_adapter_windows.pywinauto_adapter.ensure_window_usable",
      side_effect=RuntimeError(UNUSABLE_WINDOW_ERROR),
    ):
      ok = await adapter.attach()

  assert not ok
  assert adapter._state.status == WindowsRpaStatus.FAILED
  assert adapter._state.message == UNUSABLE_WINDOW_ERROR


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="ctypes.windll is Windows-only")
def test_win32_bounds_for_handle_reads_rectangle():
  with patch("ctypes.windll.user32.GetWindowRect", return_value=1) as get_rect:
    bounds = win32_bounds_for_handle(99)
  assert get_rect.called
  assert bounds is not None
