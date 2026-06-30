"""Game-specific perception adapter protocol.

Each game plugin implements this protocol to handle game-specific
evidence parsing. The perception merger calls the registered adapter
instead of containing game-specific logic itself.
"""

from __future__ import annotations

from typing import Any, Protocol


class GamePerceptionAdapter(Protocol):
    """Protocol for game-specific perception adapters.

    The merger calls parse_dom(), parse_ui(), parse_ocr(), parse_vlm()
    to extract game-specific state from raw evidence. Each game (UNO,
    Svintus, etc.) implements these methods for its own state model.
    """

    game_type: str

    def parse_dom(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        """Parse DOM evidence snapshot into game state dict.
        Returns None if no game state can be extracted.
        """
        ...

    def parse_ui(self, element_tree: dict[str, Any]) -> dict[str, Any] | None:
        """Parse UI automation evidence into game state dict.
        Returns None if no game state can be extracted.
        """
        ...

    def parse_ocr(self, text_blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Parse OCR text blocks into game state dict.
        Returns None if no game state can be extracted.
        """
        ...

    def parse_vlm(self, structured: dict[str, Any]) -> dict[str, Any]:
        """Parse VLM structured output into game state dict.
        Always returns a dict (may be empty).
        """
        ...

    def extract_elements(self, game_state: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract game elements (e.g., hand cards) from game state.
        Returns list of opaque game element dicts.
        """
        ...

    def check_discrepancy(
        self, state_a: dict[str, Any], state_b: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Check for discrepancies between two game state dicts.
        Returns discrepancy info dict or None if consistent.
        """
        ...
