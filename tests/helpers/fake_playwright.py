"""Fake Playwright page for selector health tests."""

from __future__ import annotations


class FakeLocator:
  def __init__(self, count: int, visible: bool = True):
    self._count = count
    self._visible = visible

  async def count(self) -> int:
    return self._count

  def nth(self, i: int) -> FakeLocator:
    return self

  async def is_visible(self) -> bool:
    return self._visible and self._count > 0


class FakePage:
  def __init__(self, hits: dict[str, int], title: str = "mock"):
    self._hits = hits
    self._title = title

  def locator(self, selector: str) -> FakeLocator:
    return FakeLocator(self._hits.get(selector, 0))

  async def title(self) -> str:
    return self._title

  async def evaluate(self, script: str) -> str:
    return "app:1:mock|player-hand:5:hand|deck:1:deck|playedCards:1:played"

  async def screenshot(self, **kwargs) -> None:
    path = kwargs.get("path")
    if path:
      open(path, "wb").close()
