"""FastAPI service factory for consistent service bootstrap."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uno_schemas.api import HealthResponse, HealthStatus

from uno_shared.logging import configure_logging, get_logger


class ServiceApp:
  """Bootstrap helper for UNO Operator microservices."""

  def __init__(self, name: str, version: str = "0.1.0", description: str = "") -> None:
    self.name = name
    self.version = version
    self.description = description
    self._startup_hooks: list = []
    self._shutdown_hooks: list = []
    self._health_details: dict[str, Any] = {}

  def on_startup(self, fn) -> Any:
    self._startup_hooks.append(fn)
    return fn

  def on_shutdown(self, fn) -> Any:
    self._shutdown_hooks.append(fn)
    return fn

  def set_health_detail(self, key: str, value: Any) -> None:
    self._health_details[key] = value

  def create_app(self) -> FastAPI:
    service = self

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
      configure_logging()
      get_logger(service.name).info("starting", version=service.version)
      for hook in service._startup_hooks:
        result = hook()
        if hasattr(result, "__await__"):
          await result
      yield
      for hook in service._shutdown_hooks:
        result = hook()
        if hasattr(result, "__await__"):
          await result
      get_logger(service.name).info("stopped")

    app = FastAPI(
      title=f"UNO Operator — {self.name}",
      version=self.version,
      description=self.description,
      lifespan=lifespan,
    )
    app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
      return HealthResponse(
        service=service.name,
        status=HealthStatus.HEALTHY,
        version=service.version,
        details=service._health_details,
      )

    @app.get("/openapi.json", include_in_schema=False)
    async def openapi_redirect():
      return app.openapi()

    app.state.service = self
    return app


def export_json_schema(model: type[BaseModel]) -> dict:
  return model.model_json_schema()
