import os
from pathlib import Path

import yaml
from fastapi import FastAPI
from pydantic import BaseModel, Field
from uno_schemas.chat import ChatMode
from uno_schemas.decision import StrategyId
from uno_schemas.session import AdapterType
from uno_shared.service_app import ServiceApp

DEFAULT_CONFIG = {
  "features": {
    "chat_enabled": True,
    "model_assist": False,
    "vlm_perception": False,
  },
  "defaults": {
    "adapter_type": AdapterType.MOCK.value,
    "strategy_id": StrategyId.HEURISTIC.value,
    "chat_mode": ChatMode.DETECT_ONLY.value,
    "min_confidence": 0.5,
  },
  "services": {},
}


class FeatureFlags(BaseModel):
  chat_enabled: bool = True
  model_assist: bool = False
  vlm_perception: bool = False


class AppConfig(BaseModel):
  features: FeatureFlags = Field(default_factory=FeatureFlags)
  defaults: dict = Field(default_factory=dict)


def load_config(path: Path | None = None) -> AppConfig:
  config_path = path or Path(os.getenv("UNO_CONFIG_PATH", "./config/default.yaml"))
  if config_path.exists():
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)
  return AppConfig.model_validate(DEFAULT_CONFIG)


_config = load_config()
svc = ServiceApp("config-service", description="Typed configuration and feature flags")
app: FastAPI = svc.create_app()


@app.get("/config", response_model=AppConfig, tags=["config"])
async def get_config() -> AppConfig:
  return _config


@app.get("/features", response_model=FeatureFlags, tags=["config"])
async def get_features() -> FeatureFlags:
  return _config.features


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_config.api:app", host="127.0.0.1", port=SERVICE_PORTS["config-service"])
