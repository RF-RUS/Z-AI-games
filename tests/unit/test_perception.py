"""Perception merger tests."""

from uno_perception.merger import build_observation, merge_confidence
from uno_schemas.perception import DomEvidence, UiEvidence, VisionInference


def test_merge_confidence_multiple():
  result = merge_confidence(0.9, 0.8)
  assert 0.0 <= result <= 1.0


def test_build_observation_from_dom():
  dom = DomEvidence(
    snapshot={
      "top_card": {"color": "red", "value": "5"},
      "current_player_id": "bot",
      "draw_pile_count": 10,
      "chat_messages": ["hi"],
    },
    confidence=0.9,
  )
  obs = build_observation("sess-1", dom=dom)
  assert obs.table_state is not None
  assert obs.confidence.overall > 0


def test_discrepancy_detection():
  dom = DomEvidence(
    snapshot={"top_card": {"color": "red", "value": "5"}},
    confidence=0.9,
  )
  vlm = VisionInference(
    model_id="test",
    raw_output="{}",
    structured={"top_card": {"color": "blue", "value": "5"}},
    confidence=0.7,
  )
  obs = build_observation("sess-1", dom=dom, vlm=vlm)
  assert len(obs.discrepancies) >= 1


def test_ui_evidence_merge():
  ui = UiEvidence(
    element_tree={
      "extracted": {
        "top_card": {"color": "red", "value": "5"},
        "chat_messages": ["Player2: hey bot!"],
        "current_player_id": "bot",
      }
    },
    confidence=0.8,
  )
  obs = build_observation("sess-ui", ui=ui)
  assert obs.table_state is not None
  assert obs.visible_chat
  assert obs.confidence.overall >= 0.8
