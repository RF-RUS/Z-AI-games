import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from uno_model_runtime.adapters import get_runtime
from uno_model_runtime.benchmark_runner import run_benchmark
from uno_model_runtime.invoker import invoke_with_fallback
from uno_model_runtime.prompts_registry import list_prompts
from uno_model_runtime.providers import get_provider
from uno_schemas.model import (
  BenchmarkResult,
  BenchmarkRunRequest,
  InferenceRequest,
  InferenceResponse,
  ModelInvocationRequest,
  ModelInvocationResponse,
  ModelProfile,
  ModelProviderHealth,
  ModelProviderType,
  RuntimeAdapter,
)
from uno_schemas.prompts import PromptProfile
from uno_shared.service_app import ServiceApp

PROFILES_PATH = Path(os.getenv("UNO_MODEL_PROFILES_PATH", "./models/profiles"))
REGISTRY_URL = os.getenv("UNO_MODEL_REGISTRY_URL", "http://127.0.0.1:8110")
# Native Ollama endpoint (the OpenAI-compatible /v1 base used by profiles is the
# same host with a /v1 suffix; we need the native base for /api/tags).
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

svc = ServiceApp("model-runtime-service", description="Unified model inference and benchmarks")
app: FastAPI = svc.create_app()

_active_runtime = RuntimeAdapter.MOCK
_profile_cache: dict[str, ModelProfile] = {}

# ── Operator model picker support ──────────────────────────────────────────────
# The operator UI switches a session's VLM live (3b↔7b↔any Ollama model). For
# models that are NOT pre-provisioned as profile files (e.g. "ollama:<name>"
# synthesized from Ollama's live /api/tags), we materialize a ModelProfile on
# the fly so /invoke can route through them without any file on disk.

_OLLAMA_DYNAMIC_PREFIX = "ollama:"


def _base_ollama_profile() -> ModelProfile | None:
  """A reference ollama profile to inherit provider/limits from for synthesis.

  Falls back to the first profile on disk whose provider is ollama_openai, or
  None when there is none (synthesis then uses safe defaults).
  """
  try:
    for path in sorted(PROFILES_PATH.glob("*.json")):
      p = ModelProfile.model_validate_json(path.read_text(encoding="utf-8"))
      if p.provider == ModelProviderType.OLLAMA_OPENAI:
        return p
  except Exception:  # noqa: BLE001 — listing is best-effort
    pass
  return None


def _synth_ollama_profile(profile_id: str) -> ModelProfile:
  """Build a ModelProfile for a dynamic "ollama:<model>" id.

  e.g. "ollama:qwen2.5vl:7b" -> a profile whose model_name is "qwen2.5vl:7b",
  routing through the Ollama OpenAI-compatible endpoint. Vision capability is
  assumed when the model name looks like a VL family (so the screenshot is
  attached); text-only models simply won't get an image.
  """
  assert profile_id.startswith(_OLLAMA_DYNAMIC_PREFIX)
  model_name = profile_id[len(_OLLAMA_DYNAMIC_PREFIX):]
  ref = _base_ollama_profile()
  # The reference profile's base_url already carries the /v1 suffix
  # ("http://127.0.0.1:11434/v1") — appending another one produced the 404
  # http://127.0.0.1:11434/v1/v1/chat/completions on first live use.
  if ref and ref.base_url:
    base_url = ref.base_url.rstrip("/")
    if not base_url.endswith("/v1"):
      base_url += "/v1"
  else:
    base_url = OLLAMA_BASE_URL.rstrip("/") + "/v1"
  # Vision heuristic: "vl" (qwen2.5-vl, qwen3-vl, ...), "vision", or "llava".
  # Deliberately conservative — a false text-only flag only means the screenshot
  # isn't attached (model answers blind), a false vision flag wastes bandwidth.
  vl_family = any(tok in model_name.lower() for tok in ("vl", "vision", "llava"))
  return ModelProfile(
    profile_id=profile_id,
    display_name=f"Ollama · {model_name}",
    provider=ModelProviderType.OLLAMA_OPENAI,
    base_url=base_url,
    model_name=model_name,
    api_key_env=ref.api_key_env if ref else "OLLAMA_API_KEY",
    enabled=True,
    capabilities=["vision_understanding", "text_generation"],
    use_cases=["perception_board"],
    priority=ref.priority if ref else 40,
    max_tokens_default=ref.max_tokens_default if ref else 1024,
    temperature_default=ref.temperature_default if ref else 0.1,
    timeout_seconds=ref.timeout_seconds if ref else 180.0,
    supports_json_mode=ref.supports_json_mode if ref else False,
    supports_multimodal=vl_family,
    metadata={"synthesized": "1", "source": "ollama-api-tags"},
  )


def _load_profile(profile_id: str) -> ModelProfile:
  if profile_id in _profile_cache:
    return _profile_cache[profile_id]
  # Dynamic Ollama model not yet cached: synthesize on demand, then cache.
  if profile_id.startswith(_OLLAMA_DYNAMIC_PREFIX):
    p = _synth_ollama_profile(profile_id)
    _profile_cache[profile_id] = p
    return p
  path = PROFILES_PATH / f"{profile_id.replace('/', '__')}.json"
  if path.exists():
    p = ModelProfile.model_validate_json(path.read_text(encoding="utf-8"))
    _profile_cache[profile_id] = p
    return p
  raise HTTPException(404, f"profile not found: {profile_id}")


async def _resolve_profile(req: ModelInvocationRequest) -> ModelProfile:
  if req.profile_id:
    return _load_profile(req.profile_id)
  async with httpx.AsyncClient() as client:
    r = await client.post(f"{REGISTRY_URL}/route", json={
      "use_case": req.context.use_case.value,
    }, timeout=5.0)
    r.raise_for_status()
    route = r.json()
  return _load_profile(route["profile_id"])


@app.post("/invoke", response_model=ModelInvocationResponse, tags=["inference"])
async def invoke(req: ModelInvocationRequest) -> ModelInvocationResponse:
  profile = await _resolve_profile(req)
  if not profile.enabled:
    raise HTTPException(503, "profile disabled")
  return await invoke_with_fallback(profile, req)


@app.post("/infer", response_model=InferenceResponse, tags=["inference"])
async def infer_legacy(req: InferenceRequest) -> InferenceResponse:
  """Legacy endpoint — prefer /invoke."""
  runtime = get_runtime(_active_runtime)
  return await runtime.infer(req)


@app.get("/prompts", response_model=list[PromptProfile], tags=["prompts"])
async def get_prompts() -> list[PromptProfile]:
  return list_prompts()


@app.post("/benchmark/run", response_model=BenchmarkResult, tags=["benchmark"])
async def benchmark_run(req: BenchmarkRunRequest) -> BenchmarkResult:
  profile_id = req.profile_id or "mock/uno-assistant"
  profile = _load_profile(profile_id)
  if req.provider_override:
    profile = profile.model_copy(update={"provider": req.provider_override})
  return await run_benchmark(req.dataset, profile, req.prompt_id)


@app.get("/providers/{provider}/health", response_model=ModelProviderHealth, tags=["health"])
async def provider_health(provider: ModelProviderType, profile_id: str = "mock/uno-assistant") -> ModelProviderHealth:
  profile = _load_profile(profile_id)
  if profile.provider != provider:
    profile = profile.model_copy(update={"provider": provider})
  return await get_provider(provider).health(profile)


@app.get("/status", tags=["inference"])
async def status() -> dict:
  return {"active_runtime_legacy": _active_runtime.value, "prompts": len(list_prompts())}


# ── Model picker endpoints (operator UI) ───────────────────────────────────────

def _vision_profile_brief(p: ModelProfile) -> dict:
  """Compact profile descriptor for the picker (no api_key_env, no metadata)."""
  return {
    "profile_id": p.profile_id,
    "display_name": p.display_name,
    "provider": p.provider.value,
    "model_name": p.model_name,
    "enabled": p.enabled,
    "supports_multimodal": p.supports_multimodal,
  }


@app.get("/profiles", tags=["models"])
async def list_profiles() -> list[dict]:
  """Every profile on disk that can serve perception_board, in priority order.

  The picker shows these as the "known" models (local/ollama-vlm = 3b,
  local/ollama-vlm-7b = 7b, ...). Disabled ones are included but flagged so the
  UI can grey them out with a hint.
  """
  out: list[tuple[int, dict]] = []
  try:
    for path in sorted(PROFILES_PATH.glob("*.json")):
      try:
        p = ModelProfile.model_validate_json(path.read_text(encoding="utf-8"))
      except Exception:  # noqa: BLE001 — a malformed file must not break the list
        continue
      if "perception_board" in p.use_cases or p.supports_multimodal:
        out.append((p.priority, _vision_profile_brief(p)))
  except OSError:
    pass
  out.sort(key=lambda t: -t[0])
  return [b for _, b in out]


@app.get("/ollama/models", tags=["models"])
async def list_ollama_models() -> dict:
  """Live Ollama inventory (native /api/tags) for the picker's dynamic section.

  Returns {"reachable": bool, "models": [{name, vision, size_gb, params}]}.
  vision = Ollama reports the 'vision' capability. Size is approximate so the
  UI can show a light OOM-risk hint without a hard block (operator's choice).
  """
  try:
    async with httpx.AsyncClient(timeout=3.0) as client:
      r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
      r.raise_for_status()
      raw = r.json().get("models", [])
    models = []
    for m in raw:
      caps = m.get("capabilities") or []
      size_gb = round((m.get("size") or 0) / (1024 ** 3), 1)
      models.append({
        "name": m.get("name") or m.get("model") or "",
        "profile_id": f"ollama:{m.get('name') or m.get('model') or ''}",
        "vision": "vision" in caps,
        "size_gb": size_gb,
        "params": (m.get("details") or {}).get("parameter_size") or None,
        "quantization": (m.get("details") or {}).get("quantization_level") or None,
      })
    return {"reachable": True, "models": models}
  except Exception as exc:  # noqa: BLE001 — picker degrades to "Ollama offline"
    return {"reachable": False, "models": [], "error": str(exc)}


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_model_runtime.api:app", host=os.getenv("UNO_UVICORN_HOST", "127.0.0.1"), port=SERVICE_PORTS["model-runtime-service"])
