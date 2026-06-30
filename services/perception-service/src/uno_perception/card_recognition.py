"""Card identity recognizer — structured extraction from crops.

Takes cropped card regions and returns structured recognition results
with color, value, and per-card confidence scores.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("card_recognition")


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
    """Analyze color distribution of a cropped card image.
    
    Returns dict with dominant_color, color_scores, brightness, pixel_count.
    """
    try:
        from PIL import Image
        img = Image.open(crop_path)
        pixels = list(img.getdata())
        
        if not pixels:
            return {"dominant_color": "unknown", "color_scores": {}, "brightness": 0, "pixel_count": 0}
        
        total = len(pixels)
        
        # Count pixels per color
        scores = {"red": 0, "blue": 0, "green": 0, "yellow": 0, "white": 0, "black": 0}
        for r, g, b in pixels:
            if r > 200 and g > 200 and b > 200:
                scores["white"] += 1
            elif r < 30 and g < 30 and b < 30:
                scores["black"] += 1
            elif r > 150 and g < 100 and b < 100:
                scores["red"] += 1
            elif b > 150 and r < 100 and g < 100:
                scores["blue"] += 1
            elif g > 150 and r < 100 and b < 100:
                scores["green"] += 1
            elif r > 150 and g > 150 and b < 100:
                scores["yellow"] += 1
        
        # Find dominant color (excluding white/black background)
        game_colors = {k: v for k, v in scores.items() if k not in ("white", "black")}
        dominant = max(game_colors, key=game_colors.get) if any(game_colors.values()) else "unknown"
        
        # Calculate confidence based on color dominance
        if dominant != "unknown":
            confidence = min(1.0, scores[dominant] / (total * 0.3))  # 30% threshold
        else:
            confidence = 0.0
        
        # Brightness
        brightness = sum(r + g + b for r, g, b in pixels[:1000]) / (min(1000, total) * 3)
        
        return {
            "dominant_color": dominant,
            "color_scores": scores,
            "confidence": confidence,
            "brightness": brightness,
            "pixel_count": total,
        }
    except Exception as e:
        return {"dominant_color": "unknown", "color_scores": {}, "confidence": 0.0, "error": str(e)}


def recognize_card_from_crop(
    crop_path: str,
    card_id: str,
    location: str,
) -> CardRecognition:
    """Recognize a single card from a cropped image.
    
    Stage 1: Heuristic color analysis.
    Stage 2 (future): VLM structured extraction.
    Stage 3 (future): Template matching for value.
    """
    color_result = analyze_crop_colors(crop_path)
    
    # For now, value is always "unknown" from heuristic
    # VLM integration would fill this in
    value = "unknown"
    value_confidence = 0.0
    
    return CardRecognition(
        card_id=card_id,
        color=color_result["dominant_color"],
        color_confidence=color_result["confidence"],
        value=value,
        value_confidence=value_confidence,
        overall_confidence=color_result["confidence"] * 0.7,  # penalize for unknown value
        location=location,
        crop_path=crop_path,
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
    2. Run color analysis on each crop
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
        
        # Crop region
        crop_path = None
        try:
            from PIL import Image
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
        except Exception as e:
            result.errors.append(f"crop_failed_{zone_id}: {e}")
        
        if not crop_path:
            continue
        
        result.crops_used += 1
        
        # Recognize card from crop
        card = recognize_card_from_crop(
            crop_path,
            card_id=f"{zone_id}_0",
            location=zone_id,
        )
        
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
        return {
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
