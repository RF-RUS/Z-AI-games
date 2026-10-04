"""Wild-card colour choice — the ONE strategy for "which colour to set".

Two execution paths need the identical verdict, so the rule lives here (shared
by session-orchestrator and decision-service) instead of being duplicated:

* Orchestrator prompt branch — the desktop game shows a colour PICKER as
  perceived prompt buttons ("Red"/"Yellow"/"Green"/"Blue" with coordinates);
  ``choose_prompt_with_strategy`` asks ``decide_wild_color`` which one to click.
* Decision-service heuristic — when legal actions come from the simulated
  engine, a wild play is expanded into one action PER colour
  (``LegalAction(chosen_color=...)``); ``_score_action`` ranks those variants
  with ``score_wild_color``.

The rule (standard UNO tempo play):
  1. Prefer the colour you hold the MOST non-wild cards of — after setting it
     you can keep playing that colour on your next turn instead of drawing.
  2. Tie (or an empty/unreadable hand) → continue the current sequence: the
     top card's colour. Predictable for you, legal for everyone.
  3. Still nothing (top unreadable too) → deterministic red fallback, so the
     agent never stalls and replaying a trace gives the same click.

Counts ignore wild cards: they play on any colour, so they carry no colour
preference. Unknown/missing colours are skipped, never counted as a fifth.
"""

from __future__ import annotations

from typing import Any

WILD_COLOR_ORDER = ("red", "yellow", "green", "blue")

# How much one extra same-colour card in hand is worth. A one-card lead in the
# hand must beat the top-match bonus (0.05) — that is what keeps rule 1 above
# rule 2. Capped at 3 cards: a 4th green is no more useful than a 3rd.
_PER_CARD_BONUS = 0.1
_MAX_COUNTED_CARDS = 3
# Top-match bonus, applied on top of the count score.
_TOP_MATCH_BONUS = 0.05


def color_counts(hand_cards: list[Any] | None) -> dict[str, int]:
  """Count NON-wild cards in `hand_cards` by colour.

  Entries are the perception dicts ({"color": ..., "value": ...}); anything
  that is not a dict with a known colour is ignored (wilds, unreadable, junk).
  Returns all four colours, so ``.get`` is never needed by callers.
  """
  counts = {c: 0 for c in WILD_COLOR_ORDER}
  for hc in hand_cards or []:
    if not isinstance(hc, dict):
      continue
    color = str(hc.get("color") or "").lower().strip()
    if color in counts:
      counts[color] += 1
  return counts


def score_wild_color(color: str, counts: dict[str, int], top_color: str | None) -> float:
  """Strategy score for setting `color` — higher is better.

  ``0.1 * min(count, 3)`` + ``0.05`` when `color` continues the top sequence.
  A one-card hand lead (0.1) always outranks the top-match bonus (0.05), which
  is exactly the rule-1-beats-rule-2 ordering the docstring promises.
  """
  if color not in WILD_COLOR_ORDER:
    return 0.0
  score = _PER_CARD_BONUS * min(counts.get(color, 0), _MAX_COUNTED_CARDS)
  if top_color and color == top_color:
    score += _TOP_MATCH_BONUS
  return score


def choose_wild_color(
  hand_cards: list[Any] | None, top_color: str | None = None
) -> tuple[str, str]:
  """Which colour to set when playing a wild, plus a human-readable WHY.

  Deterministic: ties resolve by WILD_COLOR_ORDER (red first), so identical
  inputs always produce the same click — traces stay reproducible.
  """
  counts = color_counts(hand_cards)
  best_color = WILD_COLOR_ORDER[0]
  best_score = -1.0
  for color in WILD_COLOR_ORDER:
    score = score_wild_color(color, counts, top_color)
    if score > best_score:
      best_color, best_score = color, score

  n = counts.get(best_color, 0)
  if n:
    reason = (
      f"hand holds {n} {best_color} (most of any colour) — "
      "setting it keeps your next turn playable"
    )
  elif top_color:
    reason = (
      f"no colour concentration in hand — continue the {top_color} sequence"
    )
  else:
    reason = "hand and top unreadable — deterministic red fallback"
  return best_color, reason
