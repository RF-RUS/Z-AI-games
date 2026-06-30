"""Windows UIA extraction unit tests."""

from uno_adapter_windows.extraction import (
  build_window_snapshot,
  match_node,
  window_snapshot_to_ui_evidence,
)
from uno_adapter_windows.profiles import load_profile
from uno_schemas.adapter_windows import ControlSelector, UiNodeSnapshot


def test_match_node_by_title():
  node = UiNodeSnapshot(node_id="1", name="Draw", control_type="Button")
  assert match_node(node, ControlSelector(title="Draw", control_type="Button"))


def test_build_snapshot_extracts_card_and_chat():
  profile = load_profile("local-mock-uno")
  nodes = [
    UiNodeSnapshot(node_id="1", name="Discard: Red 5", control_type="Text"),
    UiNodeSnapshot(node_id="2", name="Player2: hey bot!", control_type="Text"),
    UiNodeSnapshot(node_id="3", name="Draw pile: 80", control_type="Text"),
  ]
  snap = build_window_snapshot(profile, nodes, "UNO Mock Test Target", "mock")
  assert snap.extracted["top_card"] == {"color": "red", "value": "5"}
  assert snap.extracted["chat_messages"]


def test_ui_evidence_from_snapshot():
  profile = load_profile("local-mock-uno")
  nodes = [UiNodeSnapshot(node_id="1", name="Discard: Red 5")]
  snap = build_window_snapshot(profile, nodes, "test", "mock")
  ui = window_snapshot_to_ui_evidence(snap)
  assert ui.element_tree["extracted"]["top_card"]
