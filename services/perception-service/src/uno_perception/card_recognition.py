"""Card identity recognizer — structured extraction from crops.

Takes cropped card regions and returns structured recognition results
with color, value, and per-card confidence scores.
"""

from __future__ import annotations

import colorsys
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageFilter

logger = logging.getLogger("card_recognition")


# ── HSV color classification (shared with adapter-web hand_detection) ──

UNO_COLORS_HSV = {
    "red": {"h_range": (340, 20), "s_min": 0.4, "v_min": 0.3},
    "blue": {"h_range": (200, 260), "s_min": 0.3, "v_min": 0.2},
    "green": {"h_range": (80, 160), "s_min": 0.3, "v_min": 0.2},
    "yellow": {"h_range": (40, 70), "s_min": 0.3, "v_min": 0.4},
}


def _rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360, s, v


def _classify_pixel_color_hsv(r: int, g: int, b: int) -> str | None:
    """Classify a pixel into UNO color using HSV (more robust than RGB thresholds)."""
    if r > 200 and g > 200 and b > 200:
        return None
    if r < 30 and g < 30 and b < 30:
        return None
    h, s, v = _rgb_to_hsv(r, g, b)
    if s < 0.2 or v < 0.15:
        return None
    for color_name, spec in UNO_COLORS_HSV.items():
        h_min, h_max = spec["h_range"]
        if h_min > h_max:
            in_range = h >= h_min or h <= h_max
        else:
            in_range = h_min <= h <= h_max
        if in_range and s >= spec["s_min"] and v >= spec["v_min"]:
            return color_name
    return None


# ── Value detection via brightness profile matching ──

# Number detection via brightness pattern — each digit has a distinct vertical profile
_NUMBER_BRIGHTNESS_PROFILES: dict[str, list[float]] = {
    "0": [0.7, 0.9, 0.9, 0.9, 0.9, 0.9, 0.7],
    "1": [0.3, 0.8, 0.3, 0.3, 0.3, 0.3, 0.9],
    "2": [0.7, 0.9, 0.1, 0.7, 0.9, 0.9, 0.7],
    "3": [0.7, 0.9, 0.1, 0.7, 0.1, 0.9, 0.7],
    "4": [0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1],
    "5": [0.9, 0.1, 0.9, 0.1, 0.1, 0.9, 0.7],
    "6": [0.7, 0.9, 0.1, 0.9, 0.9, 0.9, 0.7],
    "7": [0.9, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1],
    "8": [0.7, 0.9, 0.9, 0.7, 0.9, 0.9, 0.7],
    "9": [0.7, 0.9, 0.9, 0.9, 0.1, 0.9, 0.7],
}


def _detect_card_number(img: Image.Image, card_bbox: dict[str, int]) -> tuple[str | None, float]:
    """Detect the number/value on a card using brightness profile matching.

    Extracts the card region, converts to grayscale, computes vertical
    brightness profile, and compares against known UNO number profiles.

    Returns (number, confidence).
    """
    try:
        crop = img.crop((
            card_bbox["x"], card_bbox["y"],
            card_bbox["x"] + card_bbox["width"],
            card_bbox["y"] + card_bbox["height"],
        ))
        gray = crop.convert("L")
        w, h = gray.size
        if w < 5 or h < 5:
            return None, 0.0

        num_bands = 7
        band_height = max(1, h // num_bands)
        profile = []
        for i in range(num_bands):
            y0 = i * band_height
            y1 = min((i + 1) * band_height, h)
            band_pixels = []
            for y in range(y0, y1, max(1, band_height // 3)):
                for x in range(0, w, max(1, w // 10)):
                    band_pixels.append(gray.getpixel((x, y)))
            avg = sum(band_pixels) / max(1, len(band_pixels)) / 255.0
            profile.append(1.0 if avg > 0.6 else 0.0)

        best_match = None
        best_score = -1.0
        for digit, ref_profile in _NUMBER_BRIGHTNESS_PROFILES.items():
            score = sum(1.0 - abs(a - b) for a, b in zip(profile, ref_profile)) / len(ref_profile)
            if score > best_score:
                best_score = score
                best_match = digit

        confidence = best_score if best_score > 0.5 else 0.0
        return best_match, confidence

    except Exception:
        return None, 0.0


def _detect_special_card(img: Image.Image, card_bbox: dict[str, int], color: str) -> tuple[str | None, float]:
    """Detect special card values (skip, reverse, draw_two) by symbol shape analysis.

    Uses edge detection on the card center region to identify symbol patterns.
    Returns (value, confidence).
    """
    try:
        crop = img.crop((
            card_bbox["x"], card_bbox["y"],
            card_bbox["x"] + card_bbox["width"],
            card_bbox["y"] + card_bbox["height"],
        ))
        w, h = crop.size
        if w < 10 or h < 10:
            return None, 0.0

        # Analyze center region for symbol detection
        center_x = w // 2
        center_y = h // 2
        sample_w = max(10, w // 3)
        sample_h = max(10, h // 3)
        center_crop = crop.crop((
            center_x - sample_w // 2, center_y - sample_h // 2,
            center_x + sample_w // 2, center_y + sample_h // 2,
        ))

        gray = center_crop.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_pixels = list(edges.getdata())
        total = len(edge_pixels)
        if total == 0:
            return None, 0.0

        edge_density = sum(1 for p in edge_pixels if p > 30) / total

        # High edge density in center suggests a symbol (skip/reverse/draw_two)
        # Low edge density suggests a number card
        if edge_density > 0.15:
            # Analyze edge direction for symbol type
            w_edges, h_edges = edges.size
            vertical_edges = 0
            horizontal_edges = 0
            for y in range(1, h_edges - 1):
                for x in range(1, w_edges - 1):
                    px = edges.getpixel((x, y))
                    if px > 30:
                        left = edges.getpixel((x - 1, y))
                        right = edges.getpixel((x + 1, y))
                        top = edges.getpixel((x, y - 1))
                        bottom = edges.getpixel((x, y + 1))
                        if abs(int(px) - int(left)) + abs(int(px) - int(right)) > abs(int(px) - int(top)) + abs(int(px) - int(bottom)):
                            vertical_edges += 1
                        else:
                            horizontal_edges += 1

            total_edges = vertical_edges + horizontal_edges
            if total_edges > 0:
                v_ratio = vertical_edges / total_edges
                # Skip: two horizontal bars
                if 0.3 < v_ratio < 0.5 and edge_density > 0.2:
                    return "skip", min(0.6, edge_density)
                # Reverse: two triangles (high vertical + horizontal)
                elif v_ratio > 0.5 and edge_density > 0.2:
                    return "reverse", min(0.6, edge_density)
                # Draw two: denser pattern
                elif edge_density > 0.3:
                    return "draw_two", min(0.5, edge_density)

        return None, 0.0

    except Exception:
        return None, 0.0


@dataclass
class CardRecognition:
    """Result of recognizing a single card from a crop."""
    card_id: str
    color: str              # "red" | "blue" | "green" | "yellow" | "wild" | "unknown"
    color_confidence: float # 0-1
    value: str              # "0"-"9" | "skip" | "reverse" | "draw_two" | "wild" | "unknown"
    value_confidence: float # 0-1
    overall_confidence: float
    location: str           # "hand" | "discard" | "play_area"
    crop_path: str | None = None
    bounds: tuple[int, int, int, int] | None = None  # (x, y, w, h) of the card region
    recognition_method: str = "heuristic"  # "heuristic" | "vlm" | "template"
    uncertainty_reason: str | None = None


@dataclass
class CardRecognitionResult:
    """Full recognition result for a screenshot."""
    top_card: CardRecognition | None = None
    hand_cards: list[CardRecognition] = field(default_factory=list)
    discard_card: CardRecognition | None = None
    overall_confidence: float = 0.0
    recognition_method: str = "heuristic"
    crops_generated: int = 0
    crops_used: int = 0
    errors: list[str] = field(default_factory=list)
    debug_data: dict[str, Any] = field(default_factory=dict)


# Color detection thresholds
COLOR_THRESHOLDS = {
    "red": {"r_min": 150, "r_range": 80, "g_max": 100, "b_max": 100},
    "blue": {"b_min": 150, "b_range": 80, "r_max": 100, "g_max": 100},
    "green": {"g_min": 150, "g_range": 80, "r_max": 100, "b_max": 100},
    "yellow": {"r_min": 150, "g_min": 150, "b_max": 100},
}


def analyze_crop_colors(crop_path: str) -> dict[str, Any]:
    """Analyze color distribution of a cropped card image using HSV classification.

    Returns dict with dominant_color, color_scores, brightness, pixel_count.
    """
    try:
        img = Image.open(crop_path)
        w, h = img.size
        if w < 2 or h < 2:
            return {"dominant_color": "unknown", "color_scores": {}, "brightness": 0, "pixel_count": 0}

        # Sample pixels for efficiency
        step_x = max(1, w // 30)
        step_y = max(1, h // 30)
        scores: dict[str, int] = {"red": 0, "blue": 0, "green": 0, "yellow": 0, "white": 0, "black": 0}
        total_sampled = 0
        brightness_sum = 0.0

        for y in range(0, h, step_y):
            for x in range(0, w, step_x):
                r, g, b = img.getpixel((x, y))[:3]
                total_sampled += 1
                brightness_sum += (r + g + b) / 3.0

                # Background checks
                if r > 200 and g > 200 and b > 200:
                    scores["white"] += 1
                    continue
                if r < 30 and g < 30 and b < 30:
                    scores["black"] += 1
                    continue

                # HSV-based classification (more robust than RGB thresholds)
                c = _classify_pixel_color_hsv(r, g, b)
                if c:
                    scores[c] += 1

        total = max(1, total_sampled)

        # Find dominant color (excluding white/black background)
        game_colors = {k: v for k, v in scores.items() if k not in ("white", "black")}
        dominant = max(game_colors, key=game_colors.get) if any(game_colors.values()) else "unknown"

        # Calculate confidence based on color dominance
        if dominant != "unknown" and scores[dominant] > 0:
            confidence = min(1.0, scores[dominant] / (total * 0.2))
        else:
            confidence = 0.0

        brightness = brightness_sum / total

        return {
            "dominant_color": dominant,
            "color_scores": scores,
            "confidence": confidence,
            "brightness": brightness,
            "pixel_count": total_sampled,
        }
    except Exception as e:
        return {"dominant_color": "unknown", "color_scores": {}, "confidence": 0.0, "error": str(e)}


def recognize_card_from_crop(
    crop_path: str,
    card_id: str,
    location: str,
    screenshot_path: str | None = None,
    card_bbox: dict[str, int] | None = None,
) -> CardRecognition:
    """Recognize a single card from a cropped image.

    Uses HSV-based color classification + brightness profile value detection.
    Optionally uses screenshot + bbox for value detection on the full image.
    """
    color_result = analyze_crop_colors(crop_path)

    # Value detection: use full screenshot if available, otherwise try from crop
    value = "unknown"
    value_confidence = 0.0

    if screenshot_path and card_bbox:
        try:
            screenshot = Image.open(screenshot_path)
            # Try digit detection first
            digit, digit_conf = _detect_card_number(screenshot, card_bbox)
            if digit and digit_conf > 0.5:
                value = digit
                value_confidence = digit_conf
            else:
                # Try special card detection
                special, special_conf = _detect_special_card(screenshot, card_bbox, color_result["dominant_color"])
                if special and special_conf > 0.4:
                    value = special
                    value_confidence = special_conf
        except Exception as e:
            logger.debug("Value detection failed for %s: %s", card_id, e)

    # Confidence calculation: value detection boosts overall confidence
    if value != "unknown":
        overall = color_result["confidence"] * 0.5 + value_confidence * 0.5
    else:
        overall = color_result["confidence"] * 0.7  # penalize for unknown value

    # Build bounds tuple if bbox available
    bounds = None
    if card_bbox:
        bounds = (card_bbox["x"], card_bbox["y"], card_bbox["width"], card_bbox["height"])

    return CardRecognition(
        card_id=card_id,
        color=color_result["dominant_color"],
        color_confidence=color_result["confidence"],
        value=value,
        value_confidence=value_confidence,
        overall_confidence=overall,
        location=location,
        crop_path=crop_path,
        bounds=bounds,
        recognition_method="heuristic",
        uncertainty_reason="value not determined" if value == "unknown" else None,
    )


def recognize_cards_from_zones(
    screenshot_path: str,
    zones: list[dict],
    output_dir: str | None = None,
) -> CardRecognitionResult:
    """Recognize cards from detected zones.

    Pipeline:
    1. For each zone, crop the region
    2. Run color analysis + value detection on each crop
    3. Map results to CardRecognition objects
    4. Build structured result
    """
    result = CardRecognitionResult()

    for zone in zones:
        zone_id = zone.get("id", "unknown")
        zone_type = zone.get("type", "unknown")
        x = zone.get("x", 0)
        y = zone.get("y", 0)
        w = zone.get("width", 0)
        h = zone.get("height", 0)

        # Crop region. Recognition needs a crop file on disk; when no output_dir
        # is given (the production path), write to a temp file so recognition
        # STILL RUNS — previously it silently skipped every card without an
        # output_dir, so real sessions recognized nothing.
        crop_path = None
        cx = cy = cw = ch = 0
        try:
            img = Image.open(screenshot_path)
            iw, ih = img.size
            cx, cy = max(0, x), max(0, y)
            cw, ch = min(w, iw - cx), min(h, ih - cy)
            if cw > 0 and ch > 0:
                cropped = img.crop((cx, cy, cx + cw, cy + ch))
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)
                    crop_path = os.path.join(output_dir, f"crop_{zone_id}_{cx}_{cy}.png")
                    cropped.save(crop_path)
                    result.crops_generated += 1
                else:
                    fd, crop_path = tempfile.mkstemp(prefix=f"crop_{zone_id}_", suffix=".png")
                    os.close(fd)
                    cropped.save(crop_path)
        except Exception as e:
            result.errors.append(f"crop_failed_{zone_id}: {e}")

        if not crop_path:
            continue

        result.crops_used += 1

        # Build bbox for value detection
        card_bbox = {"x": cx, "y": cy, "width": cw, "height": ch}

        # Recognize card from crop (with value detection)
        try:
            card = recognize_card_from_crop(
                crop_path,
                card_id=f"{zone_id}_0",
                location=zone_id,
                screenshot_path=screenshot_path,
                card_bbox=card_bbox,
            )
        finally:
            if not output_dir:  # temp crop — clean up
                try:
                    os.remove(crop_path)
                except OSError:
                    pass

        # Map to game state
        if zone_id == "hand" or zone_type == "hand":
            result.hand_cards.append(card)
        elif zone_id == "play_area" or zone_type == "play_area":
            result.discard_card = card
        elif zone_id == "draw_pile" or zone_type == "draw_pile":
            # Draw pile doesn't have a visible card to recognize
            pass
    
    # Set top card from discard
    if result.discard_card:
        result.top_card = result.discard_card
    
    # Calculate overall confidence
    confidences = []
    if result.top_card:
        confidences.append(result.top_card.overall_confidence)
    for card in result.hand_cards:
        confidences.append(card.overall_confidence)
    result.overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    
    result.recognition_method = "heuristic"
    
    return result


def recognition_to_dict(result: CardRecognitionResult) -> dict[str, Any]:
    """Convert recognition result to JSON-serializable dict."""
    def card_dict(card: CardRecognition) -> dict:
        d = {
            "card_id": card.card_id,
            "color": card.color,
            "color_confidence": round(card.color_confidence, 3),
            "value": card.value,
            "value_confidence": round(card.value_confidence, 3),
            "overall_confidence": round(card.overall_confidence, 3),
            "location": card.location,
            "recognition_method": card.recognition_method,
            "uncertainty_reason": card.uncertainty_reason,
        }
        # Absolute screenshot bounds (x, y, w, h) + click center — required to
        # GROUND an action to a real card coordinate in the windows executor.
        # Without these the detected card cannot be clicked.
        if card.bounds:
            x, y, w, h = card.bounds
            d["bounds"] = {"x": x, "y": y, "width": w, "height": h}
            d["center"] = {"x": x + w // 2, "y": y + h // 2}
        return d
    
    return {
        "top_card": card_dict(result.top_card) if result.top_card else None,
        "hand_cards": [card_dict(c) for c in result.hand_cards],
        "discard_card": card_dict(result.discard_card) if result.discard_card else None,
        "overall_confidence": round(result.overall_confidence, 3),
        "recognition_method": result.recognition_method,
        "crops_generated": result.crops_generated,
        "crops_used": result.crops_used,
        "errors": result.errors,
    }
