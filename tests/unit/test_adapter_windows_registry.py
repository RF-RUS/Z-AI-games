"""Registry attach error contract tests."""

import pytest
from uno_adapter_windows.registry import attach_adapter
from uno_schemas.adapter_windows import AttachWindowsAdapterRequest, WindowsAdapterMode


@pytest.mark.asyncio
async def test_attach_exception_returns_valid_adapter_id(monkeypatch):
  async def boom(_req):
    raise RuntimeError("simulated attach crash")

  monkeypatch.setattr(
    "uno_adapter_windows.registry.MockWindowsAdapter.attach",
    boom,
  )
  resp = await attach_adapter(
    AttachWindowsAdapterRequest(session_id="err", mode=WindowsAdapterMode.MOCK, profile_id="local-mock-uno")
  )
  assert resp.attached is False
  assert resp.adapter_id
  assert resp.message == "simulated attach crash"
