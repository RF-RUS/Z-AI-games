from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from uno_adapter_web.mock_adapter import MockWebAdapter
from uno_adapter_web.playwright_adapter import PlaywrightWebAdapter
from uno_adapter_web.profiles import load_profile
from uno_adapter_web.runtime import playwright_available
from uno_adapter_web.startup import format_startup_error
from uno_schemas.adapter_web import (
  ActionExecutionRequest,
  ActionExecutionResult,
  AdapterEvidenceBundle,
  AdapterMode,
  AttachWebAdapterRequest,
  AttachWebAdapterResponse,
)


class WebAdapterSession(Protocol):
  session_id: str
  profile_id: str
  url: str
  mode: AdapterMode

  async def attach(self) -> bool: ...
  async def read_dom(self) -> dict: ...
  async def capture_evidence(self, adapter_id: str) -> AdapterEvidenceBundle: ...
  async def execute(self, req: ActionExecutionRequest, correlation_id: str | None) -> ActionExecutionResult: ...
  async def detach(self) -> None: ...


_adapters: dict[str, WebAdapterSession] = {}


def create_adapter(req: AttachWebAdapterRequest) -> tuple[str, WebAdapterSession]:
  profile = load_profile(req.profile_id)
  url = req.url or profile.launch_url

  if req.mode == AdapterMode.MOCK:
    adapter: WebAdapterSession = MockWebAdapter(req.session_id, req.profile_id, url)
  else:
    if not playwright_available():
      raise RuntimeError("Playwright not installed. Run: playwright install chromium")
    adapter = PlaywrightWebAdapter(
      req.session_id, profile, url=url, headless=req.headless, record_trace=req.record_trace,
      cdp_url=req.cdp_url,
    )

  aid = str(uuid4())
  _adapters[aid] = adapter
  return aid, adapter


def get_adapter(adapter_id: str) -> WebAdapterSession | None:
  return _adapters.get(adapter_id)


async def _discard_failed_adapter(aid: str | None, adapter: WebAdapterSession | None) -> None:
  if not aid:
    return
  _adapters.pop(aid, None)
  if adapter:
    try:
      await adapter.detach()
    except Exception:
      pass


async def attach_adapter(req: AttachWebAdapterRequest) -> AttachWebAdapterResponse:
  profile = load_profile(req.profile_id)
  url = req.url or profile.launch_url
  adapter: WebAdapterSession | None = None
  aid: str | None = None
  try:
    aid, adapter = create_adapter(req)
    ok = await adapter.attach()
    if not ok:
      diagnostics = getattr(adapter, "startup_diagnostics", None)
      await _discard_failed_adapter(aid, adapter)
      return AttachWebAdapterResponse(
        adapter_id=None,
        session_id=req.session_id,
        attached=False,
        mode=req.mode,
        profile_id=req.profile_id,
        url=url,
        message="attach failed",
        startup_diagnostics=diagnostics,
      )
    diagnostics = getattr(adapter, "startup_diagnostics", None)
    return AttachWebAdapterResponse(
      adapter_id=aid,
      session_id=req.session_id,
      attached=True,
      mode=req.mode,
      profile_id=req.profile_id,
      url=url,
      message="attached",
      startup_diagnostics=diagnostics,
    )
  except Exception as exc:
    diagnostics = getattr(adapter, "startup_diagnostics", None) if adapter else None
    await _discard_failed_adapter(aid, adapter)
    return AttachWebAdapterResponse(
      adapter_id=None,
      session_id=req.session_id,
      attached=False,
      mode=req.mode,
      profile_id=req.profile_id,
      url=url,
      message=format_startup_error(exc),
      startup_diagnostics=diagnostics,
    )
