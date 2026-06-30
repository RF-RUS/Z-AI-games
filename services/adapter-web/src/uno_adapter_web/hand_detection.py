"""Screenshot-based game detection for canvas/WebGL games.

Uses Pillow for:
- Card detection via color segmentation in hand region
- Card identity detection via color histogram comparison (number/value)
- Draw pile detection via position heuristics
- Screen state detection (in_game vs lobby)
- Live calibration of card region coordinates
"""

from __future__ import annotations

import colorsys
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter

# UNO card colors in RGB ranges
UNO_COLORS = {
    "red": {"h_range": (340, 20), "s_min": 0.4, "v_min": 0.3},
    "blue": {"h_range": (200, 260), "s_min": 0.3, "v_min": 0.2},
    "green": {"h_range": (80, 160), "s_min": 0.3, "v_min": 0.2},
    "yellow": {"h_range": (40, 70), "s_min": 0.3, "v_min": 0.4},
}

# UNO number values
UNO_VALUES = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "skip", "reverse", "draw_two", "wild"]

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


@dataclass
class DetectedCard:
    color: str
    number: str | None = None
    slot_index: int = 0
    bbox: dict[str, int] = field(default_factory=dict)
    click_x: int = 0
    click_y: int = 0
    confidence: float = 0.0
    number_confidence: float = 0.0


@dataclass
class ActionGrounding:
    hand: list[DetectedCard]
    draw_pile: dict[str, int] | None = None
    draw_pile_click: tuple[int, int] | None = None
    detection_confidence: float = 0.0
    method: str = "pillow_color_segmentation"


@dataclass
class CalibrationResult:
    hand_region: dict[str, int]
    draw_region: dict[str, int]
    hand_slots: list[dict[str, Any]]
    draw_area: dict[str, Any] | None
    card_count: int
    canvas_width: int
    canvas_height: int


def _rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360, s, v


def _classify_pixel_color(r: int, g: int, b: int) -> str | None:
    if r > 200 and g > 200 and b > 200:
        return None
    if r < 30 and g < 30 and b < 30:
        return None
    h, s, v = _rgb_to_hsv(r, g, b)
    if s < 0.2 or v < 0.15:
        return None
    for color_name, spec in UNO_COLORS.items():
        h_min, h_max = spec["h_range"]
        if h_min > h_max:
            in_range = h >= h_min or h <= h_max
        else:
            in_range = h_min <= h <= h_max
        if in_range and s >= spec["s_min"] and v >= spec["v_min"]:
            return color_name
    return None


def _find_shape_regions(
    img: Image.Image, region: dict[str, int] | None = None,
    min_area: int = 2000, max_area_ratio: float = 0.15,
    min_aspect: float = 0.3, max_aspect: float = 3.5,
) -> list[dict[str, Any]]:
    """Find rectangular regions via edge detection — shape-based, not color-based.

    Works on red-on-red canvases where color segmentation fails.
    Uses grayscale edge detection + scanline rectangle finding.
    Returns list of {bbox, area, aspect_ratio, edge_density, confidence}.
    """
    if region:
        crop = img.crop((
            region["x"], region["y"],
            region["x"] + region["width"],
            region["y"] + region["height"],
        ))
        offset_x, offset_y = region["x"], region["y"]
    else:
        crop = img
        offset_x, offset_y = 0, 0

    w, h = crop.size
    if w < 20 or h < 20:
        return []

    gray = crop.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_data = edges.load()

    crop_area = w * h

    step_x = max(1, w // 60)
    step_y = max(1, h // 40)

    edge_points = []
    for y in range(1, h - 1, step_y):
        for x in range(1, w - 1, step_x):
            val = edge_data[x, y]
            if val > 40:
                edge_points.append((x, y))

    if not edge_points:
        return []

    regions = []
    used = set()
    for px, py in edge_points:
        if (px, py) in used:
            continue
        xs = [px]
        ys = [py]
        used.add((px, py))
        queue = [(px, py)]
        while queue:
            cx, cy = queue.pop()
            for dx in range(-step_x * 3, step_x * 3 + 1, step_x):
                for dy in range(-step_y * 3, step_y * 3 + 1, step_y):
                    nx, ny = cx + dx, cy + dy
                    if (nx, ny) in used or nx < 0 or ny < 0 or nx >= w or ny >= h:
                        continue
                    if edge_data[nx, ny] > 40:
                        used.add((nx, ny))
                        xs.append(nx)
                        ys.append(ny)
                        queue.append((nx, ny))

        if len(xs) < 5:
            continue

        bbox_w = max(xs) - min(xs)
        bbox_h = max(ys) - min(ys)
        bbox_area = bbox_w * bbox_h

        if bbox_area < min_area or bbox_area > crop_area * max_area_ratio:
            continue

        aspect = bbox_w / max(1, bbox_h)
        if aspect < min_aspect or aspect > max_aspect:
            continue

        edge_density = len(xs) / max(1, bbox_area) * 100
        confidence = min(0.9, edge_density * 2 + 0.3)

        regions.append({
            "bbox": {
                "x": offset_x + min(xs),
                "y": offset_y + min(ys),
                "width": bbox_w,
                "height": bbox_h,
            },
            "area": bbox_area,
            "aspect_ratio": round(aspect, 2),
            "edge_density": round(edge_density, 3),
            "confidence": round(confidence, 2),
            "edge_points": len(xs),
        })

    regions.sort(key=lambda r: r["area"], reverse=True)
    return regions


def _find_color_regions(
    img: Image.Image, region: dict[str, int] | None = None, min_area: int = 200,
    max_area_ratio: float = 0.15,
) -> list[dict[str, Any]]:
    """Find rectangular regions dominated by a UNO card color.

    Filters out regions that are too large (likely game background) or too small.
    max_area_ratio: maximum fraction of crop area a single region can occupy (0.0-1.0).
    """
    if region:
        crop = img.crop((
            region["x"], region["y"],
            region["x"] + region["width"],
            region["y"] + region["height"],
        ))
        offset_x, offset_y = region["x"], region["y"]
    else:
        crop = img
        offset_x, offset_y = 0, 0

    w, h = crop.size
    if w < 10 or h < 10:
        return []

    step_x = max(1, w // 40)
    step_y = max(1, h // 30)
    color_grid: dict[str, list[tuple[int, int]]] = {}

    for y in range(0, h, step_y):
        for x in range(0, w, step_x):
            r, g, b = crop.getpixel((x, y))[:3]
            c = _classify_pixel_color(r, g, b)
            if c:
                color_grid.setdefault(c, []).append((x, y))

    regions = []
    crop_area = w * h
    for color, points in color_grid.items():
        if len(points) < 3:
            continue
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        bbox_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if bbox_area < min_area:
            continue
        if crop_area > 0 and bbox_area / crop_area > max_area_ratio:
            continue
        regions.append({
            "color": color,
            "bbox": {
                "x": offset_x + min(xs),
                "y": offset_y + min(ys),
                "width": max(xs) - min(xs),
                "height": max(ys) - min(ys),
            },
            "pixel_ratio": len(points) / max(1, (w * h) // (step_x * step_y)),
        })

    regions.sort(key=lambda r: r["bbox"]["x"])
    return regions


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


def detect_hand_cards(
    img: Image.Image,
    hand_region: dict[str, int],
    canvas_width: int = 1280,
    canvas_height: int = 800,
) -> list[DetectedCard]:
    color_regions = _find_color_regions(img, hand_region, min_area=100, max_area_ratio=0.40)
    shape_regions = _find_shape_regions(img, hand_region, min_area=2000, max_area_ratio=0.30)

    all_regions = []
    seen_bboxes = set()

    for r in shape_regions:
        bbox = r["bbox"]
        key = (bbox["x"] // 20, bbox["y"] // 20, bbox["width"] // 20, bbox["height"] // 20)
        if key not in seen_bboxes:
            seen_bboxes.add(key)
            dominant_color = _dominant_color_in_region(img, bbox)
            all_regions.append({
                "color": dominant_color or "unknown",
                "bbox": bbox,
                "confidence": r["confidence"],
                "source": "shape",
                "aspect_ratio": r["aspect_ratio"],
                "edge_density": r["edge_density"],
            })

    for r in color_regions:
        bbox = r["bbox"]
        key = (bbox["x"] // 20, bbox["y"] // 20, bbox["width"] // 20, bbox["height"] // 20)
        if key not in seen_bboxes:
            seen_bboxes.add(key)
            all_regions.append({
                "color": r.get("color", "unknown"),
                "bbox": bbox,
                "confidence": min(0.9, r.get("pixel_ratio", 0.1) * 10),
                "source": "color",
            })

    all_regions.sort(key=lambda r: r["bbox"]["x"])
    cards = []
    for i, region in enumerate(all_regions):
        bbox = region["bbox"]
        cx = bbox["x"] + bbox["width"] // 2
        cy = bbox["y"] + bbox["height"] // 2
        number, number_conf = _detect_card_number(img, bbox)
        cards.append(DetectedCard(
            color=region["color"],
            number=number,
            slot_index=i,
            bbox=bbox,
            click_x=cx,
            click_y=cy,
            confidence=region["confidence"],
            number_confidence=number_conf,
        ))
    return cards


def _dominant_color_in_region(img: Image.Image, bbox: dict[str, int]) -> str | None:
    """Find the dominant UNO color in a bounding box region."""
    try:
        crop = img.crop((
            bbox["x"], bbox["y"],
            bbox["x"] + bbox["width"],
            bbox["y"] + bbox["height"],
        ))
        w, h = crop.size
        if w < 5 or h < 5:
            return None
        color_counts: dict[str, int] = {}
        step = max(1, min(w, h) // 8)
        for y in range(0, h, step):
            for x in range(0, w, step):
                r, g, b = crop.getpixel((x, y))[:3]
                c = _classify_pixel_color(r, g, b)
                if c:
                    color_counts[c] = color_counts.get(c, 0) + 1
        if not color_counts:
            return None
        return max(color_counts, key=color_counts.get)
    except Exception:
        return None


def detect_draw_pile(
    img: Image.Image,
    draw_region: dict[str, int],
) -> dict[str, Any] | None:
    color_regions = _find_color_regions(img, draw_region, min_area=100)
    shape_regions = _find_shape_regions(img, draw_region, min_area=1000, max_area_ratio=0.30)

    best = None
    best_score = 0

    for r in shape_regions:
        bbox = r["bbox"]
        score = r["confidence"] * r["area"] / 10000
        if score > best_score:
            best_score = score
            best = {"bbox": bbox, "color": _dominant_color_in_region(img, bbox) or "unknown",
                    "confidence": r["confidence"], "source": "shape"}

    for r in color_regions:
        bbox = r["bbox"]
        area = bbox["width"] * bbox["height"]
        score = min(0.9, r.get("pixel_ratio", 0.1) * 10) * area / 10000
        if score > best_score:
            best_score = score
            best = {"bbox": bbox, "color": r.get("color", "unknown"),
                    "confidence": min(0.8, r.get("pixel_ratio", 0.1) * 8), "source": "color"}

    if not best:
        return None

    bbox = best["bbox"]
    return {
        "bbox": bbox,
        "click_x": bbox["x"] + bbox["width"] // 2,
        "click_y": bbox["y"] + bbox["height"] // 2,
        "color": best["color"],
        "confidence": best["confidence"],
    }


def detect_game_elements(
    img: Image.Image,
    hand_region: dict[str, int] | None = None,
    draw_region: dict[str, int] | None = None,
    canvas_width: int = 1280,
    canvas_height: int = 800,
) -> ActionGrounding:
    """Full game element detection from screenshot.

    Detection priority:
    1. Color-based card detection in hand_region
    2. Shape-based card detection (edge/contour)
    3. Shape-based table/playing area detection (full image)
    4. Color-based draw pile detection in draw_region
    """
    if hand_region is None:
        hand_region = {"x": 0, "y": int(canvas_height * 0.70), "width": canvas_width, "height": int(canvas_height * 0.25)}
    if draw_region is None:
        draw_region = {"x": int(canvas_width * 0.35), "y": int(canvas_height * 0.25), "width": int(canvas_width * 0.30), "height": int(canvas_height * 0.25)}

    hand_cards = detect_hand_cards(img, hand_region, canvas_width, canvas_height)
    if not hand_cards:
        fallback_region = {"x": 0, "y": int(canvas_height * 0.5), "width": canvas_width, "height": int(canvas_height * 0.45)}
        hand_cards = detect_hand_cards(img, fallback_region, canvas_width, canvas_height)

    draw = detect_draw_pile(img, draw_region)

    table_landmark = None
    if not draw:
        table_shapes = _find_shape_regions(img, min_area=10000, max_area_ratio=0.25)
        if table_shapes:
            best = max(table_shapes, key=lambda s: s["area"])
            table_landmark = best["bbox"]
            draw = {
                "bbox": table_landmark,
                "click_x": table_landmark["x"] + table_landmark["width"] // 2,
                "click_y": table_landmark["y"] + table_landmark["height"] // 2,
                "color": "table",
                "confidence": best["confidence"],
            }

    confidence = 0.0
    if hand_cards:
        avg_conf = sum(c.confidence for c in hand_cards) / len(hand_cards)
        confidence = min(0.9, avg_conf * 0.7 + (0.2 if draw else 0.0))
    elif draw:
        confidence = max(0.3, draw.get("confidence", 0.3))

    return ActionGrounding(
        hand=hand_cards,
        draw_pile=draw["bbox"] if draw else None,
        draw_pile_click=(draw["click_x"], draw["click_y"]) if draw else None,
        detection_confidence=confidence,
    )


def detect_screen_state(
    img: Image.Image,
    lobby_region: dict[str, int] | None = None,
) -> str:
    w, h = img.size
    game_area = lobby_region or {"x": 0, "y": 0, "width": w, "height": int(h * 0.7)}

    # Check with generous filter (backgrounds allowed for state classification)
    regions_all = _find_color_regions(img, game_area, min_area=500, max_area_ratio=0.80)
    # Check with strict filter (backgrounds excluded for card detection)
    regions_filtered = _find_color_regions(img, game_area, min_area=500, max_area_ratio=0.15)

    # If any filtered (non-background) color regions exist, game is active
    if len(regions_filtered) >= 1:
        return "in_game"

    # If large background regions exist, the game is likely rendering
    if len(regions_all) >= 1:
        return "in_game"

    return "unknown"


# --- Calibration ---

def calibrate_from_screenshot(
    img: Image.Image,
    canvas_width: int = 1280,
    canvas_height: int = 800,
) -> CalibrationResult:
    """Auto-detect hand region, card positions, and draw area from a live screenshot.

    Uses color detection to find card clusters and infer region boundaries.
    """
    w, h = img.size

    all_regions = _find_color_regions(img, min_area=150)
    if not all_regions:
        return CalibrationResult(
            hand_region={"x": 0, "y": int(h * 0.70), "width": w, "height": int(h * 0.25)},
            draw_region={"x": int(w * 0.35), "y": int(h * 0.25), "width": int(w * 0.30), "height": int(h * 0.25)},
            hand_slots=[], draw_area=None, card_count=0,
            canvas_width=w, canvas_height=h,
        )

    card_bboxes = [r["bbox"] for r in all_regions]
    xs = [b["x"] for b in card_bboxes]
    ys = [b["y"] for b in card_bboxes]
    card_min_y = min(ys)
    card_max_y = max(ys)
    card_min_x = min(xs)
    card_max_x = max(xs)

    is_hand = card_min_y > h * 0.5
    if is_hand:
        hand_y_start = max(0, card_min_y - 20)
        hand_y_end = min(h, card_max_y + 20)
        hand_x_start = max(0, card_min_x - 20)
        hand_x_end = min(w, card_max_x + 20)
        hand_region = {
            "x": hand_x_start, "y": hand_y_start,
            "width": hand_x_end - hand_x_start, "height": hand_y_end - hand_y_start,
        }
        draw_region = {"x": int(w * 0.35), "y": int(h * 0.20), "width": int(w * 0.30), "height": int(h * 0.25)}
    else:
        hand_region = {"x": 0, "y": int(h * 0.70), "width": w, "height": int(h * 0.25)}
        draw_region = {"x": card_min_x, "y": card_min_y, "width": card_max_x - card_min_x, "height": card_max_y - card_min_y}

    hand_cards = detect_hand_cards(img, hand_region, w, h)
    hand_slots = []
    for i, card in enumerate(hand_cards):
        hand_slots.append({
            "slot_id": f"hand_slot_{i}",
            "x": card.bbox["x"],
            "y": card.bbox["y"],
            "width": card.bbox["width"],
            "height": card.bbox["height"],
            "click_x": card.click_x,
            "click_y": card.click_y,
            "color": card.color,
        })

    draw = detect_draw_pile(img, draw_region)
    draw_area = None
    if draw:
        draw_area = {
            "x": draw["bbox"]["x"], "y": draw["bbox"]["y"],
            "width": draw["bbox"]["width"], "height": draw["bbox"]["height"],
            "click_x": draw["click_x"], "click_y": draw["click_y"],
        }

    return CalibrationResult(
        hand_region=hand_region,
        draw_region=draw_region,
        hand_slots=hand_slots,
        draw_area=draw_area,
        card_count=len(hand_slots),
        canvas_width=w,
        canvas_height=h,
    )


def save_calibration(result: CalibrationResult, profile_path: str | Path) -> dict:
    """Update scuffed-uno-web.json with calibrated coordinates.

    Returns a report dict with old vs new values.
    """
    profile_path = Path(profile_path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    old_slots = profile.get("layout_targets", {}).copy()

    if "layout_targets" not in profile:
        profile["layout_targets"] = {}

    profile["layout_targets"]["hand_area"] = result.hand_region
    profile["layout_targets"]["draw_area"] = result.draw_region

    for slot in result.hand_slots:
        profile["layout_targets"][slot["slot_id"]] = {
            "x": slot["x"], "y": slot["y"],
            "width": slot["width"], "height": slot["height"],
            "click_x": slot["click_x"], "click_y": slot["click_y"],
            "label": f"Calibrated {slot['slot_id']} ({slot['color']})",
        }

    if result.draw_area:
        profile["layout_targets"]["draw"] = {
            "x": result.draw_area["x"], "y": result.draw_area["y"],
            "width": result.draw_area["width"], "height": result.draw_area["height"],
            "click_x": result.draw_area["click_x"], "click_y": result.draw_area["click_y"],
            "label": "Calibrated draw pile",
        }

    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

    return {
        "profile_id": profile.get("profile_id"),
        "calibrated_slots": result.card_count,
        "canvas_size": f"{result.canvas_width}x{result.canvas_height}",
        "hand_region": result.hand_region,
        "draw_region": result.draw_region,
        "draw_area": result.draw_area,
        "old_hand_area": old_slots.get("hand_area"),
        "slots": result.hand_slots,
    }
