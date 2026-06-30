"""Tests for action verification and gesture execution."""

from unittest.mock import MagicMock

from uno_adapter_web.action_verification import (
  compare_grounding,
  verify_action,
)


class TestCompareGrounding:
  def test_same_grounding_no_changes(self):
    before = MagicMock()
    before.hand = [MagicMock(color="red", number="5", slot_index=0)]
    before.draw_pile = {"bbox": {}}
    after = MagicMock()
    after.hand = [MagicMock(color="red", number="5", slot_index=0)]
    after.draw_pile = {"bbox": {}}
    ev = compare_grounding(before, after)
    assert ev.hand_count_changed is False
    assert ev.top_card_changed is False
    assert ev.draw_pile_changed is False

  def test_hand_count_changed(self):
    before = MagicMock()
    before.hand = [MagicMock(color="red", number="5", slot_index=0)]
    before.draw_pile = None
    after = MagicMock()
    after.hand = [MagicMock(color="red", number="5", slot_index=0), MagicMock(color="blue", number="3", slot_index=1)]
    after.draw_pile = None
    ev = compare_grounding(before, after)
    assert ev.hand_count_changed is True
    assert ev.before_hand_count == 1
    assert ev.after_hand_count == 2

  def test_top_card_changed(self):
    before = MagicMock()
    before.hand = [MagicMock(color="red", number="5", slot_index=0)]
    before.draw_pile = None
    after = MagicMock()
    after.hand = [MagicMock(color="blue", number="3", slot_index=0)]
    after.draw_pile = None
    ev = compare_grounding(before, after)
    assert ev.top_card_changed is True

  def test_draw_pile_appeared(self):
    before = MagicMock()
    before.hand = []
    before.draw_pile = None
    after = MagicMock()
    after.hand = []
    after.draw_pile = {"bbox": {}}
    ev = compare_grounding(before, after)
    assert ev.draw_pile_changed is True

  def test_both_none(self):
    ev = compare_grounding(None, None)
    assert ev.hand_count_changed is False


class TestVerifyAction:
  def test_delivery_failed(self):
    result = verify_action("play_card", "click", delivery_success=False)
    assert result.delivery == "failed"
    assert result.outcome == "unknown"

  def test_play_card_confirmed(self):
    before = MagicMock()
    before.hand = [MagicMock(color="red", number="5")]
    before.draw_pile = None
    after = MagicMock()
    after.hand = [MagicMock(color="blue", number="3")]
    after.draw_pile = None
    ev = compare_grounding(before, after)
    result = verify_action("play_card", "click", delivery_success=True, evidence=ev)
    assert result.outcome == "confirmed"
    assert "strong evidence" in result.rationale

  def test_play_card_top_card_changed(self):
    before = MagicMock()
    before.hand = [MagicMock(color="red", number="5")]
    before.draw_pile = None
    after = MagicMock()
    after.hand = [MagicMock(color="blue", number="7")]
    after.draw_pile = None
    ev = compare_grounding(before, after)
    result = verify_action("play_card", "click", delivery_success=True, evidence=ev)
    assert result.outcome == "confirmed"
    assert "top_card_changed" in result.rationale

  def test_play_card_no_change(self):
    before = MagicMock()
    before.hand = [MagicMock(color="red", number="5")]
    before.draw_pile = None
    after = MagicMock()
    after.hand = [MagicMock(color="red", number="5")]
    after.draw_pile = None
    ev = compare_grounding(before, after)
    result = verify_action("play_card", "click", delivery_success=True, evidence=ev)
    assert result.outcome == "unknown"

  def test_draw_card_confirmed(self):
    before = MagicMock()
    before.hand = []
    before.draw_pile = {"bbox": {}}
    after = MagicMock()
    after.hand = [MagicMock(color="red", number="5")]
    after.draw_pile = {"bbox": {}}
    ev = compare_grounding(before, after)
    result = verify_action("draw_card", "click", delivery_success=True, evidence=ev)
    assert result.outcome == "confirmed"
    assert "hand_count_changed" in result.rationale

  def test_draw_card_no_change(self):
    before = MagicMock()
    before.hand = []
    before.draw_pile = None
    after = MagicMock()
    after.hand = []
    after.draw_pile = None
    ev = compare_grounding(before, after)
    result = verify_action("draw_card", "click", delivery_success=True, evidence=ev)
    assert result.outcome == "unknown"

  def test_hover_does_not_require_state_change(self):
    before = MagicMock()
    before.hand = []
    before.draw_pile = None
    after = MagicMock()
    after.hand = []
    after.draw_pile = None
    ev = compare_grounding(before, after)
    result = verify_action("play_card", "hover", delivery_success=True, evidence=ev)
    assert result.outcome == "unknown"
    assert "hover" in result.rationale
