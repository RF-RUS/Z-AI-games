"""Legal actions derived from the PERCEIVED board (9d).

When perception (VLM or heuristic CV) reports the real hand + top card, legal
moves should come from what's actually on screen — not the simulated engine,
which is keyed by game_id and blind to the real table. This is the root fix for
"the agent always plays the leftmost card": a move derived here carries the
detected card's colour+value, so the windows executor's `_find_card_center`
grounds the click to the RIGHT card instead of falling back to the first one.

Pure functions only — no orchestrator/session state — so they unit-test without
a Windows host. UNO match rule reuses the schema's `Card.matches`.
"""

from __future__ import annotations

from typing import Any

from uno_schemas.game import ActionType, Card, CardColor, CardValue, LegalAction

# Lenient value mapping — perception emits human-ish tokens; map to CardValue.
_VALUE_ALIASES = {
    "0": CardValue.ZERO, "1": CardValue.ONE, "2": CardValue.TWO, "3": CardValue.THREE,
    "4": CardValue.FOUR, "5": CardValue.FIVE, "6": CardValue.SIX, "7": CardValue.SEVEN,
    "8": CardValue.EIGHT, "9": CardValue.NINE,
    "skip": CardValue.SKIP, "reverse": CardValue.REVERSE,
    "draw_two": CardValue.DRAW_TWO, "draw2": CardValue.DRAW_TWO, "+2": CardValue.DRAW_TWO,
    "wild": CardValue.WILD,
    "wild_draw_four": CardValue.WILD_DRAW_FOUR, "wild4": CardValue.WILD_DRAW_FOUR, "+4": CardValue.WILD_DRAW_FOUR,
}


def _to_card(detected: dict[str, Any]) -> Card | None:
    """Map a detected {color,value} dict → Card, or None if unmappable.

    A card with a known colour but unreadable value (colour-only CV) can't be
    rule-checked reliably, so it's dropped here — the caller then treats the hand
    as not fully readable and prefers drawing over a blind play.
    """
    if not isinstance(detected, dict):
        return None
    color_raw = str(detected.get("color") or "").lower().strip()
    value_raw = str(detected.get("value") or "").lower().strip()
    try:
        color = CardColor(color_raw)
    except ValueError:
        return None
    value = _VALUE_ALIASES.get(value_raw)
    if value is None:
        return None
    return Card(color=color, value=value)


def legal_actions_from_perception(
    hand_cards: list[dict[str, Any]] | None,
    top_card: dict[str, Any] | None,
    player_id: str = "bot",
) -> list[LegalAction] | None:
    """Legal UNO actions from the perceived hand + top card.

    Returns None when the board isn't readable enough to decide from the screen
    (no top card, or no hand card maps to a known colour+value) — the caller then
    falls back to the simulated engine. Always includes DRAW_CARD as a legal
    option; playable cards (matching colour/value/wild) come first.
    """
    top = _to_card(top_card) if top_card else None
    if top is None or not hand_cards:
        return None

    draw = LegalAction(action_type=ActionType.DRAW_CARD, player_id=player_id, action_id="draw")
    plays: list[LegalAction] = []
    mapped_any = False
    for i, hc in enumerate(hand_cards):
        card = _to_card(hc)
        if card is None:
            continue
        mapped_any = True
        if card.matches(top):
            plays.append(LegalAction(
                action_type=ActionType.PLAY_CARD,
                player_id=player_id,
                card=card,
                action_id=f"play_{card.color.value}_{card.value.value}_{i}",
            ))
    if not mapped_any:
        return None  # colour-only / unreadable hand → let the engine decide
    return [*plays, draw]


# --- On-screen prompt handling (Play/Keep, colour picker, Continue) ---------

# Preference when the game blocks on a modal button. The agent should progress
# the game: prefer Play (use the drawn card / confirm) over Keep, dismiss info
# dialogs. Colour choice is handled separately (needs the chosen colour).
_PROMPT_PRIORITY = ("play", "yes", "continue", "ok", "confirm", "uno", "keep", "draw")


def choose_prompt(prompts: list[dict] | None, prefer_color: str | None = None) -> dict | None:
    """Pick which on-screen button to click, or None if there's nothing to act on.

    prompts come from perception (VLM) as [{label, center:{x,y}}]. When the game
    shows a modal (e.g. Play/Keep after drawing, a colour picker after a wild),
    the agent must click a button before it can continue — this decides which.
    Only returns a prompt that has a click coordinate.
    """
    usable = [p for p in (prompts or []) if isinstance(p, dict) and p.get("center")]
    if not usable:
        return None

    # Colour picker: match the button whose label names the colour we want.
    if prefer_color:
        for p in usable:
            if prefer_color.lower() in str(p.get("label", "")).lower():
                return p

    def rank(p: dict) -> int:
        label = str(p.get("label", "")).lower()
        for i, key in enumerate(_PROMPT_PRIORITY):
            if key in label:
                return i
        return len(_PROMPT_PRIORITY)

    return min(usable, key=rank)
