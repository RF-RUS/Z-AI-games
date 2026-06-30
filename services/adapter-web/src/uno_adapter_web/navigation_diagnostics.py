"""Navigation diagnostics for Playwright page_goto failures."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from uno_schemas.adapter_web import (
  NavigationResponseRecord,
  NetworkReachabilityCheck,
  PageGotoDiagnostics,
  RequestFailureRecord,
)

_MAX_RESPONSES = 30
_MAX_FAILURES = 20
_MAX_CONSOLE = 20
_PREVIEW_CHARS = 2000


async def check_url_reachability(url: str, timeout: float = 20.0) -> NetworkReachabilityCheck:
  started = time.perf_counter()
  result = NetworkReachabilityCheck(url=url, reachable=False)
  try:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
      response = await client.get(
        url,
        headers={"User-Agent": "UNO-Operator-Reachability/1.0"},
      )
      result.status_code = response.status_code
      result.final_url = str(response.url)
      result.reachable = response.is_success
      result.content_length = len(response.content)
      if not response.is_success:
        result.error = f"HTTP {response.status_code}"
  except Exception as exc:
    result.error = str(exc)
  result.elapsed_ms = int((time.perf_counter() - started) * 1000)
  return result


class NavigationDiagnosticsCollector:
  def __init__(
    self,
    *,
    requested_url: str,
    wait_until: str,
    browser_launch_mode: str,
  ) -> None:
    self.requested_url = requested_url
    self.wait_until = wait_until
    self.browser_launch_mode = browser_launch_mode
    self.navigation_responses: list[NavigationResponseRecord] = []
    self.request_failures: list[RequestFailureRecord] = []
    self.console_errors: list[str] = []
    self.network_reachability: NetworkReachabilityCheck | None = None
    self._attached = False

  def attach(self, page: Any) -> None:
    if self._attached:
      return

    def on_response(response: Any) -> None:
      if len(self.navigation_responses) >= _MAX_RESPONSES:
        return
      try:
        self.navigation_responses.append(
          NavigationResponseRecord(
            url=response.url,
            status=response.status,
            ok=response.ok,
          )
        )
      except Exception:
        pass

    def on_request_failed(request: Any) -> None:
      if len(self.request_failures) >= _MAX_FAILURES:
        return
      failure = request.failure
      text = failure if isinstance(failure, str) else getattr(failure, "error_text", "") or str(failure or "")
      self.request_failures.append(
        RequestFailureRecord(
          url=request.url,
          failure=text,
          resource_type=getattr(request, "resource_type", "") or "",
        )
      )

    def on_console(msg: Any) -> None:
      if len(self.console_errors) >= _MAX_CONSOLE:
        return
      if msg.type in ("error", "warning"):
        self.console_errors.append(f"{msg.type}: {msg.text[:500]}")

    page.on("response", on_response)
    page.on("requestfailed", on_request_failed)
    page.on("console", on_console)
    self._attached = True

  async def probe_reachability(self) -> NetworkReachabilityCheck:
    self.network_reachability = await check_url_reachability(self.requested_url)
    return self.network_reachability

  async def snapshot_page(self, page: Any) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
      "final_url": None,
      "page_title": None,
      "document_ready_state": None,
      "content_preview": None,
      "content_length": None,
    }
    if not page:
      return snapshot
    try:
      snapshot["final_url"] = _as_str(page.url)
    except Exception:
      pass
    try:
      snapshot["page_title"] = _as_str(await page.title())
    except Exception:
      pass
    try:
      snapshot["document_ready_state"] = _as_str(await page.evaluate("document.readyState"))
    except Exception:
      pass
    try:
      preview = await page.evaluate(
        "() => (document.documentElement?.outerHTML || '').slice(0, 2000)"
      )
      length = await page.evaluate("() => (document.documentElement?.outerHTML || '').length")
      snapshot["content_preview"] = _sanitize_preview(_as_str(preview) or "")
      snapshot["content_length"] = _as_int(length)
    except Exception:
      pass
    return snapshot

  def build(self, page_snapshot: dict[str, Any] | None = None) -> PageGotoDiagnostics:
    snap = page_snapshot or {}
    return PageGotoDiagnostics(
      requested_url=self.requested_url,
      final_url=snap.get("final_url"),
      page_title=snap.get("page_title"),
      document_ready_state=snap.get("document_ready_state"),
      content_preview=snap.get("content_preview"),
      content_length=snap.get("content_length"),
      wait_until=self.wait_until,
      browser_launch_mode=self.browser_launch_mode,
      navigation_responses=list(self.navigation_responses),
      request_failures=list(self.request_failures),
      console_errors=list(self.console_errors),
      network_reachability=self.network_reachability,
    )


def _as_str(value: Any) -> str | None:
  if isinstance(value, str):
    return value
  return None


def _as_int(value: Any) -> int | None:
  try:
    return int(value)
  except (TypeError, ValueError):
    return None


def _sanitize_preview(text: str) -> str | None:
  cleaned = re.sub(r"\s+", " ", text).strip()
  if not cleaned:
    return None
  return cleaned[:_PREVIEW_CHARS]
