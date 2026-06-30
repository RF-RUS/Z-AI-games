"""Unit tests for Windows RPA target locator."""

from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.rpa.perception.target_locator import locate_selector, locate_targets
from uno_schemas.adapter_windows import TargetAcquisitionMethod, UiNodeSnapshot


def test_locate_selector_by_profile_selector():
  profile = load_profile("local-mock-uno")
  nodes = [UiNodeSnapshot(node_id="1", name="Draw", control_type="Button", bounds={"left": 10, "top": 20, "right": 60, "bottom": 50})]
  target = locate_selector("draw_button", profile, nodes)
  assert target is not None
  assert target.method == TargetAcquisitionMethod.UIA
  assert target.confidence >= 0.8
  assert target.click_point == {"x": 35.0, "y": 35.0}


def test_locate_selector_by_action_mapping():
  profile = load_profile("local-mock-uno")
  nodes = [UiNodeSnapshot(node_id="2", name="Play Red 5", control_type="Button")]
  target = locate_selector("play_red_five", profile, nodes)
  assert target is not None
  assert target.label == "Play Red 5"


def test_coordinate_fallback_low_confidence():
  profile = load_profile("local-mock-uno")
  nodes = [UiNodeSnapshot(node_id="3", name="Draw extra", control_type="Button")]
  assert locate_selector("draw_button", profile, nodes, allow_coordinate_fallback=False) is None
  fallback = locate_selector("draw_button", profile, nodes, allow_coordinate_fallback=True)
  assert fallback is not None
  assert fallback.method == TargetAcquisitionMethod.COORDINATE
  assert fallback.confidence < 0.55


def test_locate_layout_target_for_sparse_tkinter():
  profile = load_profile("local-mock-uno")
  bounds = {"left": 100.0, "top": 50.0, "right": 740.0, "bottom": 569.0}
  target = locate_selector("play_red_five", profile, [], window_bounds=bounds)
  assert target is not None
  assert target.method == TargetAcquisitionMethod.COORDINATE
  assert target.confidence >= 0.55
  assert target.label == "Play Red 5"
  assert target.click_point is not None
  assert 400 < target.click_point["x"] < 500


def test_locate_layout_target_draw_alias():
  profile = load_profile("local-mock-uno")
  bounds = {"left": 0.0, "top": 0.0, "right": 640.0, "bottom": 480.0}
  target = locate_selector("draw", profile, [], window_bounds=bounds)
  assert target is not None
  assert target.selector_key == "draw_button"
  assert target.confidence >= 0.55


def test_locate_targets_dedupes_keys():
  profile = load_profile("local-mock-uno")
  nodes = [
    UiNodeSnapshot(node_id="1", name="Draw", control_type="Button"),
    UiNodeSnapshot(node_id="2", name="Play Red 5", control_type="Button"),
  ]
  targets = locate_targets(profile, nodes)
  keys = [t.selector_key for t in targets.targets]
  assert "draw_button" in keys or "draw" in keys
  assert len(keys) == len(set(keys))
