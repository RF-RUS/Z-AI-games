"""Preview frame_kind contract invariants."""

import pytest
from fastapi.testclient import TestClient
from uno_adapter_windows.api import app
from uno_adapter_windows.mock_adapter import MockWindowsAdapter
from uno_schemas.adapter_windows import (
  AttachWindowsAdapterRequest,
  PreviewFrameKind,
  WindowsAdapterMode,
)


@pytest.mark.asyncio
async def test_mock_preview_frame_kind_is_synthetic_not_live():
  adapter = MockWindowsAdapter("contract-sess")
  adapter.bind_adapter_id("contract-aid")
  await adapter.attach()
  preview = adapter.get_preview_state()
  assert preview.frame_kind == PreviewFrameKind.SYNTHETIC
  assert preview.frame_kind != PreviewFrameKind.LIVE
  assert preview.live_frame is not None
  assert preview.live_frame.data_base64


@pytest.mark.contract
def test_mock_attach_preview_frame_kind_contract():
  client = TestClient(app)
  resp = client.post(
    "/attach",
    json=AttachWindowsAdapterRequest(session_id="kind-contract", mode=WindowsAdapterMode.MOCK).model_dump(mode="json"),
  )
  aid = resp.json()["adapter_id"]
  preview = client.get(f"/adapters/{aid}/preview").json()
  assert preview["frame_kind"] == PreviewFrameKind.SYNTHETIC.value
  assert preview["frame_kind"] != PreviewFrameKind.LIVE.value
  assert preview["live_frame"] is not None
  client.post(f"/adapters/{aid}/detach")


def test_preview_frame_kind_enum_values_are_distinct():
  assert PreviewFrameKind.LIVE.value == "live"
  assert PreviewFrameKind.SYNTHETIC.value == "synthetic"
  assert PreviewFrameKind.NONE.value == "none"
  assert len({PreviewFrameKind.LIVE, PreviewFrameKind.SYNTHETIC, PreviewFrameKind.NONE}) == 3
