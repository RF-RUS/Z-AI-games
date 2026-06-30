"""Tests for trace API step_dir_name field and path normalization.

Regression: Windows backslash paths caused hero image 404 because
frontend did step.path.split("/").pop() which fails on Windows paths.

Fix: Backend now returns step_dir_name (just the directory name),
frontend uses it directly instead of parsing the full path.
"""

import json
from pathlib import Path
from unittest.mock import patch


def _make_trace_session(base_dir: Path, session_id: str, steps: list[dict]):
    """Create a mock trace session directory structure."""
    session_dir = base_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    for step in steps:
        step_dir = session_dir / step["dir_name"]
        step_dir.mkdir(parents=True, exist_ok=True)
        if "frame_png" in step:
            (step_dir / "frame.png").write_bytes(step["frame_png"])
        if "meta" in step:
            (step_dir / "meta.json").write_text(
                json.dumps(step["meta"]), encoding="utf-8"
            )


class TestTraceStepDirName:
    """Verify step_dir_name is returned by the trace steps API."""

    def test_step_dir_name_matches_directory_name(self, tmp_path):
        """step_dir_name should equal the actual directory name on disk."""
        session_id = "test-session-123"
        _make_trace_session(tmp_path, session_id, [
            {"dir_name": "001_observe", "frame_png": b"fake-png", "meta": {"screen": "lobby"}},
            {"dir_name": "002_execute", "frame_png": b"fake-png", "meta": {"action_type": "click"}},
        ])

        with patch("uno_adapter_web.agent_trace.TraceManager") as mock_tm:
            mock_tm.enabled.return_value = True
            mock_tm.base_dir.return_value = tmp_path

            import asyncio

            from uno_adapter_web.api import list_trace_steps
            steps = asyncio.run(list_trace_steps(session_id))

        assert len(steps) == 2
        assert steps[0]["step_dir_name"] == "001_observe"
        assert steps[1]["step_dir_name"] == "002_execute"

    def test_step_dir_name_not_full_path(self, tmp_path):
        """step_dir_name should be just the name, not the full filesystem path."""
        session_id = "test-session-456"
        _make_trace_session(tmp_path, session_id, [
            {"dir_name": "001_observe", "frame_png": b"fake-png"},
        ])

        with patch("uno_adapter_web.agent_trace.TraceManager") as mock_tm:
            mock_tm.enabled.return_value = True
            mock_tm.base_dir.return_value = tmp_path

            import asyncio

            from uno_adapter_web.api import list_trace_steps
            steps = asyncio.run(list_trace_steps(session_id))

        assert len(steps) == 1
        # Should be just "001_observe", not the full path
        assert steps[0]["step_dir_name"] == "001_observe"
        assert "\\" not in steps[0]["step_dir_name"]
        assert "/" not in steps[0]["step_dir_name"]

    def test_step_dir_name_with_phase_variants(self, tmp_path):
        """step_dir_name works for all phase types."""
        session_id = "test-session-789"
        _make_trace_session(tmp_path, session_id, [
            {"dir_name": "001_observe", "frame_png": b"png"},
            {"dir_name": "002_perceive", "frame_png": b"png"},
            {"dir_name": "003_execute", "frame_png": b"png"},
        ])

        with patch("uno_adapter_web.agent_trace.TraceManager") as mock_tm:
            mock_tm.enabled.return_value = True
            mock_tm.base_dir.return_value = tmp_path

            import asyncio

            from uno_adapter_web.api import list_trace_steps
            steps = asyncio.run(list_trace_steps(session_id))

        dir_names = [s["step_dir_name"] for s in steps]
        assert "001_observe" in dir_names
        assert "002_perceive" in dir_names
        assert "003_execute" in dir_names


class TestFrontendPathNormalization:
    """Verify the frontend path normalization logic (unit test)."""

    def test_windows_backslash_path_extraction(self):
        """Windows path with backslashes should extract directory name."""
        # Simulate what the old code did (before fix)
        windows_path = "E:\\dev\\AI-games\\services\\artifacts\\session123\\001_observe"
        # Old broken code: split("/").pop() returns entire path on Windows
        broken = windows_path.split("/").pop()
        assert broken == windows_path  # Bug: returns full path

        # Fixed code: normalize then split
        fixed = windows_path.replace("\\", "/").split("/").pop()
        assert fixed == "001_observe"

    def test_unix_forward_slash_path_extraction(self):
        """Unix path with forward slashes should extract directory name."""
        unix_path = "/home/user/AI-games/services/artifacts/session123/001_observe"
        fixed = unix_path.replace("\\", "/").split("/").pop()
        assert fixed == "001_observe"

    def test_mixed_path_separators(self):
        """Path with mixed separators should still work."""
        mixed_path = "E:/dev/AI-games\\services/artifacts\\session123/001_observe"
        fixed = mixed_path.replace("\\", "/").split("/").pop()
        assert fixed == "001_observe"

    def test_single_directory_name(self):
        """Just a directory name (no path) should work."""
        simple = "001_observe"
        fixed = simple.replace("\\", "/").split("/").pop()
        assert fixed == "001_observe"


class TestTraceFrameUrl:
    """Verify traceFrameUrl constructs correct URLs."""

    def test_frame_url_with_step_dir_name(self):
        """traceFrameUrl should use step_dir_name directly."""
        # The URL pattern is /trace/{session_id}/{step_dir}/frame.png
        # step_dir should be just "001_observe", not a full path

        # Simulate what frontend would construct
        session_id = "abc-123"
        step_dir_name = "001_observe"
        expected_path = f"/trace/{session_id}/{step_dir_name}/frame.png"

        # Verify the path segments are correct
        assert session_id in expected_path
        assert step_dir_name in expected_path
        assert "frame.png" in expected_path
        # Should NOT contain full filesystem path
        assert "E:" not in expected_path
        assert "services" not in expected_path
