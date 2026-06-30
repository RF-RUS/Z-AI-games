"""Temporal consistency for detection results.

Stabilizes detection across frames by comparing consecutive detections
and filtering out noise/flicker.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from uno_adapter_web.hand_detection import ActionGrounding, DetectedCard


@dataclass
class TemporalState:
    """Tracks detection state across frames."""
    prev_grounding: ActionGrounding | None = None
    prev_cards_snapshot: list[tuple[str, str, int]] = field(default_factory=list)
    stable_cards: list[DetectedCard] = field(default_factory=list)
    frame_count: int = 0


def _cards_signature(cards: list[DetectedCard]) -> list[tuple[str, str, int]]:
    """Create a stable signature from detected cards for comparison."""
    return sorted([(c.color, c.number or "", c.slot_index) for c in cards])


def stabilize_detection(
    current: ActionGrounding,
    state: TemporalState,
    confidence_threshold: float = 0.3,
) -> ActionGrounding:
    """Compare current detection with previous and return stabilized result.

    If current detection has low confidence and previous had better results,
    prefer the previous detection (reduces flicker).

    Returns the best available grounding.
    """
    state.frame_count += 1
    current_sig = _cards_signature(current.hand) if current.hand else []

    if current.detection_confidence >= confidence_threshold:
        state.prev_grounding = current
        state.prev_cards_snapshot = current_sig
        state.stable_cards = current.hand
        return current

    if state.prev_grounding and state.prev_grounding.hand:
        prev_sig = state.prev_cards_snapshot
        if current_sig == prev_sig:
            return state.prev_grounding
        if len(current.hand) != len(state.prev_grounding.hand):
            state.prev_grounding = current
            state.prev_cards_snapshot = current_sig
            state.stable_cards = current.hand
            return current
        return state.prev_grounding

    state.prev_grounding = current
    state.prev_cards_snapshot = current_sig
    state.stable_cards = current.hand
    return current
