"""Visual executor layout-target fallback for sparse tkinter UIA."""

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.pywinauto_adapter import PywinautoWindowsAdapter
from uno_schemas.adapter_windows import (
  WindowsActionExecutionRequest,
  WindowsActionType,
  WindowsRpaStatus,
)


@pytest.mark.asyncio
@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
async def test_play_card_resolves_layout_target_on_live_mock_window():
  profile = load_profile("local-mock-uno")
  adapter = PywinautoWindowsAdapter("layout-exec", profile, launch_test_target_flag=True)
  assert await adapter.attach()
  try:
    executor = adapter._executor
    assert executor is not None
    result = await executor.execute_request(
      WindowsActionExecutionRequest(
        action_type=WindowsActionType.CLICK_INPUT,
        selector_key="play_red_five",
        domain_action="play_card",
        min_confidence=0.55,
      )
    )
    assert result.target is not None
    assert result.target.confidence >= 0.55
    assert result.error not in ("confidence below threshold", "target not found")
    assert adapter._state.status != WindowsRpaStatus.UNCERTAIN
  finally:
    await adapter.detach()
