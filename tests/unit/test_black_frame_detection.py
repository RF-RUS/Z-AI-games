"""Black-frame detection for GPU/Electron window capture fallthrough.

A naive capture of an Electron/Chromium window returns an all-black image; the
capture routine must recognise that and try the next method.
"""

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from uno_adapter_windows.runtime import is_mostly_black  # noqa: E402


def test_black_image_detected():
  assert is_mostly_black(Image.new("RGB", (200, 150), (0, 0, 0)))
  assert is_mostly_black(Image.new("RGB", (200, 150), (3, 2, 4)))  # near-black


def test_bright_image_not_black():
  assert not is_mostly_black(Image.new("RGB", (200, 150), (200, 30, 30)))  # UNO red table
  assert not is_mostly_black(Image.new("RGB", (200, 150), (255, 255, 255)))


def test_mostly_black_with_small_bright_patch_still_black():
  img = Image.new("RGB", (200, 150), (0, 0, 0))
  for y in range(5):
    for x in range(5):
      img.putpixel((x, y), (255, 255, 255))
  assert is_mostly_black(img)
