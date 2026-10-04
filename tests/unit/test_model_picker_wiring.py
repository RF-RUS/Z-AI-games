"""Regression: operator model picker — per-session VLM profile switching.

The operator UI switches a session's vision model live (3b↔7b↔any Ollama model).
The wiring under test:

  UI ──POST /sessions/{id}/model──▶ orchestrator.detail.vlm_profile_id
      ──clients.perceive(vlm_profile_id=…)──▶ perception /perceive
      ──infer_vision(profile_id=effective)──▶ model-runtime /invoke
      ──_load_profile("ollama:<name>")──▶ synthesized ModelProfile ──▶ Ollama

Plus the two picker endpoints on model-runtime: GET /profiles (vision profiles
on disk) and GET /ollama/models (live Ollama inventory).
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from uno_schemas.model import ModelProviderType
from uno_schemas.perception import ScreenshotFrame, VisionInference


# ── model-runtime: picker endpoints + dynamic profile synthesis ──────────────

def test_list_profiles_returns_vision_profiles():
  from uno_model_runtime.api import app
  client = TestClient(app)
  resp = client.get("/profiles")
  assert resp.status_code == 200
  ids = [p["profile_id"] for p in resp.json()]
  assert "local/ollama-vlm" in ids
  assert "local/ollama-vlm-7b" in ids
  # Only perception-capable profiles are offered.
  assert "mock/uno-assistant" not in ids


def test_list_ollama_models_reachable_false_is_graceful():
  from uno_model_runtime import api as mra
  import httpx

  async def _no_network(*a, **k):
    raise httpx.ConnectError("no ollama in test")

  with patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=_no_network)):
    resp = TestClient(mra.app).get("/ollama/models")
  assert resp.status_code == 200
  data = resp.json()
  assert data["reachable"] is False
  assert data["models"] == []


def test_synthesized_ollama_profile_from_live_name():
  from uno_model_runtime import api as mra

  mra._profile_cache.pop("ollama:qwen2.5vl:7b", None)
  p = mra._load_profile("ollama:qwen2.5vl:7b")
  assert p.provider == ModelProviderType.OLLAMA_OPENAI
  assert p.model_name == "qwen2.5vl:7b"
  assert p.enabled is True
  assert p.supports_multimodal is True  # 'vl' in the family name
  assert p.base_url.endswith("/v1")
  assert "/v1/v1" not in p.base_url  # ref profile base already carries the suffix

  # A non-vision model name is synthesized as text-only.
  mra._profile_cache.pop("ollama:gemma3:4b", None)
  p2 = mra._load_profile("ollama:gemma3:4b")
  assert p2.supports_multimodal is False


# ── orchestrator: POST /sessions/{id}/model persists on the session ──────────

def test_session_model_endpoint_sets_and_surfaces_profile():
  from uno_orchestrator.api import app, orchestrator

  client = TestClient(app)
  spec = {
    "config": {
      "adapter_type": "windows",
      "adapter_id": "pending",
      "strategy_id": "heuristic",
    },
    "automatic": True,
    "windows_profile_id": "real-uno-desktop",
  }
  created = client.post("/sessions", json=spec).json()
  sid = created["session_id"]
  try:
    assert created["vlm_profile_id"] is None  # default: perception env profile

    resp = client.post(f"/sessions/{sid}/model", json={"vlm_profile_id": "local/ollama-vlm-7b"})
    assert resp.status_code == 200
    assert resp.json()["vlm_profile_id"] == "local/ollama-vlm-7b"

    # GET surfaces it too (the UI polls the session).
    assert client.get(f"/sessions/{sid}").json()["vlm_profile_id"] == "local/ollama-vlm-7b"

    # Clearing falls back to the service default.
    resp = client.post(f"/sessions/{sid}/model", json={})
    assert resp.json()["vlm_profile_id"] is None
  finally:
    orchestrator._sessions.pop(sid, None)


def test_attach_adapter_body_captures_vlm_profile():
  from uno_orchestrator.api import orchestrator
  from uno_schemas.orchestrator import AttachAdapterBody

  body = AttachAdapterBody(adapter_type="windows", profile_id="p", vlm_profile_id="local/ollama-vlm-7b")
  assert body.vlm_profile_id == "local/ollama-vlm-7b"


@pytest.mark.asyncio
async def test_set_vlm_profile_triggers_forced_reperceive():
  """Switching a session's model must re-analyze the CURRENT frame right away
  (operator complaint: "after switching the AI the board is not re-read").

  The re-perceive runs in the background, with force_vlm=True so the
  static-frame gate in perception cannot replay the old model's board, and the
  fresh observation lands in session.latest_observation (what the UI polls).
  """
  import asyncio

  from uno_orchestrator.api import orchestrator
  from uno_orchestrator.flow_controller import RuntimeSession
  from uno_schemas.orchestrator import AdapterBinding, SessionDetail, SessionSpec

  detail = SessionDetail(
    session_id="mp-set",
    flow_state="idle",
    phase="idle",
    correlation_id="corr-mp-set",
    automatic=False,
    config={
      "adapter_type": "windows",
      "adapter_id": "ad-x",
      "strategy_id": "heuristic",
    },
    adapter_bindings=[AdapterBinding(adapter_type="windows", adapter_id="ad-x", attached=True)],
    metrics={},
  )
  spec = SessionSpec(config=detail.config)
  session = RuntimeSession(detail=detail, spec=spec)
  orchestrator._sessions["mp-set"] = session

  fake_obs = object.__new__(type("O", (), {"game_state": {"vlm_status": "forced"}}))

  async def _fake_perceive(session_id, dom=None, ui=None, screenshot=None,
                           vlm_profile_id=None, force_vlm=False):
    assert session_id == "mp-set"
    assert screenshot is not None, "the fresh capture must reach perception"
    assert vlm_profile_id == "local/ollama-vlm-7b"
    assert force_vlm is True, "a model switch must bypass the static-frame gate"
    return fake_obs

  class _Shot:
    pass

  async def _fake_observe(binding, cid):
    return None, None, 0.5, _Shot()

  with (
    patch.object(orchestrator._flow, "_observe", new=_fake_observe),
    patch.object(orchestrator._clients, "perceive", new=_fake_perceive),
  ):
    out = orchestrator.set_vlm_profile("mp-set", "local/ollama-vlm-7b")
    # /model returns immediately; the re-perceive is a fire-and-forget task.
    assert out.vlm_profile_id == "local/ollama-vlm-7b"
    assert "mp-set" in orchestrator._reperceive_inflight
    deadline = asyncio.get_event_loop().time() + 5
    while "mp-set" in orchestrator._reperceive_inflight and asyncio.get_event_loop().time() < deadline:
      await asyncio.sleep(0.01)

  assert session.latest_observation is fake_obs


def test_set_vlm_profile_unknown_session_404():
  from uno_orchestrator.api import app
  resp = TestClient(app).post("/sessions/nope/model", json={"vlm_profile_id": "x"})
  assert resp.status_code == 404


# ── clients.perceive passes the profile in the HTTP body ─────────────────────

@pytest.mark.asyncio
async def test_clients_perceive_sends_vlm_profile_id():
  from uno_orchestrator.clients import ServiceClients

  clients = ServiceClients()
  captured: dict = {}

  class _FakeResp:
    def raise_for_status(self):
      pass

    def json(self):
      return {
        "observation_id": "obs-1",
        "session_id": "s1",
        "timestamp_ms": 1,
        "confidence": {"overall": 0.5, "game_state": 0.5},
      }

  class _FakeClient:
    def __init__(self, *a, **k):
      pass

    async def __aenter__(self):
      return self

    async def __aexit__(self, *a):
      return False

    async def post(self, url, json=None, headers=None):
      captured["url"] = url
      captured["json"] = json
      return _FakeResp()

  with patch("uno_orchestrator.clients.httpx.AsyncClient", _FakeClient):
    await clients.perceive("s1", vlm_profile_id="local/ollama-vlm-7b")
  assert "vlm_profile_id" in captured["json"]
  assert captured["json"]["vlm_profile_id"] == "local/ollama-vlm-7b"

  # No profile → key absent (perception uses its env default).
  captured.clear()
  with patch("uno_orchestrator.clients.httpx.AsyncClient", _FakeClient):
    await clients.perceive("s1")
  assert "vlm_profile_id" not in captured["json"]


# ── perception: /perceive routes the profile to infer_vision ─────────────────

def _shot(session_id: str) -> dict:
  return ScreenshotFrame(
    frame_id="f1", session_id=session_id, width=320, height=240,
    path="/nonexistent-in-test.png", captured_at_ms=1,
  ).model_dump(mode="json")


def test_perceive_passes_session_profile_to_vlm_and_scopes_cache_by_it():
  from uno_perception import api as papi

  vi = VisionInference(model_id="test", raw_output="{}", structured={})
  calls: list[str] = []

  async def _fake_infer(shot_path, game_type="uno", profile_id=None):
    calls.append(profile_id or papi.VLM_PROFILE_ID)
    return vi, "ok"

  client = TestClient(papi.app)
  with (
    patch.object(papi, "vlm_enabled", return_value=True),
    patch.object(papi, "infer_vision", new=_fake_infer),
  ):
    r1 = client.post("/perceive", json={
      "session_id": "mp-1", "screenshot": _shot("mp-1"), "vlm_profile_id": "local/ollama-vlm",
    })
    assert r1.status_code == 200
    r2 = client.post("/perceive", json={
      "session_id": "mp-1", "screenshot": _shot("mp-1"), "vlm_profile_id": "local/ollama-vlm-7b",
    })
    assert r2.status_code == 200

  # Each profile got its OWN call — the static-frame cache must not replay a
  # board produced by the other model after a mid-session switch.
  assert calls == ["local/ollama-vlm", "local/ollama-vlm-7b"]
