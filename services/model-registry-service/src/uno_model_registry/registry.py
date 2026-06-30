"""Extended model profile registry with routing."""

from __future__ import annotations

from pathlib import Path

from uno_schemas.model import (
  ModelCapability,
  ModelInstallRequest,
  ModelManifest,
  ModelModality,
  ModelProfile,
  ModelProviderType,
  ModelRouteSelection,
  ModelUseCase,
  RuntimeAdapter,
)

DEFAULT_MANIFESTS: list[ModelManifest] = [
  ModelManifest(
    model_id="waltgrace/poker-gemma4-26b-a4b-lora",
    display_name="Poker Gemma 4 26B (experimental)",
    source_repo="waltgrace/poker-gemma4-26b-a4b-lora",
    modality=ModelModality.MULTIMODAL,
    runtime=RuntimeAdapter.LLAMA_CPP,
    provider=ModelProviderType.LLAMA_CPP_OPENAI,
    capabilities=[ModelCapability.TEXT_GENERATION, ModelCapability.VISION_UNDERSTANDING],
    enabled=False,
    metadata={"profile": "experimental"},
  ),
  ModelManifest(
    model_id="mock/uno-assistant",
    display_name="Mock UNO Assistant",
    source_repo="local",
    modality=ModelModality.TEXT,
    runtime=RuntimeAdapter.MOCK,
    provider=ModelProviderType.MOCK,
    capabilities=[ModelCapability.TEXT_GENERATION, ModelCapability.CHAT_REPLY],
    enabled=True,
  ),
]

DEFAULT_PROFILES: list[ModelProfile] = [
  ModelProfile(
    profile_id="mock/uno-assistant",
    display_name="Mock UNO Assistant",
    provider=ModelProviderType.MOCK,
    enabled=True,
    use_cases=[
      ModelUseCase.CHAT_INTENT, ModelUseCase.CHAT_REPLY, ModelUseCase.EXPLANATION,
      ModelUseCase.PERCEPTION_DISPUTE, ModelUseCase.POLICY_ADVICE, ModelUseCase.BENCHMARK_ONLY,
    ],
    priority=10,
    supports_json_mode=True,
  ),
]


class ModelRegistry:
  def __init__(self, registry_path: Path, profiles_path: Path | None = None) -> None:
    self.registry_path = registry_path
    self.profiles_path = profiles_path or registry_path.parent / "profiles"
    self.registry_path.mkdir(parents=True, exist_ok=True)
    self.profiles_path.mkdir(parents=True, exist_ok=True)
    self._manifests: dict[str, ModelManifest] = {}
    self._profiles: dict[str, ModelProfile] = {}
    self._defaults: dict[ModelUseCase, str] = {}
    self._load()

  def _load(self) -> None:
    for manifest in DEFAULT_MANIFESTS:
      self._manifests[manifest.model_id] = manifest.model_copy()
    for profile in DEFAULT_PROFILES:
      self._profiles[profile.profile_id] = profile.model_copy()
    for file in self.registry_path.glob("*.json"):
      if "profile" in file.name:
        continue
      m = ModelManifest.model_validate_json(file.read_text(encoding="utf-8"))
      self._manifests[m.model_id] = m
    for file in self.profiles_path.glob("*.json"):
      p = ModelProfile.model_validate_json(file.read_text(encoding="utf-8"))
      self._profiles[p.profile_id] = p
      if p.metadata.get("default_for") == "all":
        for uc in p.use_cases:
          self._defaults[uc] = p.profile_id

  def list_models(self) -> list[ModelManifest]:
    return list(self._manifests.values())

  def list_profiles(self) -> list[ModelProfile]:
    return list(self._profiles.values())

  def get(self, model_id: str) -> ModelManifest | None:
    return self._manifests.get(model_id)

  def get_profile(self, profile_id: str) -> ModelProfile | None:
    return self._profiles.get(profile_id)

  def route(self, use_case: ModelUseCase, profile_id: str | None = None) -> ModelRouteSelection:
    if profile_id:
      p = self.get_profile(profile_id)
      if not p or not p.enabled:
        raise KeyError(f"profile unavailable: {profile_id}")
      return ModelRouteSelection(
        profile_id=p.profile_id, provider=p.provider, base_url=p.base_url,
        model_name=p.model_name, use_case=use_case, reason="explicit",
      )
    candidates = [p for p in self._profiles.values() if p.enabled and use_case in p.use_cases]
    if not candidates:
      raise KeyError(f"no profile for use case: {use_case.value}")
    p = sorted(candidates, key=lambda x: x.priority)[0]
    return ModelRouteSelection(
      profile_id=p.profile_id, provider=p.provider, base_url=p.base_url,
      model_name=p.model_name, use_case=use_case, reason="priority",
    )

  def set_default(self, use_case: ModelUseCase, profile_id: str) -> None:
    if profile_id not in self._profiles:
      raise KeyError(profile_id)
    self._defaults[use_case] = profile_id

  def disable_profile(self, profile_id: str) -> ModelProfile:
    p = self._profiles[profile_id]
    p.enabled = False
    return p

  def activate(self, model_id: str) -> ModelManifest:
    if model_id not in self._manifests:
      raise KeyError(f"model not found: {model_id}")
    for mid in self._manifests:
      self._manifests[mid].enabled = mid == model_id
    return self._manifests[model_id]

  def install(self, req: ModelInstallRequest) -> ModelManifest:
    manifest = self.get(req.model_id)
    if not manifest:
      manifest = ModelManifest(
        model_id=req.model_id, display_name=req.model_id, source_repo=req.model_id,
        modality=ModelModality.TEXT, runtime=RuntimeAdapter.LLAMA_CPP,
      )
    manifest.local_path = str(self.registry_path / req.model_id.replace("/", "__"))
    self._manifests[req.model_id] = manifest
    out = self.registry_path / f"{req.model_id.replace('/', '__')}.json"
    out.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest
