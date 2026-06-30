"""Real UNO web profile validation."""


from uno_adapter_web.profiles import load_profile
from uno_schemas.adapter_web import WebAdapterProfile

REQUIRED_SELECTORS = [
  "game_root",
  "discard_top_card",
  "hand_area",
  "hand_cards",
  "draw_button",
  "play_button",
  "current_player",
]


def test_real_unoh_profile_loads():
  p = load_profile("real-unoh-web")
  assert p.profile_id == "real-unoh-web"
  assert "pizz.uno" in p.launch_url


def test_real_unoh_required_selectors():
  p = load_profile("real-unoh-web")
  for key in REQUIRED_SELECTORS:
    assert key in p.selectors, f"missing selector: {key}"
    assert p.selectors[key].primary


def test_real_unoh_schema_valid():
  p = load_profile("real-unoh-web")
  WebAdapterProfile.model_validate(p.model_dump())


def test_real_unoh_bootstrap_mappings():
  p = load_profile("real-unoh-web")
  assert "bootstrap_start_game" in p.action_mappings


def test_real_unoh_health_block():
  p = load_profile("real-unoh-web")
  assert p.health is not None
  assert "game_root" in p.health.required
