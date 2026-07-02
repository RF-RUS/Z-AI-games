"""Python client SDK for UNO Operator services."""

from __future__ import annotations

import httpx
from uno_schemas.api import SERVICE_PORTS, HealthResponse
from uno_schemas.decision import DecisionRequest, DecisionResult
from uno_schemas.game import LegalAction
from uno_schemas.model import ModelManifest


class UnoCoreClient:
  def __init__(self, base_url: str | None = None) -> None:
    self.base_url = base_url or f"http://127.0.0.1:{SERVICE_PORTS['uno-core']}"

  async def health(self) -> HealthResponse:
    async with httpx.AsyncClient() as client:
      r = await client.get(f"{self.base_url}/health")
      return HealthResponse.model_validate(r.json())

  async def create_game(self, player_names: list[str], seed: int | None = None) -> dict:
    async with httpx.AsyncClient() as client:
      r = await client.post(f"{self.base_url}/games", json={"player_names": player_names, "seed": seed})
      r.raise_for_status()
      return r.json()

  async def legal_actions(self, game_id: str) -> list[LegalAction]:
    async with httpx.AsyncClient() as client:
      r = await client.get(f"{self.base_url}/games/{game_id}/legal-actions")
      r.raise_for_status()
      return [LegalAction.model_validate(a) for a in r.json()["actions"]]


class DecisionClient:
  def __init__(self, base_url: str | None = None) -> None:
    self.base_url = base_url or f"http://127.0.0.1:{SERVICE_PORTS['decision-service']}"

  async def decide(self, req: DecisionRequest) -> DecisionResult:
    async with httpx.AsyncClient() as client:
      r = await client.post(f"{self.base_url}/decide", json=req.model_dump(mode="json"))
      r.raise_for_status()
      return DecisionResult.model_validate(r.json())


class ModelRegistryClient:
  def __init__(self, base_url: str | None = None) -> None:
    self.base_url = base_url or f"http://127.0.0.1:{SERVICE_PORTS['model-registry-service']}"

  async def list_models(self) -> list[ModelManifest]:
    async with httpx.AsyncClient() as client:
      r = await client.get(f"{self.base_url}/models")
      return [ModelManifest.model_validate(m) for m in r.json()]
