"""DOM extraction normalization tests."""

from uno_adapter_web.extraction import build_extracted_snapshot, dom_snapshot_to_evidence
from uno_adapter_web.profiles import load_profile
from uno_schemas.adapter_web import DomNodeEvidence


def test_build_extracted_snapshot_from_nodes():
  profile = load_profile("local-mock-uno")
  nodes = [
    DomNodeEvidence(
      selector="[data-testid='discard-top-card']",
      text="Red 5",
      test_id="discard-top-card",
      attributes={"data-color": "red", "data-value": "5"},
    ),
    DomNodeEvidence(selector="[data-testid='draw-pile-count']", text="80"),
    DomNodeEvidence(selector="[data-testid='current-player-id']", text="bot"),
    DomNodeEvidence(selector="[data-testid='chat-line']", text="Player2: hey bot!", test_id="chat-line"),
  ]
  snap = build_extracted_snapshot(profile, nodes, "http://test/")
  assert snap.extracted["top_card"] == {"color": "red", "value": "5"}
  assert snap.extracted["draw_pile_count"] == 80
  assert "Player2: hey bot!" in snap.extracted["chat_messages"]


def test_dom_snapshot_to_evidence():
  profile = load_profile("local-mock-uno")
  nodes = [
    DomNodeEvidence(
      selector="[data-testid='discard-top-card']",
      text="Red 5",
      test_id="discard-top-card",
      attributes={"data-color": "red", "data-value": "5"},
    )
  ]
  snap = build_extracted_snapshot(profile, nodes, "http://test/")
  evidence = dom_snapshot_to_evidence(snap)
  assert evidence.confidence == snap.confidence
  assert evidence.snapshot.get("top_card") is not None
