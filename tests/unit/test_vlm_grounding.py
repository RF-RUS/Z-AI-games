"""Tests for the action-grounding layer (VLM grounding provider + resolver).

Verifiable without a real vision model or a Windows host: (1) resolve_grounding
tries providers cheapest-first and the first confident hit wins; (2) the VLM
provider maps a model-runtime /invoke result into a GroundingResult hit/miss,
gated on VLM_PERCEPTION; (3) the cheap perceived-prompt path picks the right
colour button. The real model is swapped in later via config (VLM_PERCEPTION=1 +
a vision profile); this pins the wiring around it.
"""

from __future__ import annotations

import asyncio

from uno_orchestrator.perceived_actions import choose_prompt
from uno_perception import grounding_providers as gp
from uno_perception.grounding import GroundingRequest, GroundingResult, resolve_grounding

# --- resolve_grounding: cheapest-first, first confident hit wins ------------

class _Fake:
    def __init__(self, method: str, res: GroundingResult) -> None:
        self.method = method
        self._res = res

    async def ground(self, req):
        return self._res


def _req() -> GroundingRequest:
    return GroundingRequest("choose_color", "/tmp/x.png", {"color": "red"}, "uno")


def test_first_confident_hit_wins():
    miss = _Fake("uia", GroundingResult.miss("uia", "empty tree"))
    hit = _Fake("vlm", GroundingResult.hit(10, 20, 0.9, "vlm"))
    out = asyncio.run(resolve_grounding(_req(), [miss, hit]))
    assert out.found and out.method == "vlm" and (out.x, out.y) == (10, 20)


def test_low_confidence_hit_is_skipped():
    weak = _Fake("vlm", GroundingResult.hit(1, 2, 0.3, "vlm"))
    out = asyncio.run(resolve_grounding(_req(), [weak], min_confidence=0.5))
    assert not out.found  # last (weak) result returned, but found stays gated by caller


def test_broken_provider_does_not_block_fallback():
    class _Boom:
        method = "uia"
        async def ground(self, req):
            raise RuntimeError("provider crashed")

    hit = _Fake("vlm", GroundingResult.hit(5, 6, 0.8, "vlm"))
    out = asyncio.run(resolve_grounding(_req(), [_Boom(), hit]))
    assert out.found and out.method == "vlm"


# --- VLMGroundingProvider: /invoke result → GroundingResult -----------------

def test_vlm_provider_disabled_misses(monkeypatch):
    monkeypatch.setattr(gp, "vlm_enabled", lambda: False)
    out = asyncio.run(gp.VLMGroundingProvider().ground(_req()))
    assert not out.found and out.reason.startswith("vlm disabled")


def test_vlm_provider_parses_hit(monkeypatch):
    monkeypatch.setattr(gp, "vlm_enabled", lambda: True)
    monkeypatch.setattr(gp, "_read_image_base64", lambda p: "ZmFrZQ==")

    async def _fake_post(self, url, json):  # noqa: A002 — httpx uses `json` kwarg
        class _R:
            def raise_for_status(self): pass
            def json(self):
                return {"structured": {"found": True, "x": 42, "y": 99, "confidence": 0.8}}
        return _R()

    monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)
    out = asyncio.run(gp.VLMGroundingProvider().ground(_req()))
    assert out.found and (out.x, out.y) == (42.0, 99.0) and out.method == "vlm"


def test_vlm_provider_mock_fallback_is_miss(monkeypatch):
    monkeypatch.setattr(gp, "vlm_enabled", lambda: True)
    monkeypatch.setattr(gp, "_read_image_base64", lambda p: "ZmFrZQ==")

    async def _fake_post(self, url, json):
        class _R:
            def raise_for_status(self): pass
            def json(self):
                return {"fallback_used": True, "structured": {"found": True, "x": 1, "y": 2}}
        return _R()

    monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)
    out = asyncio.run(gp.VLMGroundingProvider().ground(_req()))
    assert not out.found and out.reason == "mock_fallback"


def test_vlm_provider_not_found_is_miss(monkeypatch):
    monkeypatch.setattr(gp, "vlm_enabled", lambda: True)
    monkeypatch.setattr(gp, "_read_image_base64", lambda p: "ZmFrZQ==")

    async def _fake_post(self, url, json):
        class _R:
            def raise_for_status(self): pass
            def json(self):
                return {"structured": {"found": False, "confidence": 0.0}}
        return _R()

    monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)
    out = asyncio.run(gp.VLMGroundingProvider().ground(_req()))
    assert not out.found and out.reason == "not_found"


# --- cheap path: perceived prompts pick the right colour button ------------

def test_choose_prompt_matches_colour_button():
    prompts = [
        {"label": "red", "center": {"x": 100, "y": 200}},
        {"label": "blue", "center": {"x": 300, "y": 200}},
    ]
    picked = choose_prompt(prompts, prefer_color="blue")
    assert picked and picked["center"] == {"x": 300, "y": 200}
