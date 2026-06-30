"""Playwright-backed web adapter session wrapper."""

from __future__ import annotations

from uno_adapter_web.runtime import PlaywrightSession
from uno_schemas.adapter_web import (
  ActionExecutionRequest,
  ActionExecutionResult,
  AdapterEvidenceBundle,
  AdapterMode,
  WebAdapterProfile,
)


class PlaywrightWebAdapter:
  def __init__(
    self,
    session_id: str,
    profile: WebAdapterProfile,
    url: str | None = None,
    headless: bool = True,
    record_trace: bool = False,
    cdp_url: str | None = None,
  ) -> None:
    self.session_id = session_id
    self.profile_id = profile.profile_id
    self.url = url or profile.launch_url
    self._session = PlaywrightSession(
      session_id, profile, url=self.url, headless=headless, record_trace=record_trace, cdp_url=cdp_url
    )

  async def attach(self) -> bool:
    return await self._session.attach()

  async def read_dom(self) -> dict:
    return await self._session.read_dom_dict()

  async def capture_evidence(self, adapter_id: str) -> AdapterEvidenceBundle:
    _, bundle, _ = await self._session.capture_evidence()
    bundle.adapter_id = adapter_id
    return bundle

  async def execute(self, req: ActionExecutionRequest, correlation_id: str | None = None) -> ActionExecutionResult:
    return await self._session.execute(req, correlation_id)

  async def detach(self) -> None:
    await self._session.detach()

  @property
  def mode(self) -> AdapterMode:
    return AdapterMode.PLAYWRIGHT

  @property
  def trace_path(self) -> str | None:
    return self._session._trace_path

  @property
  def startup_diagnostics(self):
    return self._session.startup_diagnostics
