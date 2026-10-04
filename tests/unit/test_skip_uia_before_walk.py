"""Regression: ungrounded match-card clicks must refuse fast on browser/canvas hosts.

Session de3856d6 cycle 2 burned the whole 12s adapter deadline because the UIA
tree walk ran BEFORE the skip-UIA decision. When the host is a browser and the
selector is a match-card key, the walk's result is useless anyway — so the
decision must come first and the walk must not run at all (no stall, structured
refusal instead of a 12s timeout).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_adapter_windows.rpa.session_state import RpaSessionState
from uno_schemas.adapter_windows import (
    VisualActionRequest,
    WindowMatcher,
    WindowsActionType,
    WindowsAdapterProfile,
)


def _profile() -> WindowsAdapterProfile:
    # Deliberately has NO play/draw selectors, mappings, aliases or layout_targets:
    # resolution must end in "not found" so no click path is exercised.
    return WindowsAdapterProfile(
        profile_id="empty-cascade-test",
        display_name="t",
        window=WindowMatcher(title_regex="X"),
    )


def _build_executor(*, is_browser_host: bool):
    from uno_adapter_windows.rpa.executor.visual_executor import VisualRpaExecutor

    window = MagicMock()
    window.handle = 12345
    state = RpaSessionState("", "test-session")
    state.attachment = MagicMock()
    state.attachment.is_browser_host = is_browser_host
    return VisualRpaExecutor(
        window, _profile(), "uia", MagicMock(), state, "test-session",
        bounds={"left": 100, "top": 50, "right": 740, "bottom": 569},
    )


def _req() -> VisualActionRequest:
    return VisualActionRequest(
        domain_action="play_card",
        selector_key="play_red_five",
        action_type=WindowsActionType.CLICK,
    )


class TestSkipUiaBeforeWalk:
    @pytest.mark.asyncio
    async def test_browser_match_card_skips_walk_and_refuses_fast(self):
        executor = _build_executor(is_browser_host=True)
        walk_calls = []
        walk = AsyncMock(side_effect=lambda *a, **k: walk_calls.append(1) or ([], False, True))
        with patch.object(executor, "capture_live_frame", new_callable=AsyncMock, return_value=None), \
             patch("uno_adapter_windows.rpa.executor.visual_executor.extract_ui_tree", new=walk):
            result = await asyncio.wait_for(executor._execute_visual("t1", _req()), timeout=5.0)

        assert result.success is False
        assert result.uncertain is True
        assert "not supported via Windows UIA" in (result.error or "")
        # The whole point: with skip decided up front, the walk never runs.
        assert walk_calls == []

    @pytest.mark.asyncio
    async def test_native_host_still_walks(self):
        """Non-browser host keeps the full cascade: the walk must still happen."""
        executor = _build_executor(is_browser_host=False)
        walk_calls = []
        walk = AsyncMock(side_effect=lambda *a, **k: walk_calls.append(1) or ([], False, True))
        with patch.object(executor, "capture_live_frame", new_callable=AsyncMock, return_value=None), \
             patch("uno_adapter_windows.rpa.executor.visual_executor.extract_ui_tree", new=walk):
            result = await executor._execute_visual("t2", _req())

        assert walk_calls == [1]
        assert result.success is False
        assert result.uncertain is True
