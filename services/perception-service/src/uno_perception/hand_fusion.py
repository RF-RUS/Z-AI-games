"""Attach per-card click geometry to a VLM-recognized hand.

WHY THIS EXISTS
---------------
The two perception paths were mutually exclusive, and each held exactly half of
what execution needs:

  * The **VLM** reads card IDENTITY well (colour + value, even on stylized 3D art)
    but emits no pixel coordinates. Asking a VLM for bounding boxes is the weakest
    thing it does.
  * The **heuristic segmentation** (`hand_segmentation.segment_hand_cards`) reads
    GEOMETRY well — per-slot bounds and centre, calibrated against real frames —
    but only colour, never the value.

`merger.build_observation` ran the heuristic only `if not vlm_has_cards`, so the
moment the VLM started working the geometry disappeared. Consequence observed on
2026-08-05: perception was perfect (7/7 cards, top card correct, confidence 0.95),
the decision was correct (play red 4 onto yellow 4), and **the mouse never moved** —
`_find_card_center` found no coordinate, so the click fell back to a UIA lookup that
cannot succeed on a canvas game. The agent reported "Delivered".

So: identity from the model, geometry from pixels. Neither alone can click a card.

THE ONE RULE
------------
**Never guess an alignment.** A card with no coordinate makes the agent stall, which
is visible and fixable. A card with the WRONG coordinate makes it play a card it did
not decide to play — silently, and the whole reason this project keeps biting itself
is perception that is confidently wrong. When in doubt, emit no geometry.
"""

from __future__ import annotations

from typing import Any

# Colour names the heuristic can actually discriminate. Anything else (wilds, black
# card backs, a washed-out slot) is treated as "no opinion" rather than a mismatch:
# `_classify_color` always returns SOME bucket, so a wild card is guaranteed to be
# assigned a colour it does not have.
_REAL_COLORS = {"red", "yellow", "green", "blue"}

# Below this, the slot's colour is a coin flip and must not be used to contradict the
# VLM. Chosen loose on purpose: the colour check exists to catch a gross misalignment
# (hand shifted by one), not to second-guess the model card by card.
_MIN_COLOR_CONF = 0.5


def _color_of(item: Any) -> str:
  if isinstance(item, dict):
    raw = item.get("color") or item.get("card_color") or ""
  else:
    raw = getattr(item, "color", "") or ""
  return str(raw).strip().lower()


def _slot_geometry(slot: Any) -> dict[str, Any] | None:
  """Normalize a segmentation slot to `{center, bounds}` in absolute screenshot px.

  Accepts the `HandCardSlot` dataclass (tuples) or a plain dict, because the caller
  should not have to care and tests should not have to import the dataclass.
  """
  if isinstance(slot, dict):
    center, bounds = slot.get("center"), slot.get("bounds")
  else:
    center, bounds = getattr(slot, "center", None), getattr(slot, "bounds", None)

  out: dict[str, Any] = {}
  if isinstance(center, dict) and "x" in center and "y" in center:
    out["center"] = {"x": int(center["x"]), "y": int(center["y"])}
  elif isinstance(center, (list, tuple)) and len(center) == 2:
    out["center"] = {"x": int(center[0]), "y": int(center[1])}

  if isinstance(bounds, dict) and {"x", "y", "width", "height"} <= set(bounds):
    out["bounds"] = {k: int(bounds[k]) for k in ("x", "y", "width", "height")}
  elif isinstance(bounds, (list, tuple)) and len(bounds) == 4:
    out["bounds"] = {
      "x": int(bounds[0]), "y": int(bounds[1]),
      "width": int(bounds[2]), "height": int(bounds[3]),
    }

  # A centre is what the executor clicks; bounds alone would let us derive one, and
  # `_card_center` in adapter_registry already does that. Either is enough.
  return out or None


def _confidence_of(slot: Any) -> float:
  raw = slot.get("color_confidence") if isinstance(slot, dict) else getattr(slot, "color_confidence", 0.0)
  try:
    return float(raw or 0.0)
  except (TypeError, ValueError):
    return 0.0


def _index_alignment_ok(cards: list[dict], slots: list[Any]) -> bool:
  """Do slot colours corroborate a straight left-to-right index alignment?

  Only slots with a confidently-read real colour vote, and only against cards whose
  colour is itself a real colour (a wild has no colour to compare). If nothing is
  comparable we accept — the count already matched, and refusing here would block
  every hand the colour classifier happens to be unsure about.
  """
  agree = disagree = 0
  for card, slot in zip(cards, slots, strict=True):
    c_color, s_color = _color_of(card), _color_of(slot)
    if c_color not in _REAL_COLORS or s_color not in _REAL_COLORS:
      continue
    if _confidence_of(slot) < _MIN_COLOR_CONF:
      continue
    if c_color == s_color:
      agree += 1
    else:
      disagree += 1
  if agree + disagree == 0:
    return True
  return agree / (agree + disagree) >= 0.6


def attach_hand_geometry(
  cards: list[dict] | None, slots: list[Any] | None
) -> tuple[list[dict], dict[str, Any]]:
  """Copy click geometry from segmentation `slots` onto recognized `cards`.

  Returns `(cards, diagnostics)`. Cards are new dicts; the input is not mutated.
  Cards that could not be aligned come back WITHOUT geometry — by design.

  `diagnostics` is meant to be stored on the observation (and therefore in the cycle
  trace), because "the agent did not click" and "the agent had no coordinate to click"
  are different bugs and must be distinguishable after the fact.
  """
  cards = [dict(c) for c in (cards or []) if isinstance(c, dict)]
  slots = list(slots or [])
  diag: dict[str, Any] = {
    "cards": len(cards),
    "slots": len(slots),
    "grounded": 0,
    "method": "none",
  }
  if not cards or not slots:
    diag["reason"] = "no cards" if not cards else "segmentation found no slots"
    return cards, diag

  # Path 1 — counts match and colours do not contradict: align by position. This is
  # the common case and the only one that can ground a wild card, whose colour the
  # heuristic cannot read at all.
  if len(cards) == len(slots) and _index_alignment_ok(cards, slots):
    for card, slot in zip(cards, slots, strict=True):
      geom = _slot_geometry(slot)
      if geom:
        card.update(geom)
        card["geometry_source"] = "hand_segmentation"
        diag["grounded"] += 1
    diag["method"] = "index"
    return cards, diag

  # Path 2 — counts differ, or the colour sequence contradicts the order. Fall back to
  # matching each card to the leftmost unused slot of the SAME colour. A card whose
  # colour is not a real colour (wild), or that finds no free slot, gets no geometry:
  # at this point we already know the two views of the hand disagree, and guessing
  # would mean clicking a card the agent did not choose.
  used: set[int] = set()
  for card in cards:
    c_color = _color_of(card)
    if c_color not in _REAL_COLORS:
      continue
    for i, slot in enumerate(slots):
      if i in used or _color_of(slot) != c_color:
        continue
      geom = _slot_geometry(slot)
      if geom:
        card.update(geom)
        card["geometry_source"] = "hand_segmentation_color_match"
        used.add(i)
        diag["grounded"] += 1
      break
  diag["method"] = "color_match"
  diag["reason"] = (
    "card/slot count mismatch" if len(cards) != len(slots) else "slot colours contradict card order"
  )
  return cards, diag
