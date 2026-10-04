import os
import tempfile
import time

from fastapi import FastAPI
from pydantic import BaseModel
from uno_perception.frame_gate import FrameGate
from uno_perception.grounding import GroundingRequest, resolve_grounding
from uno_perception.grounding_providers import default_providers
from uno_perception.merger import build_observation, merge_confidence, register_game_adapter
from uno_perception.uno_adapter import UnuPerceptionAdapter
from uno_perception.vlm_provider import (
  MODEL_RUNTIME_URL,
  VLM_PROFILE_ID,
  VLM_TIMEOUT_S,
  infer_vision,
  vlm_enabled,
)
from uno_schemas.perception import (
  DomEvidence,
  Observation,
  OcrEvidence,
  ScreenshotFrame,
  UiEvidence,
  VisionInference,
)
from uno_shared.service_app import ServiceApp

# Register UNO game adapter as first plugin
register_game_adapter("uno", UnuPerceptionAdapter())

svc = ServiceApp("perception-service", description="Evidence merger — never canonical truth")
# Surface the VLM gate in /health. These are read at MODULE IMPORT time, so the
# values here are exactly what /perceive will use for the life of the process —
# which makes /health the cheapest way to confirm VLM_PERCEPTION actually reached
# the service, without waiting for a game cycle to produce a [CVv3] line. This
# was the missing check behind "I set VLM_PERCEPTION=1 and it still ran on the
# heuristic": nothing loaded .env, and nothing reported that fact.
svc.set_health_detail("vlm_enabled", vlm_enabled())
svc.set_health_detail("vlm_profile_id", VLM_PROFILE_ID)
svc.set_health_detail("vlm_timeout_s", VLM_TIMEOUT_S)
svc.set_health_detail("model_runtime_url", MODEL_RUNTIME_URL)
app: FastAPI = svc.create_app()


# ── L0 frame-diff gate (latency step 2) ────────────────────────────────────────
# A static board does not deserve a VLM call. The gate compares each incoming
# frame (128x128 grayscale) against the last frame that was looked at for this
# session; only a real change (or a forced refresh) triggers the vision model,
# and the resulting VisionInference is cached and replayed while the screen
# stands still. Environment:
#   VLM_FRAME_GATE=0        disable the gate entirely (always call the VLM)
#   VLM_FRAME_GATE_TTL_S    max seconds a cached board may be reused (default 90)
#   VLM_FRAME_GATE_MEAN     mean-delta threshold (default 0.5, 0..255 scale)
#   VLM_FRAME_GATE_MAX      local-delta threshold (default 24, 0..255 scale)
def _env_flag(name: str, default: bool = False) -> bool:
  v = os.getenv(name)
  if v is None:
    return default
  return v.strip().lower() in ("1", "true", "yes", "on")

FRAME_GATE_ENABLED = _env_flag("VLM_FRAME_GATE", True)
FRAME_GATE_TTL_S = float(os.getenv("VLM_FRAME_GATE_TTL_S", "90"))
FRAME_GATE_MEAN = float(os.getenv("VLM_FRAME_GATE_MEAN", "0.5"))
FRAME_GATE_MAX = float(os.getenv("VLM_FRAME_GATE_MAX", "24"))

_gate = FrameGate(mean_threshold=FRAME_GATE_MEAN, max_threshold=FRAME_GATE_MAX) if FRAME_GATE_ENABLED else None
# (session_id, effective_profile) -> (stored_at, VisionInference). Keyed by the
# EFFECTIVE profile so switching the operator's model (3b↔7b) mid-session never
# replays a board produced by the other model.
_vlm_cache: dict[tuple[str, str], tuple[float, "VisionInference"]] = {}
VLM_CACHE_MAX = 32


class PerceptionRequest(BaseModel):
  session_id: str
  dom: DomEvidence | None = None
  ui: UiEvidence | None = None
  ocr: OcrEvidence | None = None
  vlm: VisionInference | None = None
  screenshot: ScreenshotFrame | None = None
  game_type: str | None = None
  force_vlm: bool = False
  # Per-session VLM profile override (operator model picker). None = this
  # service's env default (VLM_PROFILE_ID). The orchestrator sets it from the
  # session's vlm_profile_id, so one agent can A/B 3b/7b/Ollama models live.
  vlm_profile_id: str | None = None


@app.post("/perceive", response_model=Observation, tags=["perception"])
async def perceive(req: PerceptionRequest) -> Observation:
  # ── Screenshot snapshot ────────────────────────────────────────────────────
  # The adapter's evidence-*.png file may be deleted or overwritten between the
  # VLM call and the heuristic fallback (up to ~30 s later on a slow cycle that
  # hits the VLM timeout).  Snapshot the bytes into a process-local temp file
  # right now so every PIL Image.open() in this request reads a stable copy.
  # If the read fails we keep the original path; downstream errors will be explicit.
  _snap: str | None = None
  screenshot = req.screenshot
  if screenshot and screenshot.path:
    try:
      with open(screenshot.path, "rb") as fh:
        raw = fh.read()
      fd, _snap = tempfile.mkstemp(suffix=".png")
      os.write(fd, raw)
      os.close(fd)
      screenshot = screenshot.model_copy(update={"path": _snap})
    except OSError:
      pass  # keep original path; let downstream report the specific error

  try:
    # VLM perception (D6, env-gated via VLM_PERCEPTION): when enabled and a
    # screenshot is present, run the vision model and feed its structured board
    # into the merger's existing `vlm` slot. This is the game-agnostic primary
    # path; the heuristic canvas_plugin remains the fallback. `vlm_status` records
    # WHY the VLM did/didn't run so the operator [CVv3] line can show it (e.g.
    # "disabled" = VLM_PERCEPTION off, "http_503" = profile disabled).
    vlm = req.vlm
    vlm_status: str | None = None
    gate_stats: dict | None = None
    # Effective profile for this call: the session's operator choice, else this
    # service's env default. Everything below (cache key, the call itself) keys
    # off it so a mid-session 3b↔7b switch is clean.
    effective_profile = req.vlm_profile_id or VLM_PROFILE_ID
    if vlm is None and screenshot is not None:
      if not vlm_enabled():
        vlm_status = "disabled"
      else:
        shot_path = getattr(screenshot, "path", None)
        if not shot_path:
          vlm_status = "no_image_path"
        else:
          # L0 gate: on a static screen reuse the last VLM board instead of
          # calling the model. `force_vlm` (set by the orchestrator right after
          # the agent acted) bypasses the cache — the board just changed by
          # definition, and the diff reference must be refreshed too. The cache
          # is keyed by (session, profile): switching the model while the screen
          # is static must NOT replay the previous model's board.
          cached: VisionInference | None = None
          changed = True
          if _gate is not None and not req.force_vlm:
            changed, gate_stats = _gate.observe(req.session_id, shot_path)
            if not changed:
              hit = _vlm_cache.get((req.session_id, effective_profile))
              if hit is not None:
                age = time.time() - hit[0]
                if age <= FRAME_GATE_TTL_S:
                  _, cached = hit
          if cached is not None:
            vlm, vlm_status = cached, "cached_static"
          else:
            try:
              vlm, vlm_status = await infer_vision(
                shot_path, game_type=req.game_type or "uno", profile_id=effective_profile,
              )
              if _gate is not None and vlm is not None:
                _vlm_cache[(req.session_id, effective_profile)] = (time.time(), vlm)
                if len(_vlm_cache) > VLM_CACHE_MAX:
                  oldest = min(_vlm_cache, key=lambda k: _vlm_cache[k][0])
                  _vlm_cache.pop(oldest, None)
            except Exception:  # noqa: BLE001 — never let VLM break perception
              vlm, vlm_status = None, "error"
    obs = build_observation(
      req.session_id, dom=req.dom, ui=req.ui, ocr=req.ocr, vlm=vlm,
      screenshot=screenshot, game_type=req.game_type,
    )
    if vlm_status:
      obs.game_state = {**(obs.game_state or {}), "vlm_status": vlm_status}
    if gate_stats:
      obs.game_state = {**(obs.game_state or {}), "frame_gate": gate_stats}
    return obs
  finally:
    if _snap:
      try:
        os.unlink(_snap)
      except OSError:
        pass


@app.post("/merge-confidence", tags=["perception"])
async def merge(scores: list[float]) -> dict:
  return {"merged": merge_confidence(*scores)}


class GroundRequest(BaseModel):
  action_type: str
  screenshot_path: str
  params: dict = {}
  game_type: str = "unknown"
  profile: dict | None = None
  min_confidence: float = 0.5


class GroundResponse(BaseModel):
  found: bool
  x: float | None = None
  y: float | None = None
  confidence: float = 0.0
  method: str = "none"
  reason: str = ""
  metadata: dict = {}


@app.post("/ground", response_model=GroundResponse, tags=["grounding"])
async def ground(req: GroundRequest) -> GroundResponse:
  """Resolve a click point for a decided action (e.g. choose_color=red).

  Tries the configured providers cheapest-first (see grounding_providers); the
  first hit at/above min_confidence wins. Returns a miss (found=False) with the
  most informative reason when nothing grounds the action — the caller decides
  whether to fall back (e.g. ungrounded click, skip, ask the operator).
  """
  greq = GroundingRequest(
    action_type=req.action_type,
    screenshot_path=req.screenshot_path,
    params=req.params,
    game_type=req.game_type,
    profile=req.profile,
  )
  res = await resolve_grounding(
    greq, default_providers(req.game_type), min_confidence=req.min_confidence,
  )
  return GroundResponse(
    found=res.found, x=res.x, y=res.y, confidence=res.confidence,
    method=res.method, reason=res.reason, metadata=res.metadata,
  )


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_perception.api:app", host=os.getenv("UNO_UVICORN_HOST", "127.0.0.1"), port=SERVICE_PORTS["perception-service"])
