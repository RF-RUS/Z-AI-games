"""Navigation diagnostics for page_goto failures."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from uno_adapter_web.navigation_diagnostics import (
  NavigationDiagnosticsCollector,
  check_url_reachability,
)


@pytest.mark.asyncio
async def test_check_url_reachability_reports_success(monkeypatch):
  class FakeResponse:
    status_code = 200
    url = "https://scuffeduno.online/"
    content = b"<html><title>Scuffed Uno</title></html>"

    @property
    def is_success(self):
      return True

  class FakeClient:
    async def __aenter__(self):
      return self

    async def __aexit__(self, *args):
      return False

    async def get(self, url, headers=None):
      return FakeResponse()

  monkeypatch.setattr("uno_adapter_web.navigation_diagnostics.httpx.AsyncClient", lambda **kwargs: FakeClient())
  result = await check_url_reachability("https://scuffeduno.online/")
  assert result.reachable is True
  assert result.status_code == 200


@pytest.mark.asyncio
async def test_navigation_collector_builds_page_snapshot():
  page = AsyncMock()
  page.url = "https://scuffeduno.online/loading"
  page.title.return_value = "Scuffed Uno"
  page.evaluate.side_effect = ["interactive", "<html>partial</html>", 1234]

  collector = NavigationDiagnosticsCollector(
    requested_url="https://scuffeduno.online/",
    wait_until="commit",
    browser_launch_mode="bundled_chromium",
  )
  collector.request_failures.append(
    __import__("uno_schemas.adapter_web", fromlist=["RequestFailureRecord"]).RequestFailureRecord(
      url="https://scuffeduno.online/app.js",
      failure="net::ERR_BLOCKED_BY_CLIENT",
      resource_type="script",
    )
  )
  snapshot = await collector.snapshot_page(page)
  built = collector.build(snapshot)

  assert built.final_url == "https://scuffeduno.online/loading"
  assert built.page_title == "Scuffed Uno"
  assert built.wait_until == "commit"
  assert built.request_failures[0].failure == "net::ERR_BLOCKED_BY_CLIENT"


def test_navigation_collector_records_console_and_response():
  collector = NavigationDiagnosticsCollector(
    requested_url="https://example.com",
    wait_until="commit",
    browser_launch_mode="channel:chrome",
  )
  page = MagicMock()

  handlers: dict[str, object] = {}

  def on(event, handler):
    handlers[event] = handler

  page.on = on
  collector.attach(page)

  handlers["response"](MagicMock(url="https://example.com/", status=200, ok=True))
  handlers["requestfailed"](MagicMock(url="https://example.com/x.js", failure="failed", resource_type="script"))
  handlers["console"](MagicMock(type="error", text="blocked by client"))

  built = collector.build({"final_url": "https://example.com/", "page_title": "Example"})
  assert built.navigation_responses[0].status == 200
  assert built.request_failures[0].url.endswith("x.js")
  assert built.console_errors[0].startswith("error:")
