"""UNO visual extraction schema and card recognizer.

Structured schema for extracting game state from screenshot evidence.
Crops card regions from detected zones and runs card recognition.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from uno_perception.card_recognition import (
    CardRecognition,
    recognition_to_dict,
    recognize_cards_from_zones,
)

logger = logging.getLogger("visual_extraction")


@dataclass
class VisualCard:
    """A single detected card from screenshot."""
    card_id: str
    color: str              # "red" | "blue" | "green" | "yellow" | "wild" | "unknown"
    value: str              # "0"-"9" | "skip" | "reverse" | "draw_two" | "wild" | "unknown"
    confidence: float       # 0-1
    location: str           # "hand" | "discard" | "play_area" | "draw_pile"
    slot_index: int | None = None
    bounds: tuple[int, int, int, int] | None = None


@dataclass
class VisualGameState:
    """Structured game state extracted from screenshot."""
    top_card: VisualCard | None = None
    hand_cards: list[VisualCard] = field(default_factory=list)
    discard_card: VisualCard | None = None
    draw_pile_visible: bool = False
    direction: str = "unknown"     # "cw" | "ccw" | "unknown"
    whose_turn: str = "unknown"    # "self" | "opponent" | "unknown"
    screen_state: str = "unknown"  # "in_game" | "lobby" | "menu" | "unknown"
    confidence: float = 0.0
    extraction_errors: list[str] = field(default_factory=list)
    crops_generated: int = 0
    recognition_method: str = "heuristic"
    recognition_detail: dict[str, Any] = field(default_factory=dict)


def crop_region(
    screenshot_path: str,
    x: int, y: int, w: int, h: int,
    output_dir: str | None = None,
) -> str | None:
    """Crop a region from a screenshot and save as PNG."""
    try:
        from PIL import Image
        img = Image.open(screenshot_path)
        iw, ih = img.size
        
        x, y = max(0, x), max(0, y)
        w, h = min(w, iw - x), min(h, ih - y)
        if w <= 0 or h <= 0:
            return None
        
        cropped = img.crop((x, y, x + w, y + h))
        
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            path = os.path.join(output_dir, f"crop_{x}_{y}_{w}_{h}.png")
            cropped.save(path)
            return path
        return None
    except Exception:
        return None


class UNOVisualExtractor:
    """Extract UNO game state from screenshot using zones + card recognition.
    
    Pipeline:
    1. Use detected zones from HeuristicCanvasUNOPlugin
    2. Run card recognition on zones (crops + color analysis)
    3. Map recognition results to VisualGameState
    4. Return structured result with confidence scores
    """
    
    def __init__(self, screenshot_path: str, zones: list[dict], output_dir: str | None = None):
        self.screenshot_path = screenshot_path
        self.zones = zones
        self.output_dir = output_dir
        self.errors: list[str] = []
    
    def extract(self) -> VisualGameState:
        """Run full extraction pipeline with card recognition."""
        result = VisualGameState()
        
        # Run card recognition on all zones
        recognition = recognize_cards_from_zones(
            self.screenshot_path, self.zones, self.output_dir,
        )
        
        # Map recognition results to VisualGameState
        result.top_card = self._map_card(recognition.top_card) if recognition.top_card else None
        result.hand_cards = [self._map_card(c) for c in recognition.hand_cards]
        result.discard_card = self._map_card(recognition.discard_card) if recognition.discard_card else None
        result.draw_pile_visible = any(
            z.get("id") == "draw_pile" or z.get("type") == "draw_pile"
            for z in self.zones
        )
        
        # Determine screen state
        if result.hand_cards or result.discard_card:
            result.screen_state = "in_game"
        
        # Set top card from discard if not already set
        if not result.top_card and result.discard_card:
            result.top_card = result.discard_card
        
        # Copy recognition metadata
        result.confidence = recognition.overall_confidence
        result.extraction_errors = recognition.errors
        result.crops_generated = recognition.crops_generated
        result.recognition_method = recognition.recognition_method
        result.recognition_detail = recognition_to_dict(recognition)
        
        return result
    
    def _map_card(self, card: CardRecognition) -> VisualCard:
        """Map CardRecognition to VisualCard."""
        return VisualCard(
            card_id=card.card_id,
            color=card.color,
            value=card.value,
            confidence=card.overall_confidence,
            location=card.location,
            bounds=card.bounds,
        )


def extract_from_screenshot(
    screenshot_path: str,
    zones: list[dict],
    output_dir: str | None = None,
) -> VisualGameState:
    """Convenience function for extraction."""
    extractor = UNOVisualExtractor(screenshot_path, zones, output_dir)
    return extractor.extract()
