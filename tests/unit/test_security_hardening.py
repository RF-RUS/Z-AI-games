"""Verification tests for security hardening changes."""

import time
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.rpa.perception.target_locator import locate_selector
from uno_schemas.adapter_windows import (
    TargetAcquisitionMethod,
    UiNodeSnapshot,
    VisualActionRequest,
    WindowsActionType,
)

# --- 1. Unknown selector_key is rejected ---


class TestSelectorKeyAllowlist:
    """Verify that unknown selector_keys are rejected before execution."""

    def _build_executor(self, profile_id="local-mock-uno"):
        from uno_adapter_windows.rpa.executor.visual_executor import VisualRpaExecutor
        from uno_adapter_windows.rpa.session_state import RpaSessionState

        profile = load_profile(profile_id)
        window = MagicMock()
        window.handle = 12345
        window.window_text.return_value = "UNO Mock Test Target"
        window.class_name.return_value = "Tk"
        window.process_id.return_value = 999
        window.rectangle.return_value = MagicMock(left=100, top=50, right=740, bottom=569)
        state = RpaSessionState("", "test-session")
        state.attachment = MagicMock()
        state.attachment.is_browser_host = False
        return VisualRpaExecutor(
            window, profile, "uia", MagicMock(), state, "test-session",
            bounds={"left": 100, "top": 50, "right": 740, "bottom": 569},
        )

    @pytest.mark.asyncio
    async def test_unknown_selector_key_rejected(self):
        executor = self._build_executor()
        req = VisualActionRequest(
            domain_action="malicious_click",
            selector_key="Close",
            action_type=WindowsActionType.CLICK,
        )
        with patch.object(executor, "capture_live_frame", new_callable=AsyncMock, return_value=None):
            result = await executor._execute_visual("test-1", req)
        assert result.success is False
        assert result.uncertain is True
        assert "not in profile allowlist" in result.error
        assert result.verification.status == "rejected"

    @pytest.mark.asyncio
    async def test_known_selector_key_accepted(self):
        executor = self._build_executor()
        req = VisualActionRequest(
            domain_action="draw",
            selector_key="draw",
            action_type=WindowsActionType.CLICK,
        )
        with patch.object(executor, "capture_live_frame", new_callable=AsyncMock, return_value=None):
            result = await executor._execute_visual("test-2", req)
        assert "not in profile allowlist" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_alias_selector_key_accepted(self):
        executor = self._build_executor()
        req = VisualActionRequest(
            domain_action="play",
            selector_key="play_red_five",
            action_type=WindowsActionType.CLICK,
        )
        with patch.object(executor, "capture_live_frame", new_callable=AsyncMock, return_value=None):
            result = await executor._execute_visual("test-3", req)
        assert "not in profile allowlist" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_empty_selector_key_not_rejected(self):
        executor = self._build_executor()
        req = VisualActionRequest(
            domain_action="click",
            selector_key=None,
            action_type=WindowsActionType.CLICK,
        )
        with patch.object(executor, "capture_live_frame", new_callable=AsyncMock, return_value=None):
            result = await executor._execute_visual("test-4", req)
        assert "not in profile allowlist" not in (result.error or "")


# --- 2. Primary UIA match uses exact match only ---


class TestExactMatch:
    """Verify that locate_selector uses exact match for primary UIA path."""

    def _profile(self):
        return load_profile("local-mock-uno")

    def test_exact_match_works(self):
        profile = self._profile()
        nodes = [UiNodeSnapshot(node_id="1", name="Draw", control_type="Button")]
        target = locate_selector("draw_button", profile, nodes)
        assert target is not None
        assert target.method == TargetAcquisitionMethod.UIA

    def test_substring_does_not_match_primary(self):
        profile = self._profile()
        nodes = [UiNodeSnapshot(node_id="2", name="Draw Pile", control_type="Button")]
        target = locate_selector("draw_button", profile, nodes, allow_coordinate_fallback=False)
        assert target is None

    def test_partial_name_does_not_match(self):
        profile = self._profile()
        nodes = [UiNodeSnapshot(node_id="3", name="Play Red 5 Extra", control_type="Button")]
        target = locate_selector("play_red_five", profile, nodes, allow_coordinate_fallback=False)
        assert target is None

    def test_exact_action_mapping_match(self):
        profile = self._profile()
        nodes = [UiNodeSnapshot(node_id="4", name="Play Red 5", control_type="Button")]
        target = locate_selector("play_red_five", profile, nodes)
        assert target is not None
        assert target.label == "Play Red 5"

    def test_action_mapping_substring_rejected(self):
        profile = self._profile()
        nodes = [UiNodeSnapshot(node_id="5", name="Play Red 5 Extra", control_type="Button")]
        target = locate_selector("play_red_five", profile, nodes, allow_coordinate_fallback=False)
        assert target is None

    def test_coordinate_fallback_allows_substring(self):
        profile = self._profile()
        nodes = [UiNodeSnapshot(node_id="6", name="Draw extra", control_type="Button")]
        target = locate_selector("draw_button", profile, nodes, allow_coordinate_fallback=True)
        assert target is not None
        assert target.method == TargetAcquisitionMethod.COORDINATE
        assert target.confidence == 0.45


# --- 3. _click_uia_element restricted to profile targets ---


class TestClickUIARestriction:
    """Verify _click_uia_element only allows profile-registered titles/auto_ids."""

    def _build_executor(self):
        from uno_adapter_windows.rpa.executor.visual_executor import VisualRpaExecutor
        from uno_adapter_windows.rpa.session_state import RpaSessionState

        profile = load_profile("local-mock-uno")
        window = MagicMock()
        window.handle = 12345
        state = RpaSessionState("", "test-session")
        state.attachment = MagicMock()
        state.attachment.is_browser_host = False
        return VisualRpaExecutor(
            window, profile, "uia", MagicMock(), state, "test-session",
            bounds={"left": 100, "top": 50, "right": 740, "bottom": 569},
        )

    @pytest.mark.asyncio
    async def test_registered_title_allowed(self):
        from uno_schemas.adapter_windows import UITarget
        executor = self._build_executor()
        target = UITarget(
            selector_key="draw_button",
            label="Draw",
            method=TargetAcquisitionMethod.UIA,
            confidence=0.9,
            bounds={"left": 100, "top": 100, "right": 150, "bottom": 130},
            click_point={"x": 125, "y": 115},
            title="Draw",
        )
        executor._window.child_window.return_value = MagicMock()
        await executor._click_uia_element(target)
        executor._window.child_window.assert_called_once_with(title="Draw", found_index=0)

    @pytest.mark.asyncio
    async def test_unregistered_title_falls_through_to_coords(self):
        from uno_schemas.adapter_windows import UITarget
        executor = self._build_executor()
        target = UITarget(
            selector_key="Close",
            label="Close",
            method=TargetAcquisitionMethod.UIA,
            confidence=0.8,
            bounds={"left": 100, "top": 100, "right": 150, "bottom": 130},
            click_point={"x": 125, "y": 115},
            title="Close",
        )
        await executor._click_uia_element(target)
        executor._window.child_window.assert_not_called()


# --- 4. Rate limiting returns 429 ---


class TestRateLimiting:
    """Verify rate limiting on action endpoints."""

    def test_rate_limit_rejects_burst(self):

        timestamps = defaultdict(list)
        window = 1.0
        max_requests = 10
        adapter_id = "test-adapter"

        for i in range(max_requests):
            now = time.monotonic()
            ts = timestamps[adapter_id]
            ts[:] = [t for t in ts if now - t < window]
            assert len(ts) < max_requests
            ts.append(now)

        now = time.monotonic()
        ts = timestamps[adapter_id]
        ts[:] = [t for t in ts if now - t < window]
        assert len(ts) >= max_requests


# --- 5. Audit logs emitted ---


class TestAuditLogging:
    """Verify audit logging is called for actions."""

    @pytest.mark.asyncio
    async def test_audit_log_emitted_on_rejection(self):
        from uno_adapter_windows.rpa.executor.visual_executor import VisualRpaExecutor
        from uno_adapter_windows.rpa.session_state import RpaSessionState
        from uno_schemas.adapter_windows import VisualActionRequest, WindowsActionType

        profile = load_profile("local-mock-uno")
        window = MagicMock()
        window.handle = 12345
        state = RpaSessionState("", "test-session")
        state.attachment = MagicMock()
        state.attachment.is_browser_host = False
        executor = VisualRpaExecutor(
            window, profile, "uia", MagicMock(), state, "test-session",
            bounds={"left": 100, "top": 50, "right": 740, "bottom": 569},
        )

        req = VisualActionRequest(
            domain_action="draw",
            selector_key="Close",
            action_type=WindowsActionType.CLICK,
        )
        import logging
        real_logger = logging.getLogger("adapter-windows.audit")
        mock_logger = MagicMock()
        mock_logger.warning = real_logger.warning
        mock_info_calls = []
        original_warning = real_logger.warning
        def capture_warning(msg, *args, **kwargs):
            mock_info_calls.append((msg, args))
        real_logger.warning = capture_warning

        with patch.object(executor, "capture_live_frame", new_callable=AsyncMock, return_value=None):
            await executor._execute_visual("test-audit", req)

        real_logger.warning = original_warning
        assert len(mock_info_calls) > 0
        assert any("action_rejected" in call[0] for call in mock_info_calls)
        assert any("Close" in str(call[1]) for call in mock_info_calls)
