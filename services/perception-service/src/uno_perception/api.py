import os
import tempfile

from fastapi import FastAPI
from pydantic import BaseModel
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


class PerceptionRequest(BaseModel):
  session_id: str
  dom: DomEvidence | None = None
  ui: UiEvidence | None = None
  ocr: OcrEvidence | None = None
  vlm: VisionInference | None = None
  screenshot: ScreenshotFrame | None = None
  game_type: str | None = None


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
    if vlm is None and screenshot is not None:
      if not vlm_enabled():
        vlm_status = "disabled"
      else:
        shot_path = getattr(screenshot, "path", None)
        if not shot_path:
          vlm_status = "no_image_path"
        else:
          try:
            vlm, vlm_status = await infer_vision(shot_path, game_type=req.game_type or "uno")
          except Exception:  # noqa: BLE001 — never let VLM break perception
            vlm, vlm_status = None, "error"
    obs = build_observation(
      req.session_id, dom=req.dom, ui=req.ui, ocr=req.ocr, vlm=vlm,
      screenshot=screenshot, game_type=req.game_type,
    )
    if vlm_status:
      obs.game_state = {**(obs.game_state or {}), "vlm_status": vlm_status}
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
  uvicorn.run("uno_perception.api:app", host="127.0.0.1", port=SERVICE_PORTS["perception-service"])
