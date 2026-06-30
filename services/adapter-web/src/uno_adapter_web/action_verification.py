"""Post-action verification — action-aware evidence comparison.

Compares before/after evidence to determine whether an action had a real effect.
Produces honest verdicts: confirmed / likely_confirmed / unknown / failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VerificationEvidence:
  """Collected evidence before and after an action."""
  before_state: str = "unknown"
  after_state: str = "unknown"
  before_hand_count: int = 0
  after_hand_count: int = 0
  before_top_card: dict | None = None
  after_top_card: dict | None = None
  before_draw_pile: bool = False
  after_draw_pile: bool = False
  before_confidence: float = 0.0
  after_confidence: float = 0.0
  hand_count_changed: bool = False
  top_card_changed: bool = False
  state_changed: bool = False
  confidence_changed: bool = False
  draw_pile_changed: bool = False
  before_hand_colors: list[str] = field(default_factory=list)
  after_hand_colors: list[str] = field(default_factory=list)
  before_region_count: int = 0
  after_region_count: int = 0


@dataclass
class VerificationResult:
  """Final verification verdict."""
  delivery: str = "unknown"
  outcome: str = "unknown"
  rationale: str = ""
  evidence: VerificationEvidence = field(default_factory=VerificationEvidence)
  gesture_type: str = ""
  action_type: str = ""


def compare_grounding(before: Any, after: Any) -> VerificationEvidence:
  """Compare before/after ActionGrounding to detect changes."""
  ev = VerificationEvidence()

  if before:
    ev.before_hand_count = len(before.hand) if before.hand else 0
    ev.before_draw_pile = before.draw_pile is not None
    ev.before_hand_colors = [c.color for c in before.hand] if before.hand else []
    if before.hand:
      first = before.hand[0]
      ev.before_top_card = {"color": first.color, "number": first.number}
    ev.before_region_count = len(before.hand) + (1 if before.draw_pile else 0)

  if after:
    ev.after_hand_count = len(after.hand) if after.hand else 0
    ev.after_draw_pile = after.draw_pile is not None
    ev.after_hand_colors = [c.color for c in after.hand] if after.hand else []
    if after.hand:
      first = after.hand[0]
      ev.after_top_card = {"color": first.color, "number": first.number}
    ev.after_region_count = len(after.hand) + (1 if after.draw_pile else 0)

  ev.hand_count_changed = ev.before_hand_count != ev.after_hand_count
  ev.top_card_changed = (ev.before_top_card != ev.after_top_card) and (ev.before_top_card is not None or ev.after_top_card is not None)
  ev.draw_pile_changed = ev.before_draw_pile != ev.after_draw_pile

  return ev


def evidence_summary(ev: VerificationEvidence) -> str:
  """Produce a human-readable evidence summary for validation reports."""
  parts = []
  parts.append(f"hand: {ev.before_hand_count}->{ev.after_hand_count} (changed={ev.hand_count_changed})")
  parts.append(f"top_card: {ev.before_top_card}->{ev.after_top_card} (changed={ev.top_card_changed})")
  parts.append(f"draw_pile: {ev.before_draw_pile}->{ev.after_draw_pile} (changed={ev.draw_pile_changed})")
  parts.append(f"colors_before={ev.before_hand_colors} colors_after={ev.after_hand_colors}")
  parts.append(f"regions_before={ev.before_region_count} regions_after={ev.after_region_count}")
  if ev.before_confidence > 0 or ev.after_confidence > 0:
    parts.append(f"confidence: {ev.before_confidence:.2f}->{ev.after_confidence:.2f}")
  return "; ".join(parts)


def verify_action(
  action_type: str,
  gesture_type: str,
  delivery_success: bool,
  before_state: str = "unknown",
  after_state: str = "unknown",
  evidence: VerificationEvidence | None = None,
  before_confidence: float = 0.0,
  after_confidence: float = 0.0,
) -> VerificationResult:
  """Produce a verification verdict for an executed action.

  Verdicts:
  - confirmed: strong evidence of effect
  - likely_confirmed: moderate evidence, probable effect
  - unknown: insufficient evidence
  - failed: delivery failed
  - contradicted: evidence shows negative outcome
  """
  if not delivery_success:
    return VerificationResult(
      delivery="failed", outcome="unknown",
      rationale="delivery failed",
      evidence=evidence or VerificationEvidence(), gesture_type=gesture_type, action_type=action_type,
    )

  ev = evidence or VerificationEvidence()
  ev.before_confidence = before_confidence
  ev.after_confidence = after_confidence
  ev.state_changed = before_state != after_state and before_state != "unknown" and after_state != "unknown"

  signals = []
  if ev.hand_count_changed:
    signals.append("hand_count_changed")
  if ev.top_card_changed:
    signals.append("top_card_changed")
  if ev.state_changed:
    signals.append("state_changed")
  if ev.draw_pile_changed:
    signals.append("draw_pile_changed")
  if after_confidence > before_confidence + 0.05:
    signals.append("confidence_improved")

  ev_summary = evidence_summary(ev)

  if gesture_type in ("click", "double_click", "drag", "click_then_drop") and action_type in ("play_card", "play"):
    if ev.hand_count_changed or ev.top_card_changed:
      return VerificationResult(
        delivery="delivered", outcome="confirmed",
        rationale=f"strong evidence: {', '.join(signals)} | {ev_summary}",
        evidence=ev, gesture_type=gesture_type, action_type=action_type,
      )
    if ev.state_changed:
      return VerificationResult(
        delivery="delivered", outcome="likely_confirmed",
        rationale=f"state changed but no hand/card evidence: {', '.join(signals)} | {ev_summary}",
        evidence=ev, gesture_type=gesture_type, action_type=action_type,
      )
    if signals:
      return VerificationResult(
        delivery="delivered", outcome="likely_confirmed",
        rationale=f"weak signals: {', '.join(signals)} | {ev_summary}",
        evidence=ev, gesture_type=gesture_type, action_type=action_type,
      )
    return VerificationResult(
      delivery="delivered", outcome="unknown",
      rationale=f"no observable change | {ev_summary}",
      evidence=ev, gesture_type=gesture_type, action_type=action_type,
    )

  if action_type == "draw_card":
    if ev.hand_count_changed or ev.draw_pile_changed:
      return VerificationResult(
        delivery="delivered", outcome="confirmed",
        rationale=f"draw evidence: {', '.join(signals)} | {ev_summary}",
        evidence=ev, gesture_type=gesture_type, action_type=action_type,
      )
    if ev.top_card_changed:
      return VerificationResult(
        delivery="delivered", outcome="likely_confirmed",
        rationale=f"hand card identity changed: {', '.join(signals)} | {ev_summary}",
        evidence=ev, gesture_type=gesture_type, action_type=action_type,
      )
    if ev.state_changed:
      return VerificationResult(
        delivery="delivered", outcome="likely_confirmed",
        rationale=f"state changed: {', '.join(signals)} | {ev_summary}",
        evidence=ev, gesture_type=gesture_type, action_type=action_type,
      )
    return VerificationResult(
      delivery="delivered", outcome="unknown",
      rationale=f"no observable draw effect | {ev_summary}",
      evidence=ev, gesture_type=gesture_type, action_type=action_type,
    )

  if gesture_type == "hover":
    return VerificationResult(
      delivery="delivered", outcome="unknown",
      rationale=f"hover does not require state change | {ev_summary}",
      evidence=ev, gesture_type=gesture_type, action_type=action_type,
    )

  return VerificationResult(
    delivery="delivered", outcome="unknown",
    rationale=f"no verification rules for action={action_type} gesture={gesture_type} | {ev_summary}",
    evidence=ev, gesture_type=gesture_type, action_type=action_type,
  )
