"""Screenshot perception plugin protocol.

Generic interface for plugins that extract game state from screenshots.
Used when DOM/UIA evidence is unavailable (canvas/WebGL games).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ScreenRegion:
    """A detected rectangular region in the screenshot."""
    region_id: str
    region_type: str              # "hand" | "play_area" | "draw_pile" | "button" | "unknown"
    label: str                    # human-readable: "Hand area", "Draw pile"
    x: int
    y: int
    width: int
    height: int
    confidence: float             # 0-1
    is_actionable: bool           # can the agent click this?
    metadata: dict = field(default_factory=dict)


@dataclass
class ScreenshotInference:
    """Result of screenshot-based perception."""
    screen_valid: bool            # is the screenshot a valid game screen?
    screen_type: str              # "in_game" | "lobby" | "menu" | "unknown"
    whose_turn: str               # "self" | "opponent" | "unknown"
    regions: list[ScreenRegion]   # detected regions
    actionable_targets: list[ScreenRegion]  # regions the agent can click
    summary: str                  # human-readable summary
    confidence: float             # overall confidence
    raw_metadata: dict = field(default_factory=dict)


class ScreenshotPerceptionPlugin(Protocol):
    """Protocol for screenshot-based perception plugins."""

    game_type: str

    def infer_from_screenshot(
        self,
        screenshot_path: str,
        profile: dict | None = None,
    ) -> ScreenshotInference:
        """Infer game state from a screenshot file.

        Args:
            screenshot_path: path to the PNG screenshot
            profile: optional profile with layout zones, anchors, etc.

        Returns:
            ScreenshotInference with detected regions and actionable targets
        """
        ...
