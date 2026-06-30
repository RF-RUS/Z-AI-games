import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uno_model_registry.registry import ModelRegistry
from uno_schemas.model import (
  ModelInstallRequest,
  ModelManifest,
  ModelProfile,
  ModelRouteSelection,
  ModelUseCase,
)
from uno_shared.service_app import ServiceApp

REGISTRY_PATH = Path(os.getenv("UNO_MODEL_REGISTRY_PATH", "./models/registry"))
PROFILES_PATH = Path(os.getenv("UNO_MODEL_PROFILES_PATH", "./models/profiles"))
registry = ModelRegistry(REGISTRY_PATH, PROFILES_PATH)

svc = ServiceApp("model-registry-service", description="Model profiles and routing")
svc.set_health_detail("profiles_count", len(registry.list_profiles()))
app: FastAPI = svc.create_app()


class RouteRequest(BaseModel):
  use_case: ModelUseCase
  profile_id: str | None = None


class SetDefaultRequest(BaseModel):
  use_case: ModelUseCase
  profile_id: str


@app.get("/models", response_model=list[ModelManifest], tags=["models"])
async def list_models() -> list[ModelManifest]:
  return registry.list_models()


@app.get("/profiles", response_model=list[ModelProfile], tags=["profiles"])
async def list_profiles() -> list[ModelProfile]:
  return registry.list_profiles()


@app.get("/profiles/{profile_id:path}", response_model=ModelProfile, tags=["profiles"])
async def get_profile(profile_id: str) -> ModelProfile:
  p = registry.get_profile(profile_id)
  if not p:
    raise HTTPException(404, "profile not found")
  return p


@app.post("/route", response_model=ModelRouteSelection, tags=["routing"])
async def route_model(req: RouteRequest) -> ModelRouteSelection:
  try:
    return registry.route(req.use_case, req.profile_id)
  except KeyError as exc:
    raise HTTPException(404, str(exc)) from None


@app.post("/profiles/{profile_id:path}/disable", response_model=ModelProfile, tags=["profiles"])
async def disable_profile(profile_id: str) -> ModelProfile:
  try:
    return registry.disable_profile(profile_id)
  except KeyError:
    raise HTTPException(404, "profile not found") from None


@app.post("/defaults", tags=["routing"])
async def set_default(req: SetDefaultRequest) -> dict:
  try:
    registry.set_default(req.use_case, req.profile_id)
    return {"use_case": req.use_case.value, "profile_id": req.profile_id}
  except KeyError as exc:
    raise HTTPException(404, str(exc)) from None


@app.get("/models/{model_id:path}", response_model=ModelManifest, tags=["models"])
async def get_model(model_id: str) -> ModelManifest:
  m = registry.get(model_id)
  if not m:
    raise HTTPException(404, "model not found")
  return m


@app.post("/models/{model_id:path}/activate", response_model=ModelManifest, tags=["models"])
async def activate(model_id: str) -> ModelManifest:
  try:
    return registry.activate(model_id)
  except KeyError:
    raise HTTPException(404, "model not found") from None


@app.post("/models/install", response_model=ModelManifest, tags=["models"])
async def install(req: ModelInstallRequest) -> ModelManifest:
  return registry.install(req)


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_model_registry.api:app", host="127.0.0.1", port=SERVICE_PORTS["model-registry-service"])
