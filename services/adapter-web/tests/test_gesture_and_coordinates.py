"""Tests for gesture planning and coordinate reliability."""


from uno_adapter_web.coordinate_reliability import (
  convert_cv_to_css,
  coordinate_to_dict,
  validate_click_target,
)
from uno_adapter_web.gesture_planner import (
  GestureConfidence,
  GestureType,
  get_profile_gesture_hints,
  plan_gesture,
)

# --- Gesture Planner Tests ---

class TestGesturePlanning:
  def test_play_card_with_cv_target(self):
    plan = plan_gesture("play_card", "scuffed-uno-web", target_x=500, target_y=660,
                         raw_x=500, raw_y=660, target_source="cv_card")
    assert plan.gesture_type == GestureType.CLICK
    assert plan.target is not None
    assert plan.target.x == 500
    assert plan.confidence == GestureConfidence.HIGH

  def test_play_card_no_grounding(self):
    plan = plan_gesture("play_card", "scuffed-uno-web", available_grounding=False)
    assert plan.gesture_type == GestureType.CLICK
    assert plan.confidence == GestureConfidence.UNCERTAIN

  def test_draw_card_with_target(self):
    plan = plan_gesture("draw_card", "pizz-uno-web", target_x=640, target_y=336,
                         target_source="cv_draw")
    assert plan.gesture_type == GestureType.CLICK
    assert plan.target.x == 640
    assert plan.confidence == GestureConfidence.HIGH

  def test_draw_card_no_target(self):
    plan = plan_gesture("draw_card", "pizz-uno-web")
    assert plan.gesture_type == GestureType.CLICK
    assert plan.confidence == GestureConfidence.LOW

  def test_unknown_action_defaults_click(self):
    plan = plan_gesture("some_unknown_action", "scuffed-uno-web")
    assert plan.gesture_type == GestureType.CLICK
    assert plan.confidence == GestureConfidence.LOW

  def test_profile_hints_loaded(self):
    hints = get_profile_gesture_hints("scuffed-uno-web")
    assert hints["preferred_play_gesture"] == GestureType.CLICK
    assert hints["draggable_cards"] is False
    assert hints["animation_duration_ms"] == 300

  def test_profile_hints_fallback(self):
    hints = get_profile_gesture_hints("nonexistent-profile")
    assert hints["preferred_play_gesture"] == GestureType.CLICK

  def test_plan_has_rationale(self):
    plan = plan_gesture("play_card", "scuffed-uno-web", target_x=100, target_y=200,
                         target_source="cv_card")
    assert plan.rationale != ""
    assert "play_card" in plan.rationale


# --- Coordinate Reliability Tests ---

class TestCoordinateConversion:
  def test_dpr_1_no_change(self):
    conv = convert_cv_to_css(500, 600, dpr=1.0)
    assert conv.css_x == 500
    assert conv.css_y == 600
    assert conv.valid is True

  def test_dpr_2_halves(self):
    conv = convert_cv_to_css(1000, 1200, dpr=2.0)
    assert conv.css_x == 500
    assert conv.css_y == 600
    assert conv.valid is True

  def test_negative_coordinates_invalid(self):
    conv = convert_cv_to_css(-10, 20)
    assert conv.valid is False
    assert "negative" in conv.reason

  def test_out_of_viewport_invalid(self):
    conv = convert_cv_to_css(2000, 2000, dpr=1.0, viewport_width=1280, viewport_height=800)
    assert conv.valid is False
    assert "viewport" in conv.reason

  def test_in_canvas_bounds(self):
    bbox = {"x": 100, "y": 100, "width": 400, "height": 300}
    conv = convert_cv_to_css(300, 250, dpr=1.0, canvas_bbox=bbox)
    assert conv.in_canvas_bounds is True
    assert conv.valid is True

  def test_outside_canvas_not_invalid(self):
    bbox = {"x": 100, "y": 100, "width": 400, "height": 300}
    conv = convert_cv_to_css(600, 250, dpr=1.0, canvas_bbox=bbox)
    assert conv.in_canvas_bounds is False
    assert conv.valid is True  # still valid for clicks outside canvas

  def test_coordinate_to_dict(self):
    conv = convert_cv_to_css(500, 600, dpr=1.0)
    d = coordinate_to_dict(conv)
    assert d["raw"] == {"x": 500, "y": 600}
    assert d["css"] == {"x": 500.0, "y": 600.0}
    assert d["dpr"] == 1.0
    assert d["valid"] is True


class TestValidateClickTarget:
  def test_valid_target(self):
    ok, reason = validate_click_target(500, 600)
    assert ok is True

  def test_negative_invalid(self):
    ok, reason = validate_click_target(-10, 600)
    assert ok is False

  def test_out_of_viewport_invalid(self):
    ok, reason = validate_click_target(2000, 600)
    assert ok is False

  def test_inside_canvas_valid(self):
    bbox = {"x": 100, "y": 100, "width": 400, "height": 300}
    ok, reason = validate_click_target(300, 250, canvas_bbox=bbox)
    assert ok is True

  def test_outside_canvas_margin(self):
    bbox = {"x": 100, "y": 100, "width": 400, "height": 300}
    ok, reason = validate_click_target(95, 250, canvas_bbox=bbox)
    assert ok is True  # within 5px margin

  def test_far_outside_canvas_invalid(self):
    bbox = {"x": 100, "y": 100, "width": 400, "height": 300}
    ok, reason = validate_click_target(0, 0, canvas_bbox=bbox)
    assert ok is False
