"""Pywinauto launch and window discovery tests."""

from pathlib import Path
from unittest.mock import patch

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.runtime import launch_test_target


def test_launch_test_target_resolves_adapter_windows_script():
  profile = load_profile("local-mock-uno")
  expected = Path(__file__).resolve().parents[2] / "services" / "adapter-windows" / profile.test_target_script
  proc = launch_test_target(profile)
  try:
    assert proc is not None
    assert expected.exists()
  finally:
    if proc:
      proc.terminate()
      proc.wait(timeout=5)


@pytest.mark.asyncio
async def test_find_window_polls_until_target_appears():
  from uno_adapter_windows.runtime import find_window

  profile = load_profile("local-mock-uno")
  profile.readiness_timeout_ms = 2000
  calls = {"n": 0}

  async def fake_find(profile, backend, title_hint):
    calls["n"] += 1
    if calls["n"] < 3:
      return None
    return object()

  with patch("uno_adapter_windows.runtime._find_with_backend", side_effect=fake_find):
    win, backend = await find_window(profile)
  assert win is not None
  assert calls["n"] >= 3


@pytest.mark.asyncio
@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
async def test_pywinauto_attach_with_launch_test_target():
  from fastapi.testclient import TestClient
  from uno_adapter_windows.api import app
  from uno_schemas.adapter_windows import (
    AttachWindowsAdapterRequest,
    PreviewFrameKind,
    WindowsAdapterMode,
  )

  client = TestClient(app)
  resp = client.post(
    "/attach",
    json=AttachWindowsAdapterRequest(
      session_id="launch-contract",
      mode=WindowsAdapterMode.PYWINAUTO,
      profile_id="local-mock-uno",
      launch_test_target=True,
    ).model_dump(mode="json"),
  )
  data = resp.json()
  try:
    if not data["attached"]:
      pytest.skip(f"pywinauto attach unavailable in this environment: {data.get('message')}")
    assert data["backend"] in ("uia", "win32")
    assert data["mode"] == WindowsAdapterMode.PYWINAUTO.value
    preview = client.get(f"/adapters/{data['adapter_id']}/preview").json()
    assert preview["frame_kind"] == PreviewFrameKind.LIVE.value
    assert preview["attachment"]["backend"] != "mock"
  finally:
    if data.get("adapter_id"):
      client.post(f"/adapters/{data['adapter_id']}/detach")


@pytest.mark.asyncio
@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
async def test_pywinauto_evidence_after_live_attach():
  from fastapi.testclient import TestClient
  from uno_adapter_windows.api import app
  from uno_schemas.adapter_windows import (
    AttachWindowsAdapterRequest,
    WindowsAdapterMode,
    WindowsEvidenceBundle,
  )

  client = TestClient(app)
  attach = client.post(
    "/attach",
    json=AttachWindowsAdapterRequest(
      session_id="evidence-contract",
      mode=WindowsAdapterMode.PYWINAUTO,
      profile_id="local-mock-uno",
      launch_test_target=True,
    ).model_dump(mode="json"),
  )
  data = attach.json()
  aid = data["adapter_id"]
  try:
    if not data["attached"]:
      pytest.skip(f"pywinauto attach unavailable: {data.get('message')}")
    ev = client.get(f"/adapters/{aid}/evidence", params={"correlation_id": "observe-cid"})
    assert ev.status_code == 200, ev.text
    bundle = WindowsEvidenceBundle.model_validate(ev.json())
    assert bundle.ui_evidence.confidence > 0
    assert bundle.window_snapshot.window_title
    if bundle.screenshot:
      assert bundle.screenshot.width > 0
      assert bundle.screenshot.height > 0
  finally:
    client.post(f"/adapters/{aid}/detach")


@pytest.mark.asyncio
@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
async def test_orchestrator_windows_attach_launch_retry_real():
  import asyncio
  import subprocess

  import httpx
  from uno_orchestrator.orchestrator import SessionOrchestrator
  from uno_schemas.orchestrator import AttachAdapterBody, RecoveryConfig, SessionSpec
  from uno_schemas.session import AdapterType, SessionConfig

  subprocess.run(
    [
      "powershell",
      "-NoProfile",
      "-Command",
      "Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*UNO Mock*' } | Stop-Process -Force",
    ],
    check=False,
  )
  await asyncio.sleep(0.5)

  orch = SessionOrchestrator()
  spec = SessionSpec(
    config=SessionConfig(adapter_type=AdapterType.WINDOWS, adapter_id="pending"),
    windows_profile_id="local-mock-uno",
    recovery=RecoveryConfig(max_retries=0),
  )
  detail = await orch.create_session_with_game(spec)
  detail = await orch.attach_adapter(
    detail.session_id,
    AttachAdapterBody(
      adapter_type=AdapterType.WINDOWS,
      profile_id="local-mock-uno",
      windows_use_pywinauto=True,
      launch_test_target=False,
    ),
  )
  aid = detail.adapter_bindings[0].adapter_id
  try:
    assert detail.metrics.fallbacks == 0
    preview = httpx.get(f"http://127.0.0.1:8105/adapters/{aid}/preview", timeout=10).json()
    assert preview["attachment"]["backend"] == "uia"
    assert preview["frame_kind"] == "live"
  finally:
    httpx.post(f"http://127.0.0.1:8105/adapters/{aid}/detach", timeout=10)
