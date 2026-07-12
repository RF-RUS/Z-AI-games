"""Merge evidence from multiple sources into confidence-scored observations.

The merger is game-agnostic. Game-specific parsing is delegated to
registered GamePerceptionAdapter implementations.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from uno_schemas.perception import (
  DomEvidence,
  Observation,
  ObservationConfidence,
  ObservationDiscrepancy,
  OcrEvidence,
  ScreenshotFrame,
  UiEvidence,
  VisionInference,
)

_adapters: dict[str, Any] = {}


def register_game_adapter(game_type: str, adapter: Any) -> None:
  """Register a game perception adapter."""
  _adapters[game_type] = adapter


def get_game_adapter(game_type: str) -> Any | None:
  """Get a registered game perception adapter."""
  return _adapters.get(game_type)


def _ensure_default_adapters() -> None:
  """Register default game adapters if not already registered."""
  if "uno" not in _adapters:
    from uno_perception.uno_adapter import UnuPerceptionAdapter
    _adapters["uno"] = UnuPerceptionAdapter()


def merge_confidence(*scores: float) -> float:
  if not scores:
    return 0.0
  product = 1.0
  for s in scores:
    product *= max(0.0, min(1.0, s))
  return round(1.0 - product, 4) if len(scores) > 1 else scores[0]


def build_observation(
  session_id: str,
  dom: DomEvidence | None = None,
  ui: UiEvidence | None = None,
  ocr: OcrEvidence | None = None,
  vlm: VisionInference | None = None,
  screenshot: ScreenshotFrame | None = None,
  game_type: str | None = None,
) -> Observation:
  _ensure_default_adapters()

  evidence = [e for e in (dom, ui, ocr, vlm) if e is not None]
  confidences = [e.confidence for e in evidence]
  overall = merge_confidence(*confidences) if confidences else 0.3

  adapter = _adapters.get(game_type) if game_type else None
  if adapter is None:
    # Auto-detect UNO from evidence content
    if _looks_like_uno(dom, ui, ocr, vlm):
      adapter = _adapters.get("uno")

  game_state: dict[str, Any] | None = None
  game_elements: list[dict[str, Any]] = []
  visible_chat: list[str] = []
  discrepancies: list[ObservationDiscrepancy] = []

  if adapter:
    game_state, game_elements, visible_chat, discrepancies = _merge_with_adapter(
      adapter, dom, ui, ocr, vlm, overall
    )
  else:
    # Fallback: extract chat from evidence without game-specific parsing
    visible_chat = _extract_chat(dom, ui, ocr)

  # VLM board (D6): when the vision model produced a normalized board
  # (source=="vlm"), it is the PRIMARY perception. Fold its keys straight into
  # game_state and skip the per-game heuristic below so it can't overwrite them.
  vlm_board = vlm.structured if (vlm and isinstance(vlm.structured, dict)) else None
  vlm_has_cards = bool(vlm_board and vlm_board.get("source") == "vlm"
                       and (vlm_board.get("hand_cards") or vlm_board.get("top_card")))
  if vlm_has_cards:
    game_state = game_state or {}
    game_state["cv_build"] = "v3"
    for k in ("screen_type", "whose_turn", "top_card", "hand_cards", "hand_count"):
      if vlm_board.get(k) is not None:
        game_state[k] = vlm_board[k]
    game_state["recognition_method"] = "vlm"
    if vlm_board.get("hand_cards"):
      game_elements = [{"type": "card", **c} for c in vlm_board["hand_cards"]]
    overall = max(overall, float(vlm_board.get("confidence", 0.0) or 0.0))

  # Screenshot perception: supplement or replace UIA data when screenshot available
  if screenshot and screenshot.path and not vlm_has_cards:
    # Build marker — if the operator's [CVv3] line does NOT show pcv=v3, the
    # PERCEPTION service is running stale code (restart it), independent of the
    # orchestrator which prints [CVv3].
    game_state = (game_state or {})
    game_state["cv_build"] = "v3"
    try:
      from uno_perception.canvas_plugin import HeuristicCanvasUNOPlugin
      screenshot_plugin = HeuristicCanvasUNOPlugin()
      inference = screenshot_plugin.infer_from_screenshot(screenshot.path)
      if inference.screen_valid:
        screenshot_game_state = {
          "screen_type": inference.screen_type,
          "whose_turn": inference.whose_turn,
          "regions": [
            {
              "id": r.region_id,
              "type": r.region_type,
              "label": r.label,
              "x": r.x, "y": r.y,
              "width": r.width, "height": r.height,
              "actionable": r.is_actionable,
            }
            for r in inference.regions
          ],
          "actionable_targets": [
            {"id": r.region_id, "label": r.label, "x": r.x, "y": r.y}
            for r in inference.actionable_targets
          ],
          "source": "screenshot_heuristic",
        }
        # Extract visual card data from raw_metadata
        visual_detail = inference.raw_metadata.get("visual_extraction", {})
        if visual_detail:
          top = visual_detail.get("top_card")
          if top:
            screenshot_game_state["top_card"] = top
          hand = visual_detail.get("hand_cards", [])
          if hand:
            screenshot_game_state["hand_cards"] = hand
          discard = visual_detail.get("discard_card")
          if discard:
            screenshot_game_state["discard_card"] = discard
          screenshot_game_state["recognition_method"] = visual_detail.get("recognition_method", "heuristic")
          screenshot_game_state["recognition_detail"] = visual_detail
        # Merge with existing game_state or use screenshot state
        if game_state:
          game_state.update(screenshot_game_state)
        else:
          game_state = screenshot_game_state
        game_elements = [
          {"type": "region", "id": r.region_id, "label": r.label, "actionable": r.is_actionable}
          for r in inference.actionable_targets
        ]
        overall = max(overall, inference.confidence)
      else:
        # Screen judged invalid (unreadable / black). Surface WHY so the
        # operator diagnostic can show it instead of a silent empty state.
        game_state = (game_state or {})
        game_state["cv_screen_valid"] = False
        game_state["cv_status"] = inference.summary or "screen invalid"
    except Exception as exc:
      import logging
      import traceback
      tb = traceback.format_exc().strip().splitlines()[-1]
      logging.getLogger(__name__).warning(
        "screenshot_perception_failed error=%s", str(exc), exc_info=True,
      )
      # Surface the failure into the observation so it's visible in the UI.
      game_state = (game_state or {})
      game_state["cv_error"] = f"{type(exc).__name__}: {exc} @ {tb}"

  return Observation(
    observation_id=str(uuid4()),
    session_id=session_id,
    timestamp_ms=int(time.time() * 1000),
    game_type=adapter.game_type if adapter else "uno_canvas",
    game_state=game_state,
    game_elements=game_elements,
    visible_chat=visible_chat,
    confidence=ObservationConfidence(
      overall=overall,
      game_state=_compute_game_state_confidence(adapter, dom, ui, vlm, game_state),
      game_elements=_compute_game_elements_confidence(vlm, game_elements),
      chat_visible=(
        ocr.confidence if visible_chat and ocr
        else (ui.confidence if visible_chat and ui else (0.8 if visible_chat else 0.0))
      ),
    ),
    evidence=evidence,
    discrepancies=discrepancies,
  )


def _looks_like_uno(
  dom: DomEvidence | None,
  ui: UiEvidence | None,
  ocr: OcrEvidence | None,
  vlm: VisionInference | None,
) -> bool:
  """Heuristic: detect UNO evidence from content structure."""
  if dom and dom.snapshot and "top_card" in dom.snapshot:
    return True
  if ui and ui.element_tree:
    extracted = ui.element_tree.get("extracted", ui.element_tree)
    if isinstance(extracted, dict) and "top_card" in extracted:
      return True
  if vlm and vlm.structured and "top_card" in vlm.structured:
    return True
  return False


def _merge_with_adapter(
  adapter: Any,
  dom: DomEvidence | None,
  ui: UiEvidence | None,
  ocr: OcrEvidence | None,
  vlm: VisionInference | None,
  overall: float,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str], list[ObservationDiscrepancy]]:
  """Use a game adapter to parse evidence into game state."""
  game_state: dict[str, Any] | None = None
  game_elements: list[dict[str, Any]] = []
  visible_chat: list[str] = []
  discrepancies: list[ObservationDiscrepancy] = []

  if dom and dom.snapshot:
    parsed = adapter.parse_dom(dom.snapshot)
    if parsed:
      game_state = parsed
    visible_chat.extend(dom.snapshot.get("chat_messages", []))

  if ui and ui.element_tree:
    parsed = adapter.parse_ui(ui.element_tree)
    if parsed and not game_state:
      game_state = parsed
    extracted = ui.element_tree.get("extracted", ui.element_tree)
    if isinstance(extracted, dict):
      ui_chat = extracted.get("chat_messages", [])
      if ui_chat:
        visible_chat = list(dict.fromkeys([*visible_chat, *ui_chat]))

  if ocr:
    for block in ocr.text_blocks:
      text = block.get("text", "")
      if ":" in text:
        visible_chat.append(text)
    parsed = adapter.parse_ocr(ocr.text_blocks)
    if parsed and not game_state:
      game_state = parsed

  if vlm and vlm.structured:
    parsed = adapter.parse_vlm(vlm.structured)
    if parsed and not game_state:
      game_state = parsed
    game_elements = adapter.extract_elements(vlm.structured)

  if not game_elements and dom and dom.snapshot:
    hand_cards = dom.snapshot.get("hand_cards")
    if hand_cards:
      game_elements = hand_cards

  if game_state and dom and vlm:
    dom_state = adapter.parse_dom(dom.snapshot) if dom.snapshot else None
    vlm_state = adapter.parse_vlm(vlm.structured) if vlm.structured else None
    if dom_state and vlm_state:
      disc = adapter.check_discrepancy(dom_state, vlm_state)
      if disc:
        discrepancies.append(ObservationDiscrepancy(**disc))

  return game_state, game_elements, visible_chat, discrepancies


def _extract_chat(
  dom: DomEvidence | None,
  ui: UiEvidence | None,
  ocr: OcrEvidence | None,
) -> list[str]:
  """Extract chat messages without game-specific parsing."""
  chat: list[str] = []
  if dom and dom.snapshot:
    chat.extend(dom.snapshot.get("chat_messages", []))
  if ui and ui.element_tree:
    extracted = ui.element_tree.get("extracted", ui.element_tree)
    if isinstance(extracted, dict):
      chat.extend(extracted.get("chat_messages", []))
  if ocr:
    for block in ocr.text_blocks:
      text = block.get("text", "")
      if ":" in text:
        chat.append(text)
  return list(dict.fromkeys(chat))


def _compute_game_state_confidence(
  adapter: Any,
  dom: DomEvidence | None,
  ui: UiEvidence | None,
  vlm: VisionInference | None,
  game_state: dict[str, Any] | None,
) -> float:
  if not game_state:
    return 0.0
  # Screenshot-sourced game state has its own confidence
  if game_state.get("source") == "screenshot_heuristic":
    return game_state.get("confidence", 0.5)
  if vlm and game_state:
    return vlm.confidence
  if dom and game_state:
    cv_conf = 0.0
    grounding = dom.snapshot.get("action_grounding") if dom and dom.snapshot else None
    if grounding:
      cv_conf = grounding.get("detection_confidence", 0.0)
    if cv_conf > 0.0:
      return max(cv_conf, dom.confidence)
    return dom.confidence
  if ui and game_state:
    return ui.confidence
  return 0.0


def _compute_game_elements_confidence(
  vlm: VisionInference | None,
  game_elements: list[dict[str, Any]],
) -> float:
  if game_elements and vlm:
    return vlm.confidence
  return 0.0
