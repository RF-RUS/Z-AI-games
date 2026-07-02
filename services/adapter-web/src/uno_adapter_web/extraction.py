"""Profile-driven DOM extraction — generic, not canonical game truth."""

from __future__ import annotations

import re
import time
from uuid import uuid4

from uno_schemas.adapter_web import DomNodeEvidence, DomSnapshot, ProfileSelector, WebAdapterProfile
from uno_schemas.perception import DomEvidence, EvidenceSource

COLOR_MAP = {
  "red": "red", "blue": "blue", "green": "green", "yellow": "yellow",
  "wild": "wild",
}

VALUE_MAP = {
  "0": "0", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
  "6": "6", "7": "7", "8": "8", "9": "9",
  "skip": "skip", "reverse": "reverse", "draw two": "draw_two",
  "draw_two": "draw_two", "wild": "wild",
}


def _parse_card_from_element(text: str, color_attr: str | None = None, class_attr: str | None = None) -> dict | None:
  t = text.strip().lower()
  color = COLOR_MAP.get(color_attr or "", None)
  if not color and class_attr:
    for c in COLOR_MAP:
      if c in class_attr.lower().split():
        color = c
        break
  if not color:
    for c in COLOR_MAP:
      if c in t:
        color = c
        break
  value = None
  for k, v in VALUE_MAP.items():
    if k in t:
      value = v
      break
  if not value and re.search(r"\b\d\b", t):
    value = re.search(r"\b(\d)\b", t).group(1)  # type: ignore[union-attr]
  if color and value:
    return {"color": color, "value": value}
  return None


def normalize_playwright_nodes(raw_nodes: list[dict]) -> list[DomNodeEvidence]:
  return [DomNodeEvidence.model_validate(n) for n in raw_nodes]


def build_extracted_snapshot(profile: WebAdapterProfile, nodes: list[DomNodeEvidence], url: str) -> DomSnapshot:
  extracted: dict = {}
  chat_messages: list[str] = []

  discard_sel = profile.selectors.get("discard_top_card")
  if discard_sel:
    node = _find_node(nodes, discard_sel)
    if node:
      card = _parse_card_from_element(
        node.text or "",
        node.attributes.get("data-color"),
        node.attributes.get("class"),
      )
      if card:
        extracted["top_card"] = card

  draw_sel = profile.selectors.get("draw_pile_count")
  if draw_sel:
    node = _find_node(nodes, draw_sel)
    if node and node.text:
      try:
        extracted["draw_pile_count"] = int(node.text.strip())
      except ValueError:
        pass

  player_sel = profile.selectors.get("current_player")
  if player_sel:
    node = _find_node(nodes, player_sel)
    if node and node.text:
      extracted["current_player_id"] = node.text.strip()

  chat_line_sel = profile.selectors.get("chat_lines")
  if chat_line_sel:
    for n in nodes:
      if n.test_id == "chat-line" or (chat_line_sel.primary in n.selector):
        if n.text:
          chat_messages.append(n.text.strip())
  extracted["chat_messages"] = chat_messages
  extracted["discard_pile_count"] = extracted.get("discard_pile_count", 1)
  extracted["direction"] = extracted.get("direction", 1)
  extracted["pending_draw"] = extracted.get("pending_draw", 0)

  return DomSnapshot(
    snapshot_id=str(uuid4()),
    url=url,
    captured_at_ms=int(time.time() * 1000),
    profile_id=profile.profile_id,
    nodes=nodes,
    extracted=extracted,
    confidence=0.85 if extracted.get("top_card") else 0.5,
  )


def dom_snapshot_to_evidence(snapshot: DomSnapshot) -> DomEvidence:
  return DomEvidence(
    source=EvidenceSource.DOM,
    snapshot=snapshot.extracted,
    selectors={n.selector: n.text or "" for n in snapshot.nodes[:20]},
    confidence=snapshot.confidence,
  )


def _find_node(nodes: list[DomNodeEvidence], sel: ProfileSelector) -> DomNodeEvidence | None:
  from uno_adapter_web.selector_resolver import resolve_from_nodes
  winning, _level = resolve_from_nodes(nodes, sel)
  if not winning:
    return None
  for n in nodes:
    if winning in n.selector:
      return n
  return None
