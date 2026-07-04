"""Heuristic canvas perception plugin for UNO.

Uses profile-guided zones + color/size heuristics to detect
game elements from screenshots. This is the minimal vertical slice:
not perfect VLM, but enough to detect actionable targets.
"""

from __future__ import annotations

import logging

from uno_perception.screenshot_plugin import ScreenRegion, ScreenshotInference
from uno_perception.visual_extraction import extract_from_screenshot

logger = logging.getLogger("screenshot_perception")


def _estimate_image_size(screenshot_path: str) -> tuple[int, int] | None:
    """Get image dimensions without PIL dependency."""
    try:
        from PIL import Image
        with Image.open(screenshot_path) as img:
            return img.size
    except Exception:
        return None


def _color_region_avg(screenshot_path: str, x: int, y: int, w: int, h: int) -> dict | None:
    """Get average color of a region. Returns {r, g, b, brightness}."""
    try:
        from PIL import Image
        with Image.open(screenshot_path) as img:
            # Clamp to image bounds
            iw, ih = img.size
            x, y = max(0, x), max(0, y)
            w, h = min(w, iw - x), min(h, ih - y)
            if w <= 0 or h <= 0:
                return None
            region = img.crop((x, y, x + w, y + h))
            pixels = list(region.getdata())
            if not pixels:
                return None
            r = sum(p[0] for p in pixels) // len(pixels)
            g = sum(p[1] for p in pixels) // len(pixels)
            b = sum(p[2] for p in pixels) // len(pixels)
            brightness = (r + g + b) / 3
            return {"r": r, "g": g, "b": b, "brightness": brightness}
    except Exception:
        return None


def _is_likely_empty_region(avg_color: dict | None, threshold: float = 30) -> bool:
    """Check if a region is mostly dark/empty."""
    if not avg_color:
        return True
    return avg_color["brightness"] < threshold


class HeuristicCanvasUNOPlugin:
    """Minimal screenshot perception for UNO canvas games.

    Uses profile-guided zones to detect regions, then applies
    color/size heuristics to determine if they contain game elements.
    """

    game_type = "uno"

    def __init__(self):
        # Default zone definitions (can be overridden by profile).
        # Calibrated against real UNO desktop (Electron) screenshots @1296x759:
        # the hand is a centered strip (NOT full-width — full-width would capture
        # the bottom-left avatar glow and corrupt hand extent detection).
        self._default_zones = {
            "hand": {"rel_x": 0.30, "rel_y": 0.75, "rel_w": 0.45, "rel_h": 0.22},
            "play_area": {"rel_x": 0.43, "rel_y": 0.46, "rel_w": 0.14, "rel_h": 0.16},
            "draw_pile": {"rel_x": 0.26, "rel_y": 0.20, "rel_w": 0.11, "rel_h": 0.14},
        }

    def infer_from_screenshot(
        self,
        screenshot_path: str,
        profile: dict | None = None,
    ) -> ScreenshotInference:
        """Infer game state from screenshot using heuristics."""
        # Get image dimensions
        size = _estimate_image_size(screenshot_path)
        if not size:
            return ScreenshotInference(
                screen_valid=False, screen_type="unknown", whose_turn="unknown",
                regions=[], actionable_targets=[], summary="Cannot read screenshot",
                confidence=0.0,
            )

        img_w, img_h = size

        # Check if screen is valid (not all black/white)
        avg = _color_region_avg(screenshot_path, 0, 0, img_w, img_h)
        if avg and avg["brightness"] < 10:
            return ScreenshotInference(
                screen_valid=False, screen_type="unknown", whose_turn="unknown",
                regions=[], actionable_targets=[], summary="Screen appears black/empty",
                confidence=0.0,
            )

        # Get zones from profile or defaults
        zones = self._get_zones(profile)

        # Detect regions
        regions = []
        for zone_name, zone_def in zones.items():
            x = int(zone_def["rel_x"] * img_w)
            y = int(zone_def["rel_y"] * img_h)
            w = int(zone_def["rel_w"] * img_w)
            h = int(zone_def["rel_h"] * img_h)

            avg_color = _color_region_avg(screenshot_path, x, y, w, h)
            is_empty = _is_likely_empty_region(avg_color)

            # Determine if region is actionable
            is_actionable = False
            if zone_name == "draw_pile" and not is_empty:
                is_actionable = True  # Draw pile is always clickable
            elif zone_name == "hand" and not is_empty:
                is_actionable = True  # Hand area has playable cards

            regions.append(ScreenRegion(
                region_id=zone_name,
                region_type="button" if is_actionable else "unknown",
                label=f"{zone_name.replace('_', ' ').title()} area",
                x=x, y=y, width=w, height=h,
                confidence=0.6 if not is_empty else 0.3,
                is_actionable=is_actionable,
                metadata={"avg_brightness": avg_color["brightness"] if avg_color else 0},
            ))

        # Build actionable targets
        actionable = [r for r in regions if r.is_actionable]

        # Run visual extraction on detected zones
        visual_state = None
        try:
            zone_dicts = [
                {"id": r.region_id, "type": r.region_type, "x": r.x, "y": r.y, "width": r.width, "height": r.height}
                for r in regions
            ]
            visual_state = extract_from_screenshot(screenshot_path, zone_dicts)
        except Exception as exc:
            logger.warning("visual_extraction_failed error=%s", str(exc))

        # Determine screen type
        screen_type = "in_game" if any(r.is_actionable for r in regions) else "unknown"
        if visual_state and visual_state.screen_state != "unknown":
            screen_type = visual_state.screen_state

        # Build summary
        summary_parts = []
        if actionable:
            summary_parts.append(f"{len(actionable)} actionable regions")
        if visual_state:
            if visual_state.top_card:
                summary_parts.append(f"top: {visual_state.top_card.color} {visual_state.top_card.value}")
            if visual_state.hand_cards:
                summary_parts.append(f"hand: {len(visual_state.hand_cards)} cards")
        summary = ", ".join(summary_parts) if summary_parts else "No regions detected"

        # Use visual extraction confidence if available
        confidence = 0.5 if actionable else 0.2
        if visual_state and visual_state.confidence > 0:
            confidence = max(confidence, visual_state.confidence)

        raw_meta = {"image_size": [img_w, img_h], "zones_checked": len(zones)}
        if visual_state:
            # Carry the FULL per-card hand list (color/value/bounds/center) — not
            # just a count — so downstream execution can ground a chosen card to a
            # real screen coordinate. recognition_detail is the dict form from
            # recognition_to_dict(), which now includes absolute bounds + center.
            rec = visual_state.recognition_detail or {}
            raw_meta["visual_extraction"] = {
                "top_card": rec.get("top_card"),
                "hand_cards": rec.get("hand_cards", []),
                "discard_card": rec.get("discard_card"),
                "hand_count": len(visual_state.hand_cards),
                "crops_generated": visual_state.crops_generated,
                "extraction_errors": visual_state.extraction_errors,
            }

        return ScreenshotInference(
            screen_valid=True,
            screen_type=screen_type,
            whose_turn=visual_state.whose_turn if visual_state else "unknown",
            regions=regions,
            actionable_targets=actionable,
            summary=summary,
            confidence=confidence,
            raw_metadata=raw_meta,
        )

    def _get_zones(self, profile: dict | None) -> dict:
        """Get zone definitions from profile or defaults."""
        if profile and "layout_targets" in profile:
            # Profile provides relative zone definitions
            return profile["layout_targets"]
        return self._default_zones
