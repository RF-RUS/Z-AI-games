"""In-process and pluggable event bus abstraction."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class BusEvent(BaseModel):
  event_type: str
  payload: dict[str, Any] = Field(default_factory=dict)
  correlation_id: str | None = None
  event_id: str = Field(default_factory=lambda: str(uuid4()))
  timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


EventHandler = Callable[[BusEvent], Awaitable[None] | None]


@dataclass
class InMemoryEventBus:
  """Append-only in-process event bus for local dev and tests."""

  _handlers: dict[str, list[EventHandler]] = field(default_factory=lambda: defaultdict(list))
  _history: list[BusEvent] = field(default_factory=list)
  _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

  def subscribe(self, event_type: str, handler: EventHandler) -> None:
    self._handlers[event_type].append(handler)
    self._handlers["*"].append(handler)

  async def publish(self, event: BusEvent) -> None:
    async with self._lock:
      self._history.append(event)
    handlers = list(self._handlers.get(event.event_type, [])) + list(self._handlers.get("*", []))
    for handler in handlers:
      result = handler(event)
      if asyncio.iscoroutine(result):
        await result

  def history(self, event_type: str | None = None) -> list[BusEvent]:
    if event_type is None:
      return list(self._history)
    return [e for e in self._history if e.event_type == event_type]

  def clear(self) -> None:
    self._history.clear()


# Global singleton for local orchestration
_bus: InMemoryEventBus | None = None


def get_event_bus() -> InMemoryEventBus:
  global _bus
  if _bus is None:
    _bus = InMemoryEventBus()
  return _bus
