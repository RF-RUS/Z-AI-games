"""FastAPI service factory for consistent service bootstrap."""

from __future__ import annotations

import asyncio as _asyncio
import os
import time
import uuid
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uno_schemas.api import SERVICE_PORTS, HealthResponse, HealthStatus

from uno_shared.logging import bind_correlation_id, configure_logging, get_logger


def _observability_url() -> str | None:
  host = os.getenv("UNO_SERVICE_HOST", "127.0.0.1")
  port = SERVICE_PORTS.get("observability-service")
  if not port:
    return None
  return f"http://{host}:{port}"


class MetricsReporter:
  """Best-effort cycle-step reporter to observability-service.

  Fire-and-forget: a metrics report must never block or fail a pipeline step.
  Keeps a process-local ring buffer so /metrics works even when the
  observability service is down (e.g. unit tests, offline dev).
  """

  def __init__(self, service: str, max_recent: int = 200) -> None:
    self.service = service
    self.recent: deque[dict[str, Any]] = deque(maxlen=max_recent)
    self.counts: dict[str, int] = {}
    self.latency_ms_sum: dict[str, float] = {}

  def record(self, path: str, status_code: int, latency_ms: float) -> None:
    key = f"{status_code // 100}xx"
    self.counts[key] = self.counts.get(key, 0) + 1
    self.latency_ms_sum[key] = self.latency_ms_sum.get(key, 0.0) + latency_ms
    entry = {"service": self.service, "path": path, "status": status_code, "latency_ms": round(latency_ms)}
    self.recent.append(entry)

  def snapshot(self) -> dict[str, Any]:
    return {
      "service": self.service,
      "total_requests": sum(self.counts.values()),
      "by_status": dict(self.counts),
      "recent": list(self.recent)[-50:],
    }


_bg_tasks: set = set()


async def _report_to_observability(url: str, payload: dict[str, Any]) -> None:
  try:
    async with httpx.AsyncClient(timeout=1.0) as client:
      await client.post(f"{url}/metrics/report", json=payload)
  except Exception:  # noqa: BLE001 — metrics are best-effort, never fatal
    pass


class ServiceApp:
  """Bootstrap helper for UNO Operator microservices."""

  def __init__(self, name: str, version: str = "0.1.0", description: str = "") -> None:
    self.name = name
    self.version = version
    self.description = description
    self._startup_hooks: list = []
    self._shutdown_hooks: list = []
    self._health_details: dict[str, Any] = {}
    self.metrics = MetricsReporter(name)

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

    # Correlation/trace propagation + step metrics (see docs/architecture/overview.md).
    # - X-Trace-Id: inbound value wins; otherwise generate one so EVERY log line
    #   from every service in a pipeline run carries the same id.
    # - X-Correlation-ID is an alias of the same id for backward compatibility.
    # - Per-request duration is recorded locally and fire-and-forget reported to
    #   observability-service (/metrics/report), which aggregates it into /metrics.
    _obs_url = _observability_url() if os.getenv("UNO_METRICS_DISABLED") not in ("1", "true") else None

    @app.middleware("http")
    async def trace_and_metrics(request: Request, call_next):  # noqa: ANN001
      trace_id = request.headers.get("X-Trace-Id") or request.headers.get("X-Correlation-ID") or uuid.uuid4().hex[:16]
      bind_correlation_id(trace_id)
      started = time.perf_counter()
      try:
        response = await call_next(request)
        status_code = response.status_code
      except Exception:
        service.metrics.record(request.url.path, 500, (time.perf_counter() - started) * 1000)
        raise
      latency_ms = (time.perf_counter() - started) * 1000
      response.headers["X-Trace-Id"] = trace_id
      if request.url.path not in ("/health", "/metrics"):
        service.metrics.record(request.url.path, status_code, latency_ms)
        if _obs_url:
          task = _asyncio.ensure_future(_report_to_observability(_obs_url, {
            "service": service.name,
            "path": request.url.path,
            "status": status_code,
            "latency_ms": round(latency_ms, 1),
            "correlation_id": trace_id,
          }))
          _bg_tasks.add(task)
          task.add_done_callback(_bg_tasks.discard)
      return response

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
      return HealthResponse(
        service=service.name,
        status=HealthStatus.HEALTHY,
        version=service.version,
        details=service._health_details,
      )

    @app.get("/metrics", tags=["metrics"])
    async def local_metrics() -> dict[str, Any]:
      return service.metrics.snapshot()

    @app.get("/openapi.json", include_in_schema=False)
    async def openapi_redirect():
      return app.openapi()

    app.state.service = self
    return app


def export_json_schema(model: type[BaseModel]) -> dict:
  return model.model_json_schema()
