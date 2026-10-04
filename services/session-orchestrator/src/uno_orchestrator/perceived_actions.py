"""Legal actions derived from the PERCEIVED board (9d).

When perception (VLM or heuristic CV) reports the real hand + top card, legal
moves should come from what's actually on screen — not the simulated engine,
which is keyed by game_id and blind to the real table. This is the root fix for
"the agent always plays the leftmost card": a move derived here carries the
detected card's colour+value, so the windows executor's `_find_card_center`
grounds the click to the RIGHT card instead of falling back to the first one.

Two readabilities, two decision sources:

* Values readable (VLM) → legal moves from colour+value rules; None → engine.
* Colours only (heuristic CV, VLM dead) → legal moves from COLOUR matches
  against the perceived top card. This keeps the decision in lockstep with what
  is actually on screen: the chosen action names a card that exists in the
  perceived hand, so the windows adapter can ground the click to its detected
  coordinate (`_find_card_center`). Deferring to the simulated engine here is
  what produced "decision demands blue skip, but the real hand has no blue" →
  grounding refuses → UIA cascade → stall (session de3856d6, cycles 2–3).

Pure functions only — no orchestrator/session state — so they unit-test without
a Windows host. UNO match rule reuses the schema's `Card.matches`.
"""

from __future__ import annotations

from typing import Any

from uno_schemas.game import ActionType, Card, CardColor, CardValue, LegalAction
from uno_shared.wild_color import WILD_COLOR_ORDER, choose_wild_color

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

# A colour-only detection (VLM down, heuristic CV) carries no value. We tag it
# CardValue.UNKNOWN: in real UNO any same-colour card is legal on top, so when the
# value is unreadable colour alone decides — the tag only marks provenance. The
# schema exposes it, traces show it, and `_find_card_center` matches on it to find
# the detected card's coordinate. `_to_card` deliberately does NOT alias it, so an
# unknown-valued card is still unreadable for exact rule checks.
_VALUE_UNREADABLE = CardValue.UNKNOWN


def _to_card(detected: dict[str, Any]) -> Card | None:
    """Map a detected {color,value} dict → Card, or None if unmappable.

    A card with a known colour but unreadable value (colour-only CV) can't be
    exact-rule-checked, so it's dropped here. The caller sees "no readable card"
    and switches to the colour-match path (`_color_only_legal_actions`) rather
    than deferring to the desynced simulated engine.
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


def _color_of(detected: dict[str, Any]) -> CardColor | None:
    """Parsed colour of a detection, or None when the token isn't a known colour."""
    if not isinstance(detected, dict):
        return None
    try:
        return CardColor(str(detected.get("color") or "").lower().strip())
    except ValueError:
        return None


def legal_actions_from_perception(
    hand_cards: list[dict[str, Any]] | None,
    top_card: dict[str, Any] | None,
    player_id: str = "bot",
) -> list[LegalAction] | None:
    """Legal UNO actions from the perceived hand + top card.

    Values readable (VLM): exact rules decide, via colour+value. When NO value
    is readable (heuristic CV with the VLM down) but colours are: colour-match
    decisions keep the agent in lockstep with the real hand — see
    `_color_only_legal_actions`. As soon as the board is readable (top + at least
    one coloured card), the result is NEVER None: "nothing playable" resolves to
    [DRAW], not to the simulated engine, whose hand is desynced from the screen.
    None remains only for an unreadable board (no top card / no colours).
    DRAW_CARD is always present alongside whatever plays are found.
    """
    top = _to_card(top_card) if top_card else None
    if top is None or not hand_cards:
        return None

    draw = LegalAction(action_type=ActionType.DRAW_CARD, player_id=player_id, action_id="draw")
    plays: list[LegalAction] = []
    # A readable card AND a colour-only card may both match the top; a readable
    # card whose value is exact-matchable is the stronger signal, but a colour-only
    # card of the same colour is a distinct physical card and must not be shadowed.
    seen_exact: set[tuple[str, str]] = set()
    seen_color: set[str] = set()
    any_readable = False
    any_color = False
    for i, hc in enumerate(hand_cards):
        card = _to_card(hc)
        if card is not None:
            any_readable = True
            if card.matches(top):
                key = (card.color.value, card.value.value)
                if key in seen_exact:
                    continue
                seen_exact.add(key)
                plays.append(LegalAction(
                    action_type=ActionType.PLAY_CARD,
                    player_id=player_id,
                    card=card,
                    action_id=f"play_{card.color.value}_{card.value.value}_{i}",
                ))
            continue
        # Unreadable value: colour is the only signal (colour-only CV / a card the
        # small VLM collapsed away and we recovered from segmentation). Same colour
        # as top is legal; anything else is not. One representative per colour.
        color = _color_of(hc)
        if color is None:
            continue
        any_color = True
        if color == top.color and color not in seen_color:
            seen_color.add(color)
            plays.append(LegalAction(
                action_type=ActionType.PLAY_CARD,
                player_id=player_id,
                card=Card(color=color, value=_VALUE_UNREADABLE),
                action_id=f"play_{color.value}_unknown_{i}",
            ))
    # Nothing playable. If the board is at all readable (a value OR a colour) the
    # honest answer is [DRAW], never None — None hands the decision to the simulated
    # engine, whose hand is desynced from the screen. None remains only for a board
    # with no readable card and no parseable colour at all.
    if not any_readable and not any_color:
        return None
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


# Label keywords for the two sides of the post-draw dilemma. Matched on the
# lowercased visible button text (exact label first, then substring) so "Play
# card" / "Keep in hand" variants still resolve. Deliberately no bare "no"/"ok":
# those are too ambiguous outside this specific two-button dialog.
_PLAY_LABEL_KEYS = ("play", "take", "use", "сыгра", "да")
_KEEP_LABEL_KEYS = ("keep", "hold", "pass", "leave", "остав")

# A wild colour picker is the ONLY UNO dialog with several colour buttons on
# screen at once, so two-or-more colour labels is a reliable picker signature.
_COLOR_BUTTON_LABELS = frozenset(WILD_COLOR_ORDER)


def _find_color_button(prompts: list[dict], color: str) -> dict | None:
    """The perceived button whose label names `color`, else None."""
    labeled = [(p, str(p.get("label", "")).strip().lower()) for p in prompts]
    for p, label in labeled:
        if label == color:
            return p
    for p, label in labeled:
        if color in label:
            return p
    return None


def _find_prompt_button(prompts: list[dict], keys: tuple[str, ...]) -> dict | None:
    """The first perceived button whose label names one of `keys`, else None."""
    labeled = [(p, str(p.get("label", "")).strip().lower()) for p in prompts]
    for p, label in labeled:
        if label in keys:
            return p
    for p, label in labeled:
        if any(k in label for k in keys):
            return p
    return None


def decide_drawn_play_or_keep(
    drawn_card: dict[str, Any] | None,
    top_card: dict[str, Any] | None = None,
    hand_cards: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Game-strategy verdict for the "Play this card, or Keep it?" prompt.

    This is the decision the AI must make the moment the game shows a freshly
    drawn card with a Play/Keep choice: analyse what is required (the drawn
    card, the top card, the rest of the hand) and say which way to go — it does
    NOT blindly click "Play" as the old static priority did.

    Rules (UNO):
    * Unreadable drawn card → keep. Playing blind risks dumping a wild the
      player still needs; keeping costs one card and keeps the turn honest.
    * Doesn't match the top (colour/value/wild rule, same `Card.matches` as
      legal actions) → keep. A non-matching card cannot be played anyway.
    * Wild / +4: keep when the hand ALREADY has a playable card (a wild is the
      rarest resource — spend it last); play when nothing else is playable,
      otherwise the player is forced to keep every turn and lose slowly.
    * Action card (+2 / skip / reverse) → play: it matches AND pressures the
      opponent, never changes the colour sequence.
    * Plain number matching the top → play: it is a legal, tempo-neutral move.
    """
    drawn = _to_card(drawn_card) if drawn_card else None
    top = _to_card(top_card) if top_card else None

    if drawn is None:
        return "keep", "drawn card unreadable — keep it (playing a blind card may burn a wild)"

    if top is not None and not drawn.matches(top):
        return (
            "keep",
            f"{drawn.color.value} {drawn.value.value} does not match top "
            f"{top.color.value} {top.value.value}",
        )

    if drawn.value in (CardValue.WILD, CardValue.WILD_DRAW_FOUR):
        others = [c for c in (_to_card(h) for h in (hand_cards or [])) if c is not None]
        if top is not None and any(c.matches(top) for c in others):
            keeper = next(c for c in others if c.matches(top))
            return (
                "keep",
                f"hoard {drawn.value.value}: hand already has a playable "
                f"{keeper.color.value} {keeper.value.value}",
            )
        return "play", f"nothing else is playable — spend the {drawn.value.value} now"

    if top is None:
        return "keep", "top card unreadable — keep until the board is readable"

    if drawn.value in (CardValue.DRAW_TWO, CardValue.SKIP, CardValue.REVERSE):
        return "play", f"{drawn.value.value} is an action card: legal and pressures the opponent"

    return "play", f"matches top {top.color.value} {top.value.value}"


def choose_prompt_with_strategy(
    prompts: list[dict] | None,
    top_card: dict[str, Any] | None = None,
    hand_cards: list[dict[str, Any]] | None = None,
    drawn_card: dict[str, Any] | None = None,
) -> tuple[dict | None, str]:
    """Which perceived prompt button to click, decided by game strategy.

    Returns (button, reason). Three regimes:

    * The wild colour picker — SEVERAL colour buttons are visible at once
      ("Red"/"Yellow"/"Green"/"Blue"). The verdict comes from `choose_wild_color`
      (shared strategy: most-held colour in hand, else continue the top's
      colour) instead of the static label preference that used to always pick
      whatever ranked first — "pick a winning colour", not the first colour.
    * The classic dilemma — BOTH a play-side and a keep-side button are visible
      (the post-draw "Play or Keep this card?" dialog): the verdict comes from
      `decide_drawn_play_or_keep`, analysing the perceived drawn card, top card
      and hand instead of a fixed "Play wins" priority.
    * Anything else (info dialogs, a lone colour button, Continue): unchanged
      `choose_prompt` behaviour — progress the game by the static preference.

    When the strategy's preferred button was not perceived (VLM missed its
    label), the other recognised side — or the only available button — is
    clicked instead: on a blocking modal, doing SOMETHING advances the game,
    while refusing to click stalls the session on a cached identical frame.
    """
    usable = [p for p in (prompts or []) if isinstance(p, dict) and p.get("center")]
    if not usable:
        return None, ""

    play_btn = _find_prompt_button(usable, _PLAY_LABEL_KEYS)
    keep_btn = _find_prompt_button(usable, _KEEP_LABEL_KEYS)
    # The dilemma beats the picker: a post-draw Play/Keep screen is never a
    # wild colour chooser, so check it first even if stray colour labels show.
    if play_btn and keep_btn:
        action, reason = decide_drawn_play_or_keep(drawn_card, top_card, hand_cards)
        preferred = play_btn if action == "play" else keep_btn
        chosen = preferred
        if chosen is None:
            # Preferred side absent from perception — fall back so the game
            # proceeds.
            if len(usable) == 1:
                chosen = usable[0]
            else:
                chosen = keep_btn if action == "play" else play_btn
            reason += " (preferred button not perceived — clicked best available)"
        return chosen, reason

    # Wild colour picker: two or more colour buttons on screen is the picker's
    # signature (no other UNO dialog has several colours). Strategy decides.
    color_buttons = [
        p for p in usable
        if str(p.get("label", "")).strip().lower() in _COLOR_BUTTON_LABELS
    ]
    if len(color_buttons) >= 2:
        top_color = None
        if top_card:
            tc = str(top_card.get("color") or "").lower().strip()
            if tc in _COLOR_BUTTON_LABELS:
                top_color = tc
        color, reason = choose_wild_color(hand_cards, top_color)
        button = _find_color_button(color_buttons, color)
        if button is None:
            # Strategy's colour not perceived — click the first available
            # colour: the game blocks until one is chosen.
            button = color_buttons[0]
            reason += " (preferred colour not perceived — clicked first available)"
        return button, reason

    # Anything else (info dialogs, a lone colour button, Continue): progress by
    # the static preference. (At this point play_btn/keep_btn cannot BOTH be
    # set — the dilemma already returned above — so this is a plain choice.)
    legacy = choose_prompt(usable)
    return (legacy, "") if legacy else (None, "")
