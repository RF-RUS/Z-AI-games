"""Attach by explicit HWND."""

from unittest.mock import MagicMock, patch

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.runtime import STALE_WINDOW_ERROR, connect_window_by_handle, find_window


@pytest.mark.asyncio
async def test_find_window_with_handle_bypasses_title_discovery():
  profile = load_profile("real-uno-desktop")
  win = MagicMock()

  with patch("uno_adapter_windows.runtime.connect_window_by_handle", return_value=(win, "uia")) as connect:
    with patch("uno_adapter_windows.runtime._find_with_backend") as discover:
      result = await find_window(profile, "ignored hint", window_handle=12345, window_pid=99)

  assert result == (win, "uia")
  connect.assert_awaited_once_with(profile, 12345, 99)
  discover.assert_not_called()


@pytest.mark.asyncio
async def test_connect_window_by_handle_uses_pywinauto_connect():
  profile = load_profile("real-uno-desktop")
  win = MagicMock()

  with patch("uno_adapter_windows.runtime._connect_handle", return_value=win) as connect:
    found, backend = await connect_window_by_handle(profile, 424242, 1001)

  assert found is win
  assert backend == "uia"
  connect.assert_called_once_with("uia", 424242, 1001)


@pytest.mark.asyncio
async def test_stale_handle_raises_clear_error_without_fallback():
  profile = load_profile("real-uno-desktop")

  with patch("uno_adapter_windows.runtime._connect_handle", side_effect=RuntimeError(STALE_WINDOW_ERROR)):
    with patch("uno_adapter_windows.runtime._find_with_backend") as discover:
      with pytest.raises(RuntimeError, match=STALE_WINDOW_ERROR):
        await find_window(profile, None, window_handle=999999)
      discover.assert_not_called()
