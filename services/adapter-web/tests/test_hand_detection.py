"""Tests for screenshot-based hand detection, card identity, and calibration."""

import json

from PIL import Image
from uno_adapter_web.hand_detection import (
    ActionGrounding,
    CalibrationResult,
    DetectedCard,
    _classify_pixel_color,
    _detect_card_number,
    _dominant_color_in_region,
    _find_color_regions,
    _find_shape_regions,
    calibrate_from_screenshot,
    detect_game_elements,
    detect_hand_cards,
    detect_screen_state,
    save_calibration,
)
from uno_adapter_web.temporal_consistency import TemporalState, stabilize_detection


def _make_test_image(width=1280, height=800, hand_colors=None):
    img = Image.new("RGB", (width, height), (40, 40, 40))
    if hand_colors:
        y_start = int(height * 0.72)
        slot_width = width // (len(hand_colors) + 1)
        for i, color in enumerate(hand_colors):
            rgb = {"red": (220, 40, 40), "blue": (40, 40, 220), "green": (40, 180, 40), "yellow": (220, 200, 40)}
            x = slot_width * (i + 1)
            for dy in range(60):
                for dx in range(80):
                    img.putpixel((x + dx, y_start + dy), rgb.get(color, (128, 128, 128)))
    return img


class TestPixelClassification:
  def test_red_pixel(self):
    assert _classify_pixel_color(220, 40, 40) == "red"

  def test_blue_pixel(self):
    assert _classify_pixel_color(40, 40, 220) == "blue"

  def test_green_pixel(self):
    assert _classify_pixel_color(40, 180, 40) == "green"

  def test_yellow_pixel(self):
    assert _classify_pixel_color(220, 200, 40) == "yellow"

  def test_white_background(self):
    assert _classify_pixel_color(255, 255, 255) is None

  def test_black_border(self):
    assert _classify_pixel_color(10, 10, 10) is None


class TestCardNumberDetection:
  def test_returns_none_for_small_bbox(self):
    img = Image.new("RGB", (10, 10), (200, 200, 200))
    num, conf = _detect_card_number(img, {"x": 0, "y": 0, "width": 2, "height": 2})
    assert num is None

  def test_returns_tuple(self):
    img = Image.new("RGB", (40, 60), (220, 40, 40))
    num, conf = _detect_card_number(img, {"x": 0, "y": 0, "width": 40, "height": 60})
    assert isinstance(num, (str, type(None)))
    assert isinstance(conf, float)


class TestColorRegionDetection:
  def test_finds_red_region(self):
    img = _make_test_image(hand_colors=["red"])
    regions = _find_color_regions(img, {"x": 0, "y": 576, "width": 1280, "height": 200}, min_area=100)
    assert len(regions) >= 1
    assert regions[0]["color"] == "red"

  def test_finds_multiple_regions(self):
    img = _make_test_image(hand_colors=["red", "blue", "green"])
    regions = _find_color_regions(img, {"x": 0, "y": 576, "width": 1280, "height": 200}, min_area=100)
    colors = [r["color"] for r in regions]
    assert "red" in colors
    assert "blue" in colors
    assert "green" in colors

  def test_sorted_by_x(self):
    img = _make_test_image(hand_colors=["green", "red", "blue"])
    regions = _find_color_regions(img, {"x": 0, "y": 576, "width": 1280, "height": 200}, min_area=100)
    if len(regions) >= 2:
      assert regions[0]["bbox"]["x"] <= regions[1]["bbox"]["x"]


class TestHandCardDetection:
  def test_detects_cards(self):
    img = _make_test_image(hand_colors=["red", "blue", "green"])
    cards = detect_hand_cards(img, {"x": 0, "y": 576, "width": 1280, "height": 200})
    assert len(cards) >= 2
    assert all(isinstance(c, DetectedCard) for c in cards)

  def test_slot_indices_ordered(self):
    img = _make_test_image(hand_colors=["red", "blue", "green"])
    cards = detect_hand_cards(img, {"x": 0, "y": 576, "width": 1280, "height": 200})
    indices = [c.slot_index for c in cards]
    assert indices == sorted(indices)

  def test_click_coordinates_are_center(self):
    img = _make_test_image(hand_colors=["red"])
    cards = detect_hand_cards(img, {"x": 0, "y": 576, "width": 1280, "height": 200})
    if cards:
      c = cards[0]
      assert c.click_x == c.bbox["x"] + c.bbox["width"] // 2
      assert c.click_y == c.bbox["y"] + c.bbox["height"] // 2

  def test_cards_have_number_field(self):
    img = _make_test_image(hand_colors=["red"])
    cards = detect_hand_cards(img, {"x": 0, "y": 576, "width": 1280, "height": 200})
    if cards:
      assert hasattr(cards[0], "number")
      assert hasattr(cards[0], "number_confidence")


class TestFullGrounding:
  def test_returns_grounding(self):
    img = _make_test_image(hand_colors=["red", "blue"])
    g = detect_game_elements(img)
    assert isinstance(g, ActionGrounding)
    assert g.detection_confidence > 0

  def test_empty_image_low_confidence(self):
    img = Image.new("RGB", (1280, 800), (40, 40, 40))
    g = detect_game_elements(img)
    assert g.detection_confidence == 0.0


class TestScreenStateDetection:
  def test_in_game_with_cards(self):
    img = _make_test_image(hand_colors=["red", "blue", "green", "yellow"])
    state = detect_screen_state(img, lobby_region={"x": 0, "y": 0, "width": 1280, "height": 800})
    assert state == "in_game"

  def test_unknown_with_no_cards(self):
    img = Image.new("RGB", (1280, 800), (40, 40, 40))
    state = detect_screen_state(img, lobby_region={"x": 0, "y": 0, "width": 1280, "height": 800})
    assert state == "unknown"


class TestCalibration:
  def test_calibration_detects_regions(self):
    img = _make_test_image(hand_colors=["red", "blue", "green"])
    result = calibrate_from_screenshot(img, 1280, 800)
    assert isinstance(result, CalibrationResult)
    assert result.canvas_width == 1280
    assert result.canvas_height == 800

  def test_calibration_returns_hand_region(self):
    img = _make_test_image(hand_colors=["red", "blue", "green"])
    result = calibrate_from_screenshot(img, 1280, 800)
    assert "x" in result.hand_region
    assert "y" in result.hand_region
    assert "width" in result.hand_region
    assert "height" in result.hand_region

  def test_calibration_empty_image(self):
    img = Image.new("RGB", (1280, 800), (40, 40, 40))
    result = calibrate_from_screenshot(img, 1280, 800)
    assert result.card_count == 0

  def test_save_calibration(self, tmp_path):
    img = _make_test_image(hand_colors=["red", "blue"])
    result = calibrate_from_screenshot(img, 1280, 800)

    profile = {
        "profile_id": "scuffed-uno-web",
        "layout_targets": {
            "hand_area": {"x": 0, "y": 600, "width": 1280, "height": 200},
        },
    }
    profile_path = tmp_path / "test-profile.json"
    profile_path.write_text(json.dumps(profile))

    report = save_calibration(result, profile_path)
    assert report["profile_id"] == "scuffed-uno-web"
    assert report["calibrated_slots"] >= 0

    updated = json.loads(profile_path.read_text())
    assert "hand_area" in updated["layout_targets"]
    assert "draw_area" in updated["layout_targets"]


# --- Shape detection tests ---

class TestShapeDetection:
  def test_finds_rectangular_region(self):
    img = Image.new("RGB", (100, 100), (40, 40, 40))
    for y in range(20, 80):
      for x in range(20, 80):
        img.putpixel((x, y), (200, 200, 200))
    shapes = _find_shape_regions(img, min_area=200, max_area_ratio=0.80)
    assert len(shapes) >= 1

  def test_empty_image_no_shapes(self):
    img = Image.new("RGB", (100, 100), (40, 40, 40))
    shapes = _find_shape_regions(img, min_area=1000)
    assert len(shapes) == 0

  def test_dominant_color_in_region(self):
    img = Image.new("RGB", (100, 100), (40, 40, 40))
    for y in range(10, 90):
      for x in range(10, 90):
        img.putpixel((x, y), (220, 40, 40))
    color = _dominant_color_in_region(img, {"x": 10, "y": 10, "width": 80, "height": 80})
    assert color == "red"


class TestTemporalConsistency:
  def test_stable_detection_keeps_previous(self):
    state = TemporalState()
    cards = [DetectedCard(color="red", number="5", slot_index=0, bbox={"x": 100, "y": 100, "width": 50, "height": 80}, click_x=125, click_y=140, confidence=0.8)]
    grounding = ActionGrounding(hand=cards, detection_confidence=0.8)
    result = stabilize_detection(grounding, state, confidence_threshold=0.3)
    assert result.hand[0].color == "red"

  def test_low_confidence_keeps_previous(self):
    state = TemporalState()
    good_cards = [DetectedCard(color="blue", number="3", slot_index=0, bbox={"x": 100, "y": 100, "width": 50, "height": 80}, click_x=125, click_y=140, confidence=0.8)]
    good_grounding = ActionGrounding(hand=good_cards, detection_confidence=0.8)
    stabilize_detection(good_grounding, state)

    bad_cards = [DetectedCard(color="unknown", number=None, slot_index=0, bbox={"x": 100, "y": 100, "width": 50, "height": 80}, click_x=125, click_y=140, confidence=0.1)]
    bad_grounding = ActionGrounding(hand=bad_cards, detection_confidence=0.1)
    result = stabilize_detection(bad_grounding, state)
    assert result.hand[0].color == "blue"

  def test_new_detection_replaces_old(self):
    state = TemporalState()
    good_cards = [DetectedCard(color="red", number="5", slot_index=0, bbox={"x": 100, "y": 100, "width": 50, "height": 80}, click_x=125, click_y=140, confidence=0.8)]
    good_grounding = ActionGrounding(hand=good_cards, detection_confidence=0.8)
    stabilize_detection(good_grounding, state)

    new_cards = [DetectedCard(color="blue", number="3", slot_index=0, bbox={"x": 100, "y": 100, "width": 50, "height": 80}, click_x=125, click_y=140, confidence=0.8)]
    new_grounding = ActionGrounding(hand=new_cards, detection_confidence=0.8)
    result = stabilize_detection(new_grounding, state)
    assert result.hand[0].color == "blue"
