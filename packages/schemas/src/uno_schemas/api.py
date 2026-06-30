"""Service API contracts and health models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
  HEALTHY = "healthy"
  DEGRADED = "degraded"
  UNHEALTHY = "unhealthy"


class HealthResponse(BaseModel):
  service: str
  status: HealthStatus
  version: str = "0.1.0"
  details: dict[str, Any] = Field(default_factory=dict)


class ServiceInfo(BaseModel):
  name: str
  port: int
  description: str


SERVICE_PORTS: dict[str, int] = {
  "session-orchestrator": 8100,
  "uno-core": 8101,
  "state-replay-service": 8102,
  "perception-service": 8103,
  "adapter-web": 8104,
  "adapter-windows": 8105,
  "decision-service": 8106,
  "policy-guard": 8107,
  "chat-intent-service": 8108,
  "chat-response-service": 8109,
  "model-registry-service": 8110,
  "model-runtime-service": 8111,
  "observability-service": 8112,
  "config-service": 8113,
}
