"""Gesture decision layer — explicit, inspectable gesture planning.

Transforms (action intent + target grounding + profile hints + evidence)
into a GesturePlan that the executor can consume.

Supported gestures: click, double_click, drag, click_then_drop, hover.
Conservative by default: unknown → click (safest browser gesture).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class GestureType(StrEnum):
  CLICK = "click"
  DOUBLE_CLICK = "double_click"
  DRAG = "drag"
  CLICK_THEN_DROP = "click_then_drop"
  HOVER = "hover"


class GestureConfidence(StrEnum):
  HIGH = "high"
  MEDIUM = "medium"
  LOW = "low"
  UNCERTAIN = "uncertain"


@dataclass
class GestureTarget:
  """A resolved point for gesture execution."""
  x: float
  y: float
  raw_x: float = 0.0
  raw_y: float = 0.0
  source: str = "unknown"
  bbox: dict[str, float] | None = None


@dataclass
class GesturePlan:
  """Explicit, inspectable gesture decision."""
  gesture_type: GestureType = GestureType.CLICK
  target: GestureTarget | None = None
  drag_from: GestureTarget | None = None
  drag_to: GestureTarget | None = None
  confidence: GestureConfidence = GestureConfidence.LOW
  rationale: str = ""
  source: str = ""
  profile_hint: str = ""


# --- Profile gesture hints ---

PROFILE_GESTURE_HINTS: dict[str, dict[str, Any]] = {
  "scuffed-uno-web": {
    "preferred_play_gesture": GestureType.CLICK,
    "preferred_draw_gesture": GestureType.CLICK,
    "draggable_cards": False,
    "requires_drop_zone": False,
    "hover_before_click": False,
    "animation_duration_ms": 300,
  },
  "pizz-uno-web": {
    "preferred_play_gesture": GestureType.CLICK,
    "preferred_draw_gesture": GestureType.CLICK,
    "draggable_cards": False,
    "requires_drop_zone": False,
    "hover_before_click": False,
    "animation_duration_ms": 200,
  },
  "real-unoh-web": {
    "preferred_play_gesture": GestureType.CLICK,
    "preferred_draw_gesture": GestureType.CLICK,
    "draggable_cards": False,
    "requires_drop_zone": False,
    "hover_before_click": False,
    "animation_duration_ms": 200,
  },
}

DEFAULT_GESTURE_HINTS = {
    "preferred_play_gesture": GestureType.CLICK,
    "preferred_draw_gesture": GestureType.CLICK,
    "draggable_cards": False,
    "requires_drop_zone": False,
    "hover_before_click": False,
    "animation_duration_ms": 300,
}


def get_profile_gesture_hints(profile_id: str) -> dict[str, Any]:
  return PROFILE_GESTURE_HINTS.get(profile_id, DEFAULT_GESTURE_HINTS)


def plan_gesture(
  action_type: str,
  profile_id: str,
  target_x: float | None = None,
  target_y: float | None = None,
  raw_x: float | None = None,
  raw_y: float | None = None,
  bbox: dict[str, float] | None = None,
  target_source: str = "unknown",
  hand_cards: list[dict] | None = None,
  card_color: str | None = None,
  card_value: str | None = None,
  available_grounding: bool = False,
) -> GesturePlan:
  """Produce an explicit gesture plan for a given action.

  This is the single entry point for gesture decision.
  Returns a GesturePlan with type, target, confidence, and rationale.
  """
  hints = get_profile_gesture_hints(profile_id)

  if action_type in ("play_card", "play"):
    gesture = hints.get("preferred_play_gesture", GestureType.CLICK)
    rationale = f"play_card: preferred gesture from profile={profile_id}"
    if target_x is not None and target_y is not None:
      target = GestureTarget(x=target_x, y=target_y, raw_x=raw_x or target_x, raw_y=raw_y or target_y, source=target_source, bbox=bbox)
      confidence = GestureConfidence.HIGH if target_source == "cv_card" else GestureConfidence.MEDIUM
    elif available_grounding and hand_cards:
      target = GestureTarget(x=0, y=0, source="no_match")
      confidence = GestureConfidence.LOW
      rationale += " (no matching card in grounding)"
    else:
      target = None
      confidence = GestureConfidence.UNCERTAIN
      rationale += " (no grounding available)"

  elif action_type == "draw_card":
    gesture = hints.get("preferred_draw_gesture", GestureType.CLICK)
    rationale = f"draw_card: preferred gesture from profile={profile_id}"
    if target_x is not None and target_y is not None:
      target = GestureTarget(x=target_x, y=target_y, raw_x=raw_x or target_x, raw_y=raw_y or target_y, source=target_source, bbox=bbox)
      confidence = GestureConfidence.HIGH if target_source == "cv_draw" else GestureConfidence.MEDIUM
    else:
      target = None
      confidence = GestureConfidence.LOW
      rationale += " (no draw pile target)"

  elif action_type in ("click",):
    gesture = GestureType.CLICK
    target = GestureTarget(x=target_x or 0, y=target_y or 0, source="dom_selector")
    confidence = GestureConfidence.HIGH
    rationale = "DOM click action"

  else:
    gesture = GestureType.CLICK
    target = GestureTarget(x=target_x or 0, y=target_y or 0, source="default") if target_x is not None else None
    confidence = GestureConfidence.LOW
    rationale = f"unknown action_type={action_type}, defaulting to click"

  return GesturePlan(
    gesture_type=gesture,
    target=target,
    confidence=confidence,
    rationale=rationale,
    source=f"profile={profile_id}",
    profile_hint=str(hints),
  )
