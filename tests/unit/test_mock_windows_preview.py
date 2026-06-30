"""Mock Windows adapter preview tests."""

from uno_adapter_windows.mock_adapter import MockWindowsAdapter
from uno_schemas.adapter_windows import PreviewFrameKind, WindowsRpaStatus


async def test_mock_adapter_preview_ready_with_synthetic_frame():
  adapter = MockWindowsAdapter("sess-mock", profile_id="local-mock-uno")
  adapter.bind_adapter_id("mock-aid-1")
  assert await adapter.attach()
  preview = adapter.get_preview_state()
  assert preview.adapter_id == "mock-aid-1"
  assert preview.status == WindowsRpaStatus.READY
  assert preview.attachment is not None
  assert preview.attachment.backend == "mock"
  assert preview.frame_kind == PreviewFrameKind.SYNTHETIC
  assert preview.live_frame is not None
  assert preview.live_frame.data_base64
  assert "not available" not in preview.message.lower()
