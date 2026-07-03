"""Profile-driven UIA evidence extraction — not canonical game truth."""

from __future__ import annotations

import re
import time
from uuid import uuid4

from uno_schemas.adapter_windows import (
  ControlEvidence,
  ControlSelector,
  UiNodeSnapshot,
  WindowsAdapterProfile,
  WindowSnapshot,
)
from uno_schemas.perception import EvidenceSource, UiEvidence

COLOR_MAP = {"red": "red", "blue": "blue", "green": "green", "yellow": "yellow", "wild": "wild"}
VALUE_PATTERNS = [
  (r"\b(\d)\b", lambda m: m.group(1)),
  (r"skip", lambda _: "skip"),
  (r"reverse", lambda _: "reverse"),
  (r"draw two", lambda _: "draw_two"),
]


def _parse_card_from_text(text: str) -> dict | None:
  t = text.lower()
  color = next((c for c in COLOR_MAP if c in t), None)
  value = None
  for pattern, fn in VALUE_PATTERNS:
    m = re.search(pattern, t)
    if m:
      value = fn(m)
      break
  if color and value:
    return {"color": color, "value": value}
  return None


def _extract_hand_cards(
  nodes: list[UiNodeSnapshot],
  profile: WindowsAdapterProfile,
) -> list[dict]:
  """Extract individual cards from the hand area.

  Strategy:
  1. Find the hand_area node using profile selector
  2. Find child nodes that look like cards (by name containing color/value)
  3. Parse each child's name to extract card info
  4. Return list of {color, value, name, node_id, bounds}

  If no hand_area selector or no children found, scan all nodes for card-like names.
  """
  hand_cards: list[dict] = []
  seen_names: set[str] = set()

  # Strategy 1: Find hand_area node and extract its children
  hand_sel = profile.selectors.get("hand_area")
  if hand_sel:
    hand_nodes = find_matching_nodes(nodes, hand_sel)
    if hand_nodes:
      hand_node = hand_nodes[0]
      hand_id = hand_node.node_id
      # Find children of hand_area (nodes whose parent_id matches hand_node)
      for n in nodes:
        if hasattr(n, "parent_id") and n.parent_id == hand_id:
          card = _parse_card_from_text(n.name or "")
          if card and n.name not in seen_names:
            seen_names.add(n.name)
            hand_cards.append({
              **card,
              "name": n.name,
              "node_id": n.node_id,
              "bounds": n.bounds,
            })

  # Strategy 2: If no children found, scan all nodes for card-like names
  if not hand_cards:
    for n in nodes:
      name = n.name or ""
      if not name or len(name) > 50:
        continue
      card = _parse_card_from_text(name)
      if card and name not in seen_names:
        seen_names.add(name)
        hand_cards.append({
          **card,
          "name": name,
          "node_id": n.node_id,
          "bounds": n.bounds,
        })

  return hand_cards


def match_node(node: UiNodeSnapshot, sel: ControlSelector) -> bool:
  if sel.auto_id and node.auto_id != sel.auto_id:
    return False
  if sel.control_type and node.control_type and sel.control_type.lower() not in node.control_type.lower():
    return False
  if sel.class_name and node.class_name != sel.class_name:
    return False
  if sel.title and node.name != sel.title:
    return False
  if sel.title_regex and node.name and not re.search(sel.title_regex, node.name, re.I):
    return False
  return True


def find_matching_nodes(nodes: list[UiNodeSnapshot], sel: ControlSelector) -> list[UiNodeSnapshot]:
  return [n for n in nodes if match_node(n, sel)]


def build_window_snapshot(
  profile: WindowsAdapterProfile,
  nodes: list[UiNodeSnapshot],
  window_title: str,
  backend: str,
  class_name: str | None = None,
  process_name: str | None = None,
  truncated: bool = False,
  sparse_tree: bool = False,
) -> WindowSnapshot:
  extracted: dict = {}
  controls: list[ControlEvidence] = []
  chat_messages: list[str] = []

  discard_sel = profile.selectors.get("discard_top_card")
  if discard_sel:
    matched = find_matching_nodes(nodes, discard_sel)
    for n in matched:
      card = _parse_card_from_text(n.name or "")
      if card:
        extracted["top_card"] = card
        controls.append(ControlEvidence(selector_key="discard_top_card", name=n.name, text=n.name, confidence=0.85))
        break

  draw_sel = profile.selectors.get("draw_pile_count")
  if draw_sel:
    for n in find_matching_nodes(nodes, draw_sel):
      m = re.search(r"\d+", n.name or "")
      if m:
        extracted["draw_pile_count"] = int(m.group())
        break
  if "draw_pile_count" not in extracted:
    for n in nodes:
      m = re.search(r"draw pile:\s*(\d+)", (n.name or "").lower())
      if m:
        extracted["draw_pile_count"] = int(m.group(1))
        break

  player_sel = profile.selectors.get("current_player")
  if player_sel:
    for n in find_matching_nodes(nodes, player_sel):
      extracted["current_player_id"] = (n.name or "").replace("Current:", "").strip() or "bot"
      break

  for key, sel in profile.chat_selectors.items():
    for n in find_matching_nodes(nodes, sel):
      if n.name and ":" in n.name:
        chat_messages.append(n.name.strip())
      elif n.name and "hey bot" in n.name.lower():
        chat_messages.append(n.name.strip())

  for n in nodes:
    if n.name and re.search(r"player\d+:\s*", n.name, re.I):
      if n.name not in chat_messages:
        chat_messages.append(n.name.strip())

  # Extract hand cards
  hand_cards = _extract_hand_cards(nodes, profile)
  if hand_cards:
    extracted["hand_cards"] = hand_cards
    extracted["hand_count"] = len(hand_cards)

  extracted["chat_messages"] = chat_messages
  extracted.setdefault("discard_pile_count", 1)
  extracted.setdefault("direction", 1)
  extracted.setdefault("pending_draw", 0)

  confidence = 0.85 if extracted.get("top_card") else (0.5 if sparse_tree else 0.65)

  return WindowSnapshot(
    snapshot_id=str(uuid4()),
    window_title=window_title,
    class_name=class_name,
    process_name=process_name,
    backend=backend,
    captured_at_ms=int(time.time() * 1000),
    profile_id=profile.profile_id,
    nodes=nodes,
    extracted=extracted,
    confidence=confidence,
    truncated=truncated,
    sparse_tree=sparse_tree,
  )


def window_snapshot_to_ui_evidence(snapshot: WindowSnapshot) -> UiEvidence:
  return UiEvidence(
    source=EvidenceSource.UI_AUTOMATION,
    element_tree={
      "extracted": snapshot.extracted,
      "window_title": snapshot.window_title,
      "backend": snapshot.backend,
      "nodes_count": len(snapshot.nodes),
      "truncated": snapshot.truncated,
      "sparse_tree": snapshot.sparse_tree,
    },
    confidence=snapshot.confidence,
  )
