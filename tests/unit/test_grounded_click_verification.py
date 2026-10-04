"""Regression: a dispatched click must not record as confirmed unless the board
visibly changed between before/after frames. A missed click used to log
ok:true and every later cycle decided on a stale board.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from uno_adapter_windows.rpa.session_state import RpaSessionState
from uno_schemas.adapter_windows import (
    WindowMatcher,
    WindowsActionExecutionRequest,
    WindowsAdapterProfile,
    WindowsActionType,
)


def _executor(tmp: Path):
    from uno_adapter_windows.rpa.executor.visual_executor import VisualRpaExecutor

    profile = WindowsAdapterProfile(
        profile_id="verify-test", display_name="t", window=WindowMatcher(title_regex="X"),
    )
    state = RpaSessionState("", "s-verify")
    state.attachment = None
    return VisualRpaExecutor(
        MagicMock(), profile, "uia", MagicMock(), state, "s-verify",
        bounds={"left": 0, "top": 0, "right": 1000, "bottom": 800},
    )


def _frames(tmp: Path) -> tuple[str, str, str]:
    before = tmp / "before.png"
    Image.new("RGB", (40, 30), (200, 30, 30)).save(before)
    after_changed = tmp / "after_changed.png"
    Image.new("RGB", (40, 30), (30, 200, 30)).save(after_changed)
    after_same = tmp / "after_same.png"
    Image.new("RGB", (40, 30), (200, 30, 30)).save(after_same)
    return str(before), str(after_changed), str(after_same)


def _req() -> WindowsActionExecutionRequest:
    return WindowsActionExecutionRequest(
        action_type=WindowsActionType.CLICK_INPUT,
        selector_key="play_red_five",
        domain_action="play_card",
        target_x=20, target_y=15,
        capture_screenshots=True,
    )


def _patch_inputs(executor, before: str, after: str):
    return (
        patch.object(executor, "capture_live_frame", new_callable=AsyncMock, side_effect=[before, after]),
        patch("uno_adapter_windows.rpa.executor.visual_executor.humanized_move_and_click", new=AsyncMock(return_value=(20, 15))),
        patch("uno_adapter_windows.rpa.executor.visual_executor.ensure_focus", new=AsyncMock()),
    )


class TestGroundedClickVerification:
    @pytest.mark.asyncio
    async def test_changed_board_confirms_delivery(self, tmp_path):
        executor = _executor(tmp_path)
        before, after_changed, _ = _frames(tmp_path)
        p1, p2, p3 = _patch_inputs(executor, before, after_changed)
        with p1, p2, p3:
            result = await executor._execute_grounded_click("act-1", _req())
        assert result.success is True
        assert result.uncertain is False
        assert result.verification.status == "passed"
        from uno_schemas.adapter_windows import WindowsRpaStatus
        assert executor._state.status == WindowsRpaStatus.READY

    @pytest.mark.asyncio
    async def test_unchanged_board_flags_unconfirmed(self, tmp_path):
        """Click dispatched but the board didn't move → NOT recorded as done."""
        executor = _executor(tmp_path)
        before, _, after_same = _frames(tmp_path)
        p1, p2, p3 = _patch_inputs(executor, before, after_same)
        with p1, p2, p3:
            result = await executor._execute_grounded_click("act-2", _req())
        assert result.success is True  # the click itself was dispatched
        assert result.uncertain is True
        assert result.verification.status == "no_visible_change"
        from uno_schemas.adapter_windows import WindowsRpaStatus
        assert executor._state.status == WindowsRpaStatus.UNCERTAIN
