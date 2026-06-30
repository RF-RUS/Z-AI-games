"""Window selection for Windows attach."""

from unittest.mock import MagicMock, patch

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.runtime import _find_with_backend


def _win(title: str, *, focused: bool = False, class_name: str = "GameWindow"):
  w = MagicMock()
  w.window_text.return_value = title
  w.class_name.return_value = class_name
  w.has_focus.return_value = focused
  return w


@pytest.mark.asyncio
async def test_find_window_prefers_real_uno_over_mock():
  profile = load_profile("real-uno-desktop")
  mock = _win("UNO Mock Test Target")
  real = _win("UNO", focused=True)

  with patch("pywinauto.Desktop") as desktop_cls:
    desktop_cls.return_value.windows.return_value = [mock, real]
    found = await _find_with_backend(profile, "uia", None)

  assert found is real


@pytest.mark.asyncio
async def test_find_window_honors_title_hint():
  profile = load_profile("real-uno-desktop")
  mock = _win("UNO Mock Test Target")
  real = _win("UNO Championship")

  with patch("pywinauto.Desktop") as desktop_cls:
    desktop_cls.return_value.windows.return_value = [mock, real]
    found = await _find_with_backend(profile, "uia", "Championship")

  assert found is real


@pytest.mark.asyncio
async def test_local_mock_profile_matches_mock_target():
  profile = load_profile("local-mock-uno")
  mock = _win("UNO Mock Test Target")
  real = _win("UNO")

  with patch("pywinauto.Desktop") as desktop_cls:
    desktop_cls.return_value.windows.return_value = [real, mock]
    found = await _find_with_backend(profile, "uia", None)

  assert found is mock
