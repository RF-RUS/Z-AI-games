"""Attach stores selected HWND and expected title."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.pywinauto_adapter import PywinautoWindowsAdapter
from uno_schemas.adapter_windows import WindowsRpaStatus


@pytest.mark.asyncio
async def test_attach_stores_handle_and_detects_browser_warning():
  profile = load_profile("real-uno-desktop")
  window = MagicMock()
  window.window_text.return_value = "UNO Operator - Google Chrome"
  window.class_name.return_value = "Chrome_WidgetWin_1"
  window.process_id.return_value = 4242
  window.handle = 123456

  adapter = PywinautoWindowsAdapter(
    "sess-browser",
    profile,
    window_title="Scuffed Uno | Game - Google Chrome",
    window_handle=123456,
    window_pid=4242,
  )

  with patch("uno_adapter_windows.pywinauto_adapter.find_window", return_value=(window, "uia")):
    with patch(
      "uno_adapter_windows.pywinauto_adapter.ensure_window_usable",
      return_value={"left": 100.0, "top": 50.0, "right": 900.0, "bottom": 700.0},
    ):
      with patch("uno_adapter_windows.pywinauto_adapter.extract_ui_tree", return_value=([], False, False)):
        with patch("uno_adapter_windows.pywinauto_adapter.VisualRpaExecutor") as executor_cls:
          executor_cls.return_value.capture_live_frame = AsyncMock(return_value=None)
          ok = await adapter.attach()

  assert ok
  assert adapter._state.attachment.window_handle == 123456
  assert adapter._state.attachment.expected_title == "Scuffed Uno | Game - Google Chrome"
  assert adapter._state.attach_warning is not None
  assert adapter._state.status == WindowsRpaStatus.UNCERTAIN
