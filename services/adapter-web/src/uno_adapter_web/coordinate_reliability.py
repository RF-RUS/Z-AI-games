"""Coordinate-space reliability — explicit transformations, validation, and logging.

Centralizes coordinate conversion between:
- CV screenshot space (device pixels)
- CSS viewport space (what page.mouse.click uses)
- Canvas-relative space (bounding box offsets)

Provides validation, logging, and safety checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CoordinateConversion:
  """Records the full coordinate transformation chain."""
  raw_x: float = 0.0
  raw_y: float = 0.0
  dpr: float = 1.0
  viewport_width: int = 1280
  viewport_height: int = 800
  canvas_bbox: dict[str, float] | None = None
  css_x: float = 0.0
  css_y: float = 0.0
  in_canvas_bounds: bool = False
  valid: bool = False
  reason: str = ""


def convert_cv_to_css(
  raw_x: float,
  raw_y: float,
  dpr: float = 1.0,
  canvas_bbox: dict[str, float] | None = None,
  viewport_width: int = 1280,
  viewport_height: int = 800,
) -> CoordinateConversion:
  """Convert CV screenshot coordinates (device pixels) to CSS viewport coordinates.

  CV coordinates come from page.screenshot() which captures at device pixel ratio.
  page.mouse.click() operates in CSS pixel space.
  """
  if raw_x < 0 or raw_y < 0:
    return CoordinateConversion(
      raw_x=raw_x, raw_y=raw_y, dpr=dpr,
      viewport_width=viewport_width, viewport_height=viewport_height,
      valid=False, reason=f"negative coordinates: ({raw_x}, {raw_y})",
    )

  css_x = raw_x / dpr
  css_y = raw_y / dpr

  in_canvas = False
  if canvas_bbox:
    cbx = canvas_bbox.get("x", 0)
    cby = canvas_bbox.get("y", 0)
    cbw = canvas_bbox.get("width", 0)
    cbh = canvas_bbox.get("height", 0)
    in_canvas = cbx <= css_x <= cbx + cbw and cby <= css_y <= cby + cbh

  out_of_viewport = css_x > viewport_width or css_y > viewport_height

  if out_of_viewport:
    return CoordinateConversion(
      raw_x=raw_x, raw_y=raw_y, dpr=dpr,
      viewport_width=viewport_width, viewport_height=viewport_height,
      canvas_bbox=canvas_bbox, css_x=css_x, css_y=css_y,
      in_canvas_bounds=in_canvas,
      valid=False, reason=f"out of viewport: ({css_x:.1f}, {css_y:.1f}) > {viewport_width}x{viewport_height}",
    )

  return CoordinateConversion(
    raw_x=raw_x, raw_y=raw_y, dpr=dpr,
    viewport_width=viewport_width, viewport_height=viewport_height,
    canvas_bbox=canvas_bbox, css_x=css_x, css_y=css_y,
    in_canvas_bounds=in_canvas,
    valid=True, reason="ok",
  )


def convert_draw_pile_css(
  raw_x: float,
  raw_y: float,
  dpr: float = 1.0,
) -> tuple[float, float]:
  """Simple DPR correction for draw pile coordinates."""
  return raw_x / dpr, raw_y / dpr


def validate_click_target(
  css_x: float,
  css_y: float,
  canvas_bbox: dict[str, float] | None = None,
  viewport_width: int = 1280,
  viewport_height: int = 800,
) -> tuple[bool, str]:
  """Validate that a click target is within reasonable bounds.

  Returns (is_valid, reason).
  """
  if css_x < 0 or css_y < 0:
    return False, f"negative coordinates ({css_x:.1f}, {css_y:.1f})"

  if css_x > viewport_width or css_y > viewport_height:
    return False, f"outside viewport ({css_x:.1f}, {css_y:.1f}) > {viewport_width}x{viewport_height}"

  if canvas_bbox:
    cbx = canvas_bbox.get("x", 0)
    cby = canvas_bbox.get("y", 0)
    cbw = canvas_bbox.get("width", 0)
    cbh = canvas_bbox.get("height", 0)
    if cbw > 0 and cbh > 0:
      margin = 5
      if css_x < cbx - margin or css_x > cbx + cbw + margin:
        return False, f"outside canvas x: {css_x:.1f} not in [{cbx-margin:.0f}, {cbx+cbw+margin:.0f}]"
      if css_y < cby - margin or css_y > cby + cbh + margin:
        return False, f"outside canvas y: {css_y:.1f} not in [{cby-margin:.0f}, {cby+cbh+margin:.0f}]"

  return True, "valid"


def coordinate_to_dict(conv: CoordinateConversion) -> dict[str, Any]:
  """Serialize conversion chain to metadata dict."""
  return {
    "raw": {"x": conv.raw_x, "y": conv.raw_y},
    "css": {"x": round(conv.css_x, 1), "y": round(conv.css_y, 1)},
    "dpr": conv.dpr,
    "in_canvas_bounds": conv.in_canvas_bounds,
    "valid": conv.valid,
    "reason": conv.reason,
  }
