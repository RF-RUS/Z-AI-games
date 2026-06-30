"""Windows profile unit tests."""


from uno_adapter_windows.profiles import list_profiles, load_profile
from uno_schemas.adapter_windows import WindowsAdapterProfile


def test_list_profiles():
  profiles = list_profiles()
  assert any(p.profile_id == "local-mock-uno" for p in profiles)


def test_load_local_profile():
  p = load_profile("local-mock-uno")
  assert p.window.title_regex
  assert "discard_top_card" in p.selectors


def test_real_uno_desktop_profile_exists():
  p = load_profile("real-uno-desktop")
  assert p.window.title_regex == "UNO"
  assert p.window.exclude_title_regex
  assert p.test_target_script is None


def test_profile_roundtrip():
  p = load_profile("local-mock-uno")
  assert WindowsAdapterProfile.model_validate_json(p.model_dump_json()).profile_id == p.profile_id
