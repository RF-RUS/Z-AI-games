"""Synthetic mock preview frame tests."""

from pathlib import Path

from uno_adapter_windows.rpa.synthetic_frame import build_mock_synthetic_frame


def test_build_mock_synthetic_frame(tmp_path: Path):
  frame = build_mock_synthetic_frame(
    tmp_path,
    "UNO Mock Test Target",
    ["Discard: Red 5", "Draw"],
    "sess-1",
  )
  assert frame.width == 640
  assert frame.height == 360
  assert frame.data_base64
  assert Path(frame.path).exists()
