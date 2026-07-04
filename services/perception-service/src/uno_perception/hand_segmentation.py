"""Segment the player's hand strip into individual cards.

Calibrated against real UNO desktop (Electron) screenshots. The hand is a
horizontally-centered fan of overlapping cards at the bottom of the screen.
Classic per-card contour detection on a stylised 3D fan is unreliable, so this
uses a robust, testable pipeline:

  1. Detect the hand's horizontal EXTENT (bright card columns vs the red table)
     inside a profile-provided region.
  2. Estimate the card COUNT from the extent width / a typical card step.
  3. Divide the extent into even slots → per-card bounds + click center.
  4. Sample each slot's dominant COLOR (red/yellow/green/blue/wild).

Value (number/action) recognition is intentionally NOT done here — it needs
live tuning on the target machine; colour + a reliable click coordinate per slot
is enough to start grounding actions. See AGENT_DECISIONS D5 / TODO #9.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

# Typical visible width (px) of one hand card at the reference 1296x759 window.
# Used only to estimate card count from the detected extent.
_TYPICAL_CARD_STEP = 60.0
_MIN_CARDS, _MAX_CARDS = 1, 12


@dataclass
class HandCardSlot:
  slot_index: int
  color: str                       # red|yellow|green|blue|wild
  bounds: tuple[int, int, int, int]  # absolute (x, y, w, h)
  center: tuple[int, int]          # absolute click point
  color_confidence: float


def _classify_color(px, x0: int, x1: int, y0: int, y1: int) -> tuple[str, float]:
  buckets = {"red": 0, "yellow": 0, "green": 0, "blue": 0, "wild": 0}
  total = 0
  for x in range(x0, x1, 2):
    for y in range(y0, y1, 2):
      r, g, b = px[x, y]
      mx, mn = max(r, g, b), min(r, g, b)
      v = mx / 255
      s = (mx - mn) / mx if mx else 0
      total += 1
      # Dark or desaturated-dark → wild (black card / multi-colour back).
      if v < 0.28 or (s < 0.22 and v < 0.6):
        buckets["wild"] += 1
        continue
      if s < 0.25:
        continue  # washed-out border pixel, skip
      h = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0] * 360
      if h < 20 or h >= 330:
        buckets["red"] += 1
      elif h < 70:
        buckets["yellow"] += 1
      elif h < 170:
        buckets["green"] += 1
      else:
        buckets["blue"] += 1
  if total == 0:
    return "unknown", 0.0
  color = max(buckets, key=buckets.get)
  conf = buckets[color] / max(1, sum(buckets.values()))
  return color, round(conf, 3)


def _detect_extent(px, rx0: int, ry0: int, rx1: int, ry1: int) -> tuple[int, int] | None:
  """Find [x_start, x_end] of the bright card strip inside the region."""
  cols: list[int] = []
  for x in range(rx0, rx1):
    card = tot = 0
    for y in range(ry0, ry1, 3):
      r, g, b = px[x, y]
      mx, mn = max(r, g, b), min(r, g, b)
      v = mx / 255
      s = (mx - mn) / mx if mx else 0
      tot += 1
      is_table = (r > g and r > b and v < 0.75 and not (g > 90 and b > 90))
      is_card = (v > 0.80) or (s > 0.45 and not (r > 1.6 * g and r > 1.6 * b)) or (v < 0.18)
      if is_card and not is_table:
        card += 1
    cols.append(1 if tot and card / tot > 0.35 else 0)
  xs = [i for i, c in enumerate(cols) if c]
  if not xs:
    return None
  return rx0 + xs[0], rx0 + xs[-1] + 1


def segment_hand_cards(
  screenshot_path: str,
  region: dict[str, int],
) -> list[HandCardSlot]:
  """Segment the hand region (absolute px {x,y,width,height}) into card slots."""
  try:
    from PIL import Image
    img = Image.open(screenshot_path).convert("RGB")
  except Exception:
    return []
  W, H = img.size
  px = img.load()

  rx0 = max(0, int(region.get("x", 0)))
  ry0 = max(0, int(region.get("y", 0)))
  rx1 = min(W, rx0 + int(region.get("width", 0)))
  ry1 = min(H, ry0 + int(region.get("height", 0)))
  if rx1 - rx0 < 20 or ry1 - ry0 < 20:
    return []

  extent = _detect_extent(px, rx0, ry0, rx1, ry1)
  if not extent:
    return []
  x_start, x_end = extent
  width = x_end - x_start
  n = max(_MIN_CARDS, min(_MAX_CARDS, round(width / _TYPICAL_CARD_STEP)))
  step = width / n

  # Sample colours in the card body band (middle-lower part of the region).
  band_y0 = ry0 + int((ry1 - ry0) * 0.25)
  band_y1 = ry0 + int((ry1 - ry0) * 0.75)

  slots: list[HandCardSlot] = []
  for i in range(n):
    sx0 = int(x_start + i * step)
    sx1 = int(x_start + (i + 1) * step)
    color, conf = _classify_color(px, min(sx0 + 4, W - 1), min(sx1 - 4, W), band_y0, band_y1)
    cx = (sx0 + sx1) // 2
    cy = (band_y0 + band_y1) // 2
    slots.append(HandCardSlot(
      slot_index=i,
      color=color,
      bounds=(sx0, ry0, sx1 - sx0, ry1 - ry0),
      center=(cx, cy),
      color_confidence=conf,
    ))
  return slots
