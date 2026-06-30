"""Canvas coordinate click payload and bounds handling."""

import pytest
from uno_adapter_web.canvas_coords import (
  build_coordinate_click_payload,
  click_point_from_canvas,
  diagnose_page,
  resolve_layout_target_key,
)
from uno_adapter_web.profiles import load_profile
from uno_schemas.adapter_web import WebAdapterProfile, WebAutomationMode


def test_click_point_from_canvas():
  bounds = {"x": 100.0, "y": 50.0, "width": 800.0, "height": 600.0}
  point = click_point_from_canvas(bounds, 0.5, 0.82)
  assert point == {"x": 500.0, "y": 542.0}


def test_resolve_layout_target_aliases():
  profile = load_profile("scuffed-uno-web")
  assert resolve_layout_target_key("hand_slot_0", profile) == "hand_slot_0"
  assert resolve_layout_target_key("draw", profile) == "draw"


def test_build_coordinate_click_payload():
  profile = load_profile("scuffed-uno-web")
  bounds = {"x": 0.0, "y": 0.0, "width": 1000.0, "height": 800.0}
  point, label = build_coordinate_click_payload("draw", profile, bounds)
  assert "x" in point and "y" in point
  # Draw target uses absolute coords from calibration
  assert point["x"] == pytest.approx(961.0)
  assert point["y"] == pytest.approx(507.0)


def test_build_payload_missing_layout_raises():
  profile = WebAdapterProfile(
    profile_id="empty",
    display_name="empty",
    launch_url="http://example.com",
  )
  with pytest.raises(ValueError, match="no layout_targets"):
    build_coordinate_click_payload("play_card", profile, {"x": 0, "y": 0, "width": 100, "height": 100})


def test_diagnose_page_canvas_mode():
  diag = diagnose_page({"x": 1, "y": 2, "width": 640, "height": 480}, lobby_count=0)
  assert diag.automation_mode == WebAutomationMode.CANVAS_COORDINATE
  assert diag.canvas_detected is True
  assert diag.uia_actionable_in_match is False


def test_diagnose_page_lobby_mode():
  diag = diagnose_page(None, lobby_count=2)
  assert diag.automation_mode == WebAutomationMode.LOBBY_HTML
  assert "Lobby HTML" in diag.message


def test_scuffed_profile_is_canvas_coordinate():
  profile = load_profile("scuffed-uno-web")
  assert profile.match_automation == "canvas_coordinate"
  assert profile.canvas_selector == "canvas"
