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

svc = ServiceApp("model-runtime-service", description="Unified model inference and benchmarks")
app: FastAPI = svc.create_app()

_active_runtime = RuntimeAdapter.MOCK
_profile_cache: dict[str, ModelProfile] = {}


def _load_profile(profile_id: str) -> ModelProfile:
  if profile_id in _profile_cache:
    return _profile_cache[profile_id]
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


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_model_runtime.api:app", host="127.0.0.1", port=SERVICE_PORTS["model-runtime-service"])
