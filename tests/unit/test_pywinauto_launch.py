"""Pywinauto unit tests — autonomous, no live services required."""

from pathlib import Path
from unittest.mock import patch

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.runtime import launch_test_target


def test_launch_test_target_resolves_adapter_windows_script():
  profile = load_profile("local-mock-uno")
  expected = Path(__file__).resolve().parents[2] / "services" / "adapter-windows" / profile.test_target_script
  proc = launch_test_target(profile)
  try:
    assert proc is not None
    assert expected.exists()
  finally:
    if proc:
      proc.terminate()
      proc.wait(timeout=5)


@pytest.mark.asyncio
async def test_find_window_polls_until_target_appears():
  from uno_adapter_windows.runtime import find_window

  profile = load_profile("local-mock-uno")
  profile.readiness_timeout_ms = 2000
  calls = {"n": 0}

  async def fake_find(profile, backend, title_hint):
    calls["n"] += 1
    if calls["n"] < 3:
      return None
    return object()

  with patch("uno_adapter_windows.runtime._find_with_backend", side_effect=fake_find):
    win, backend = await find_window(profile)
  assert win is not None
  assert calls["n"] >= 3
