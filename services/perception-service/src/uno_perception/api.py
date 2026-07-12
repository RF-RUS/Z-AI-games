from fastapi import FastAPI
from pydantic import BaseModel
from uno_perception.merger import build_observation, merge_confidence, register_game_adapter
from uno_perception.uno_adapter import UnuPerceptionAdapter
from uno_perception.vlm_provider import infer_vision, vlm_enabled
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
  # VLM perception (D6, env-gated via VLM_PERCEPTION): when enabled and a
  # screenshot is present, run the vision model and feed its structured board
  # into the merger's existing `vlm` slot. This is the game-agnostic primary
  # path; the heuristic canvas_plugin remains the fallback (VLM off / no image /
  # inference failed → vlm stays None and nothing changes).
  vlm = req.vlm
  if vlm is None and req.screenshot is not None and vlm_enabled():
    shot_path = getattr(req.screenshot, "path", None)
    if shot_path:
      try:
        vlm = await infer_vision(shot_path, game_type=req.game_type or "uno")
      except Exception:  # noqa: BLE001 — never let VLM break perception
        vlm = None
  return build_observation(
    req.session_id, dom=req.dom, ui=req.ui, ocr=req.ocr, vlm=vlm,
    screenshot=req.screenshot, game_type=req.game_type,
  )


@app.post("/merge-confidence", tags=["perception"])
async def merge(scores: list[float]) -> dict:
  return {"merged": merge_confidence(*scores)}


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_perception.api:app", host="127.0.0.1", port=SERVICE_PORTS["perception-service"])
