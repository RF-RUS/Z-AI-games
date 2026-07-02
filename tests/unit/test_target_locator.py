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


def test_layout_targets_resolve_inside_client_bounds():
  """layout_targets must resolve against client_bounds, not window_bounds.

  Regression: clicks were landing in the title bar because ratios were
  applied to the full window rectangle (including chrome).
  """
  from uno_adapter_windows.rpa.perception.target_locator import ResolutionTrace, locate_layout_target

  profile = load_profile("local-mock-uno")
  # Window has a 31px title bar and 8px right border
  window_bounds = {"left": 100.0, "top": 100.0, "right": 748.0, "bottom": 619.0}
  # Client area is 640x480, starting at (100, 131)
  client_bounds = {"left": 100.0, "top": 131.0, "right": 740.0, "bottom": 611.0}

  # With client_bounds, draw_button (x_ratio=0.44, y_ratio=0.34) should land
  # inside the client area: x = 100 + 640*0.44 = 381.6, y = 131 + 480*0.34 = 294.2
  target = locate_layout_target("draw_button", profile, window_bounds, client_bounds)
  assert target is not None
  cx = target.click_point["x"]
  cy = target.click_point["y"]
  assert client_bounds["left"] <= cx <= client_bounds["right"], (
    f"click_x={cx} should be inside client area [{client_bounds['left']}, {client_bounds['right']}]"
  )
  assert client_bounds["top"] <= cy <= client_bounds["bottom"], (
    f"click_y={cy} should be inside client area [{client_bounds['top']}, {client_bounds['bottom']}]"
  )

  # Without client_bounds, it falls back to window_bounds
  target_win = locate_layout_target("draw_button", profile, window_bounds)
  assert target_win is not None
  # window_bounds y = 100 + 519*0.34 = 276.46 — 17.7px higher (closer to title bar)
  # than client_bounds y = 131 + 480*0.34 = 294.2
  assert target_win.click_point["y"] < target.click_point["y"], (
    "without client_bounds, click is shifted up toward the title bar"
  )


def test_locate_selector_uses_client_bounds_for_layout():
  """locate_selector passes client_bounds through to layout_targets."""
  from uno_adapter_windows.rpa.perception.target_locator import ResolutionTrace

  profile = load_profile("local-mock-uno")
  window_bounds = {"left": 100.0, "top": 100.0, "right": 748.0, "bottom": 619.0}
  client_bounds = {"left": 100.0, "top": 131.0, "right": 740.0, "bottom": 611.0}

  trace = ResolutionTrace()
  target = locate_selector(
    "draw", profile, [],
    window_bounds=window_bounds, client_bounds=client_bounds,
    trace=trace,
  )
  assert target is not None
  assert trace.source == "layout_targets"
  # Click should be inside client area
  assert client_bounds["top"] <= target.click_point["y"] <= client_bounds["bottom"]
