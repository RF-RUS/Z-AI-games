"""UNO-specific perception adapter — first game plugin implementation.

Extracts UNO game state from raw adapter evidence. This is the UNO-specific
logic that was previously embedded in the perception merger.
"""

from __future__ import annotations

from typing import Any

COLOR_MAP = {
    "red": "red", "blue": "blue", "green": "green",
    "yellow": "yellow", "wild": "wild",
}

VALUE_MAP = {
    "0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
    "5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
    "skip": "skip", "reverse": "reverse", "draw two": "draw_two",
    "draw_two": "draw_two", "wild": "wild",
}


def parse_card_from_text(text: str) -> dict[str, str] | None:
    """Parse a card description from text into {color, value} dict."""
    t = text.strip().lower()
    color = None
    for c in COLOR_MAP:
        if c in t:
            color = c
            break
    value = None
    for k, v in VALUE_MAP.items():
        if k in t:
            value = v
            break
    if color and value:
        return {"color": color, "value": value}
    return None


class UnuPerceptionAdapter:
    """UNO game perception adapter.

    Implements the GamePerceptionAdapter protocol for UNO-specific
    evidence parsing and state extraction.
    """

    game_type = "uno"

    def parse_dom(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        top = snapshot.get("top_card")
        hand_cards = snapshot.get("hand_cards")
        action_grounding = snapshot.get("action_grounding")

        # Return partial state even when top_card/hand_cards are missing
        # This allows the pipeline to continue with whatever data is available
        has_any = top or hand_cards or action_grounding or snapshot.get("discard_pile_count") is not None

        result = {
            "top_card": top or ({"color": hand_cards[0].get("color", "unknown"), "value": hand_cards[0].get("number", "unknown")} if hand_cards else None),
            "draw_pile_count": snapshot.get("draw_pile_count", 0),
            "discard_pile_count": snapshot.get("discard_pile_count", 1),
            "current_player_id": snapshot.get("current_player_id", "unknown"),
            "direction": snapshot.get("direction", 1),
            "pending_draw": snapshot.get("pending_draw", 0),
        }

        if hand_cards:
            result["hand_cards"] = hand_cards
        if action_grounding:
            result["action_grounding"] = action_grounding

        return result if has_any else None

    def parse_ui(self, element_tree: dict[str, Any]) -> dict[str, Any] | None:
        extracted = element_tree.get("extracted", element_tree)
        if not isinstance(extracted, dict):
            return None
        top = extracted.get("top_card")
        if not top:
            return None
        return {
            "top_card": top,
            "draw_pile_count": extracted.get("draw_pile_count", 0),
            "discard_pile_count": extracted.get("discard_pile_count", 1),
            "current_player_id": extracted.get("current_player_id", "unknown"),
            "direction": extracted.get("direction", 1),
            "pending_draw": extracted.get("pending_draw", 0),
        }

    def parse_ocr(self, text_blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
        for block in text_blocks:
            text = block.get("text", "")
            card = parse_card_from_text(text)
            if card:
                return {
                    "top_card": card,
                    "draw_pile_count": 0,
                    "discard_pile_count": 1,
                    "current_player_id": "unknown",
                    "direction": 1,
                }
        return None

    def parse_vlm(self, structured: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if "top_card" in structured:
            result["top_card"] = structured["top_card"]
            result["draw_pile_count"] = structured.get("draw_pile_count", 0)
            result["discard_pile_count"] = 1
            result["current_player_id"] = structured.get("current_player_id", "unknown")
            result["direction"] = 1
        return result

    def extract_elements(self, game_state: dict[str, Any]) -> list[dict[str, Any]]:
        return game_state.get("hand_cards", [])

    def check_discrepancy(
        self, state_a: dict[str, Any], state_b: dict[str, Any]
    ) -> dict[str, Any] | None:
        card_a = state_a.get("top_card")
        card_b = state_b.get("top_card")
        if card_a and card_b and card_a != card_b:
            return {
                "field": "top_card",
                "expected": card_a,
                "observed": card_b,
                "severity": "error",
            }
        return None
