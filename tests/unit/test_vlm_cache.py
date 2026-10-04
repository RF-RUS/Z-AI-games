"""VLM perception cache tests — identical frames must not pay model latency twice."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_perception import vlm_provider


def _fake_runtime_result(board: dict) -> tuple[MagicMock, MagicMock]:
  resp = MagicMock()
  resp.raise_for_status = MagicMock()
  resp.json.return_value = {
    "text": "",
    "structured": {"parsed": board},
    "profile_id": "mock/vision",
    "fallback_used": False,
  }
  client = AsyncMock()
  client.post = AsyncMock(return_value=resp)
  ctx = MagicMock()
  ctx.__aenter__ = AsyncMock(return_value=client)
  ctx.__aexit__ = AsyncMock(return_value=False)
  return client, ctx


BOARD = {
  "screen_state": "in_game",
  "whose_turn": "self",
  "top_card": {"color": "red", "value": "5"},
  "hand_cards": [{"color": "red", "value": "5"}],
  "prompts": [],
  "confidence": 0.9,
}


@pytest.mark.asyncio
async def test_second_identical_frame_is_cache_hit(tmp_path):
  vlm_provider.reset_vlm_cache()
  img = tmp_path / "frame.png"
  img.write_bytes(b"\x89PNG fake-bytes-123")

  client, ctx = _fake_runtime_result(BOARD)
  with patch("httpx.AsyncClient", return_value=ctx):
    inference, status = await vlm_provider.infer_vision(str(img), game_type="uno")
    assert status == "ok"
    assert inference is not None
    calls_after_first = client.post.await_count

    inference2, status2 = await vlm_provider.infer_vision(str(img), game_type="uno")
    assert status2 == "cache_hit"
    assert inference2 is not None
    assert inference2.structured == inference.structured
    # No extra model call for the identical frame.
    assert client.post.await_count == calls_after_first


@pytest.mark.asyncio
async def test_different_image_misses_cache(tmp_path):
  vlm_provider.reset_vlm_cache()
  frame_a = tmp_path / "a.png"
  frame_b = tmp_path / "b.png"
  frame_a.write_bytes(b"image-a")
  frame_b.write_bytes(b"image-b")

  client, ctx = _fake_runtime_result(BOARD)
  with patch("httpx.AsyncClient", return_value=ctx):
    await vlm_provider.infer_vision(str(frame_a), game_type="uno")
    await vlm_provider.infer_vision(str(frame_b), game_type="uno")
    # Two distinct frames → two real model calls (no false cache hit).
    assert client.post.await_count == 2


@pytest.mark.asyncio
async def test_cache_reset_clears_entries(tmp_path):
  vlm_provider.reset_vlm_cache()
  img = tmp_path / "f.png"
  img.write_bytes(b"bytes")
  _, ctx = _fake_runtime_result(BOARD)
  with patch("httpx.AsyncClient", return_value=ctx):
    await vlm_provider.infer_vision(str(img), game_type="uno")
  vlm_provider.reset_vlm_cache()
  assert len(vlm_provider._vlm_cache) == 0
  with patch("httpx.AsyncClient", return_value=ctx):
    _, status = await vlm_provider.infer_vision(str(img), game_type="uno")
  assert status == "ok"


@pytest.mark.asyncio
async def test_cache_disabled_by_env(monkeypatch, tmp_path):
  monkeypatch.setenv("VLM_CACHE_ENABLED", "0")
  importlib_reload = __import__("importlib").reload
  importlib_reload(vlm_provider)
  try:
    img = tmp_path / "g.png"
    img.write_bytes(b"gbytes")
    _, ctx = _fake_runtime_result(BOARD)
    with patch("httpx.AsyncClient", return_value=ctx):
      _, s1 = await vlm_provider.infer_vision(str(img))
      _, s2 = await vlm_provider.infer_vision(str(img))
    assert s1 == "ok" and s2 == "ok"
  finally:
    import os
    os.environ.pop("VLM_CACHE_ENABLED", None)
    importlib_reload(vlm_provider)
