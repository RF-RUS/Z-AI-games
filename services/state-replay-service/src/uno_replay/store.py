"""Append-only event store with artifacts — Postgres planned, file-based for local dev."""

from __future__ import annotations

import json
from pathlib import Path

from uno_schemas.adapter_web import ObservationArtifactBundle, ReplayArtifactRef, ReplayDetail
from uno_schemas.game import DomainEvent, ReplayEnvelope


class FileEventStore:
  def __init__(self, base_path: Path) -> None:
    self.base_path = base_path
    self.base_path.mkdir(parents=True, exist_ok=True)
    self.artifacts_path = self.base_path / "artifacts"
    self.artifacts_path.mkdir(parents=True, exist_ok=True)

  def _meta_path(self, replay_id: str) -> Path:
    return self.base_path / f"{replay_id}.meta.json"

  def _artifacts_index_path(self, replay_id: str) -> Path:
    return self.artifacts_path / f"{replay_id}_artifacts.json"

  def _observations_path(self, replay_id: str) -> Path:
    return self.artifacts_path / f"{replay_id}_observations.json"

  def append(self, replay_id: str, event: DomainEvent) -> None:
    path = self.base_path / f"{replay_id}.jsonl"
    existing = self.load(replay_id)
    if any(e.event_id == event.event_id for e in existing):
      return
    with path.open("a", encoding="utf-8") as f:
      f.write(event.model_dump_json() + "\n")

  def load(self, replay_id: str) -> list[DomainEvent]:
    path = self.base_path / f"{replay_id}.jsonl"
    if not path.exists():
      return []
    events = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
      if line:
        events.append(DomainEvent.model_validate_json(line))
    return events

  def list_replays(self) -> list[dict]:
    replays = []
    for file in self.base_path.glob("*.jsonl"):
      rid = file.stem
      meta = self._load_meta(rid)
      replays.append({
        "replay_id": rid,
        "game_id": meta.get("game_id", "unknown"),
        "session_id": meta.get("session_id", "unknown"),
        "event_count": len(self.load(rid)),
      })
    return replays

  def _load_meta(self, replay_id: str) -> dict:
    path = self._meta_path(replay_id)
    if path.exists():
      return json.loads(path.read_text(encoding="utf-8"))
    return {}

  def save_meta(self, replay_id: str, meta: dict) -> None:
    existing = self._load_meta(replay_id)
    existing.update(meta)
    self._meta_path(replay_id).write_text(json.dumps(existing, indent=2), encoding="utf-8")

  def append_artifact(self, replay_id: str, artifact: ReplayArtifactRef) -> None:
    artifacts = self.load_artifacts(replay_id)
    if any(a.artifact_id == artifact.artifact_id for a in artifacts):
      return
    artifacts.append(artifact)
    self._artifacts_index_path(replay_id).write_text(
      json.dumps([a.model_dump(mode="json") for a in artifacts], indent=2),
      encoding="utf-8",
    )

  def load_artifacts(self, replay_id: str) -> list[ReplayArtifactRef]:
    path = self._artifacts_index_path(replay_id)
    if not path.exists():
      return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ReplayArtifactRef.model_validate(a) for a in data]

  def append_observation(self, replay_id: str, bundle: ObservationArtifactBundle) -> None:
    obs = self.load_observations(replay_id)
    obs.append(bundle)
    self._observations_path(replay_id).write_text(
      json.dumps([o.model_dump(mode="json") for o in obs], indent=2),
      encoding="utf-8",
    )

  def load_observations(self, replay_id: str) -> list[ObservationArtifactBundle]:
    path = self._observations_path(replay_id)
    if not path.exists():
      return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ObservationArtifactBundle.model_validate(o) for o in data]

  def export_envelope(self, replay_id: str, game_id: str, session_id: str) -> ReplayEnvelope:
    meta = self._load_meta(replay_id)
    return ReplayEnvelope(
      replay_id=replay_id,
      game_id=meta.get("game_id", game_id),
      session_id=meta.get("session_id", session_id),
      events=self.load(replay_id),
      metadata=meta.get("metadata", {}),
    )

  def export_detail(self, replay_id: str) -> ReplayDetail | None:
    events = self.load(replay_id)
    if not events and not self._meta_path(replay_id).exists():
      return None
    meta = self._load_meta(replay_id)
    return ReplayDetail(
      replay_id=replay_id,
      game_id=meta.get("game_id", "unknown"),
      session_id=meta.get("session_id", "unknown"),
      events=events,
      artifacts=self.load_artifacts(replay_id),
      observations=self.load_observations(replay_id),
      metadata=meta.get("metadata", {}),
    )

  def import_envelope(self, envelope: ReplayEnvelope) -> str:
    for event in envelope.events:
      self.append(envelope.replay_id, event)
    self.save_meta(envelope.replay_id, {
      "game_id": envelope.game_id,
      "session_id": envelope.session_id,
      "metadata": envelope.metadata,
    })
    return envelope.replay_id
