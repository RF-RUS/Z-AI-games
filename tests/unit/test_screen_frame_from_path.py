"""screen_frame_from_path dimension handling."""

from PIL import Image
from uno_adapter_windows.rpa.session_state import screen_frame_from_path


def test_screen_frame_from_path_reads_image_dimensions(tmp_path):
  img_path = tmp_path / "frame.png"
  Image.new("RGB", (320, 200), (10, 20, 30)).save(img_path)
  frame = screen_frame_from_path(str(img_path), "sess-1")
  assert frame.width == 320
  assert frame.height == 200
  assert frame.data_base64
