"""HTTP client helpers for inter-service calls."""

from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


async def post_json(  # noqa: UP047 - keep TypeVar form for Python 3.11 compatibility
  client: httpx.AsyncClient,
  url: str,
  body: BaseModel,
  response_model: type[T],
  correlation_id: str | None = None,
) -> T:
  headers = {}
  if correlation_id:
    headers["X-Correlation-ID"] = correlation_id
  resp = await client.post(url, json=body.model_dump(mode="json"), headers=headers, timeout=30.0)
  resp.raise_for_status()
  return response_model.model_validate(resp.json())


async def get_json(client: httpx.AsyncClient, url: str, response_model: type[T]) -> T:  # noqa: UP047 - keep TypeVar form for Python 3.11 compatibility
  resp = await client.get(url, timeout=10.0)
  resp.raise_for_status()
  return response_model.model_validate(resp.json())
