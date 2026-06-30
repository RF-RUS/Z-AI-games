"""Contract tests for schema serialization."""

import json
from pathlib import Path

from uno_schemas.game import EventType, ReplayEnvelope
from uno_schemas.model import ModelManifest
from uno_schemas.perception import Observation, ObservationConfidence

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_replay_envelope_roundtrip():
  raw = json.loads((FIXTURES / "sample_replay.json").read_text())
  env = ReplayEnvelope.model_validate(raw)
  assert env.replay_id == "sample-replay-001"
  assert env.events[0].event_type == EventType.CARD_PLAYED


def test_observation_json_schema():
  obs = Observation(
    observation_id="o1",
    session_id="s1",
    timestamp_ms=0,
    confidence=ObservationConfidence(overall=0.5),
  )
  dumped = json.loads(obs.model_dump_json())
  assert dumped["confidence"]["overall"] == 0.5


def test_model_manifest_contract():
  m = ModelManifest(
    model_id="test/m",
    display_name="T",
    source_repo="test/m",
    modality="text",
    runtime="mock",
  )
  restored = ModelManifest.model_validate_json(m.model_dump_json())
  assert restored.model_id == m.model_id
