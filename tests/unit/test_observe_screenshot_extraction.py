"""Regression: the flow controller must surface the adapter screenshot.

GenericEvidenceBundle carries the screenshot as `.screenshot_path` (+ the raw
dict in `.extra`), NOT a `.screenshot` attribute. The old _observe looked for the
non-existent attribute, so the screenshot never reached perception on real
windows/web sessions → screenshot CV never ran → every frame was classified
"not_in_game" and the agent never played. This guards the fix.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_orchestrator.clients import binding_for
from uno_orchestrator.flow_controller import FlowController
from uno_schemas.session import AdapterType
from uno_shared.adapter_protocol import GenericEvidenceBundle


def _bundle(**kw) -> GenericEvidenceBundle:
  return GenericEvidenceBundle(
    adapter_id="win-1", session_id="s",
    ui_evidence={"confidence": 0.4, "element_tree": {}},
    **kw,
  )


@pytest.mark.asyncio
async def test_observe_reconstructs_screenshot_from_extra():
  frame = {
    "frame_id": "f1", "session_id": "s", "width": 1296, "height": 759,
    "path": "/tmp/shot.png", "captured_at_ms": 1, "format": "png",
  }
  bundle = _bundle(screenshot_path="/tmp/shot.png", extra={"screenshot": frame})

  client = MagicMock()
  client.capture_evidence = AsyncMock(return_value=bundle)
  registry = MagicMock()
  registry.get_client = MagicMock(return_value=client)

  fc = FlowController(clients=MagicMock())
  binding = binding_for(AdapterType.WINDOWS, "win-1", "real-uno-desktop")
  with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
    _dom, _ui, _conf, screenshot = await fc._observe(binding, "cid")

  assert screenshot is not None
  assert screenshot.path == "/tmp/shot.png"
  assert screenshot.width == 1296 and screenshot.height == 759


@pytest.mark.asyncio
async def test_observe_falls_back_to_screenshot_path(tmp_path):
  # No structured dict in extra — only a path. Must still build a frame.
  from PIL import Image
  shot = tmp_path / "s.png"
  Image.new("RGB", (320, 240), (10, 10, 10)).save(shot)

  bundle = _bundle(screenshot_path=str(shot), extra={})
  client = MagicMock()
  client.capture_evidence = AsyncMock(return_value=bundle)
  registry = MagicMock()
  registry.get_client = MagicMock(return_value=client)

  fc = FlowController(clients=MagicMock())
  binding = binding_for(AdapterType.WINDOWS, "win-1", "real-uno-desktop")
  with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
    _dom, _ui, _conf, screenshot = await fc._observe(binding, "cid")

  assert screenshot is not None
  assert screenshot.path == str(shot)
  assert screenshot.width == 320 and screenshot.height == 240


@pytest.mark.asyncio
async def test_observe_no_screenshot_is_none():
  bundle = _bundle()  # no screenshot at all
  client = MagicMock()
  client.capture_evidence = AsyncMock(return_value=bundle)
  registry = MagicMock()
  registry.get_client = MagicMock(return_value=client)

  fc = FlowController(clients=MagicMock())
  binding = binding_for(AdapterType.WINDOWS, "win-1", "real-uno-desktop")
  with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
    _dom, _ui, _conf, screenshot = await fc._observe(binding, "cid")

  assert screenshot is None
  _ = time  # keep import used across variants
