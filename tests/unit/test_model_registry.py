"""Model manifest validation tests."""

from pathlib import Path

from uno_model_registry.registry import ModelRegistry
from uno_schemas.model import ModelInstallRequest, ModelManifest


def test_default_manifests_load():
  reg = ModelRegistry(Path("./models/registry"))
  models = reg.list_models()
  assert any(m.model_id == "waltgrace/poker-gemma4-26b-a4b-lora" for m in models)


def test_manifest_schema_export():
  m = ModelManifest(
    model_id="test/model",
    display_name="Test",
    source_repo="test/model",
    modality="text",
    runtime="mock",
  )
  schema = m.model_json_schema()
  assert "model_id" in schema["properties"]


def test_install_model(tmp_path):
  reg = ModelRegistry(tmp_path)
  m = reg.install(ModelInstallRequest(model_id="custom/model"))
  assert m.local_path is not None
