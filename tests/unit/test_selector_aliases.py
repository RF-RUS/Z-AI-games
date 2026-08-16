"""Selector aliases must come from the game PROFILE, not from locator code.

The platform is plugin-based: a generic locator must not carry UNO-specific
knowledge. target_locator.py used to hardcode {"draw": "draw_button",
"play_red_five": "play_button"} — impossible for any other game to extend.
"""

from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.rpa.perception.target_locator import locate_selector
from uno_schemas.adapter_windows import WindowsAdapterProfile


def test_selector_alias_field_is_loaded_from_profile_json():
  profile = load_profile("local-mock-uno")
  assert profile.selector_aliases.get("draw") == "draw_button"
  assert profile.selector_aliases.get("play_red_five") == "play_button"


def test_alias_resolves_layout_target_via_profile_only():
  """A synthetic profile whose aliases exist ONLY in JSON still resolves."""
  profile = WindowsAdapterProfile(
    profile_id="synthetic",
    display_name="synthetic game",
    window={"title_regex": "Synthetic"},
    selector_aliases={"attack": "attack_button"},
    layout_targets={"attack_button": {"x_ratio": 0.5, "y_ratio": 0.5, "label": "Attack"}},
  )
  window_bounds = {"left": 0.0, "top": 0.0, "right": 800.0, "bottom": 600.0}
  target = locate_selector("attack", profile, [], window_bounds=window_bounds)
  assert target is not None, "profile-declared alias must drive key expansion"
  assert target.label == "Attack"
