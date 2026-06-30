import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from uno_replay.store import FileEventStore
from uno_schemas.adapter_web import ObservationArtifactBundle, ReplayArtifactRef, ReplayDetail
from uno_schemas.game import DomainEvent, ReplayEnvelope
from uno_shared.service_app import ServiceApp

STORE_PATH = Path(os.getenv("UNO_REPLAY_STORAGE_PATH", "./data/replays"))
store = FileEventStore(STORE_PATH)

svc = ServiceApp("state-replay-service", description="Event store, artifacts, and replay detail")
svc.set_health_detail("replay_count", len(store.list_replays()))
app: FastAPI = svc.create_app()


@app.get("/replays", tags=["replay"])
async def list_replays() -> list[dict]:
  return store.list_replays()


@app.post("/replays/{replay_id}/events", tags=["replay"])
async def append_event(replay_id: str, event: DomainEvent) -> dict:
  store.append(replay_id, event)
  return {"appended": event.event_id}


@app.post("/replays/{replay_id}/artifacts", tags=["replay"])
async def append_artifact(replay_id: str, artifact: ReplayArtifactRef) -> dict:
  store.append_artifact(replay_id, artifact)
  return {"appended": artifact.artifact_id}


@app.post("/replays/{replay_id}/observations", tags=["replay"])
async def append_observation(replay_id: str, bundle: ObservationArtifactBundle) -> dict:
  store.append_observation(replay_id, bundle)
  return {"appended": bundle.observation_id}


@app.get("/replays/{replay_id}", response_model=ReplayEnvelope, tags=["replay"])
async def get_replay(replay_id: str) -> ReplayEnvelope:
  envelope = store.export_envelope(replay_id, "unknown", "unknown")
  if not envelope.events:
    meta = store._load_meta(replay_id)
    if not meta:
      raise HTTPException(404, "replay not found")
  return envelope


@app.get("/replays/{replay_id}/detail", response_model=ReplayDetail, tags=["replay"])
async def get_replay_detail(replay_id: str) -> ReplayDetail:
  detail = store.export_detail(replay_id)
  if not detail:
    raise HTTPException(404, "replay not found")
  return detail


@app.post("/replays/import", tags=["replay"])
async def import_replay(envelope: ReplayEnvelope) -> dict:
  rid = store.import_envelope(envelope)
  return {"replay_id": rid}


def main() -> None:
  import uvicorn
  from uno_schemas.api import SERVICE_PORTS
  uvicorn.run("uno_replay.api:app", host="127.0.0.1", port=SERVICE_PORTS["state-replay-service"])
