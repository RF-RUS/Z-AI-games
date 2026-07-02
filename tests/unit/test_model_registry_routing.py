"""Model registry routing tests."""


from uno_model_registry.registry import ModelRegistry
from uno_schemas.model import ModelUseCase


def test_list_profiles(tmp_path):
  reg = ModelRegistry(tmp_path, tmp_path / "profiles")
  assert any(p.profile_id == "mock/uno-assistant" for p in reg.list_profiles())


def test_route_chat_intent():
  from pathlib import Path
  reg = ModelRegistry(Path("./models/registry"), Path("./models/profiles"))
  route = reg.route(ModelUseCase.CHAT_INTENT)
  assert route.profile_id == "mock/uno-assistant"


def test_disable_profile():
  from pathlib import Path
  reg = ModelRegistry(Path("./models/registry"), Path("./models/profiles"))
  p = reg.disable_profile("mock/uno-assistant")
  assert not p.enabled
