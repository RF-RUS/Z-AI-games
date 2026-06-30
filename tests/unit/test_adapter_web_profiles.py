"""Web adapter profile validation tests."""

import pytest
from uno_adapter_web.profiles import list_profiles, load_profile
from uno_schemas.adapter_web import WebAdapterProfile


def test_list_profiles():
  profiles = list_profiles()
  assert any(p.profile_id == "local-mock-uno" for p in profiles)
  assert any(p.profile_id == "real-unoh-web" for p in profiles)
  assert any(p.profile_id == "scuffed-uno-web" for p in profiles)


def test_load_local_mock_uno_profile():
  p = load_profile("local-mock-uno")
  assert p.launch_url.startswith("http://")
  assert "discard_top_card" in p.selectors
  assert p.readiness_selector is not None


def test_profile_schema_roundtrip():
  p = load_profile("local-mock-uno")
  restored = WebAdapterProfile.model_validate_json(p.model_dump_json())
  assert restored.profile_id == p.profile_id


def test_missing_profile_raises():
  with pytest.raises(FileNotFoundError):
    load_profile("nonexistent-profile")
