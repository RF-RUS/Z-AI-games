"""Perception domain — observations never equal canonical truth."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from uno_schemas.ids import Confidence, ObservationId, SessionId, TimestampMs


class EvidenceSource(StrEnum):
  DOM = "dom"
  UI_AUTOMATION = "ui_automation"
  OCR = "ocr"
  VLM = "vlm"
  SCREENSHOT = "screenshot"


class ScreenshotFrame(BaseModel):
  frame_id: str
  session_id: SessionId
  width: int = Field(gt=0)
  height: int = Field(gt=0)
  format: str = "png"
  data_base64: str | None = None
  path: str | None = None
  captured_at_ms: TimestampMs


class UiEvidence(BaseModel):
  source: EvidenceSource = EvidenceSource.UI_AUTOMATION
  element_tree: dict[str, Any] = Field(default_factory=dict)
  confidence: Confidence = 0.8


class OcrEvidence(BaseModel):
  source: EvidenceSource = EvidenceSource.OCR
  text_blocks: list[dict[str, Any]] = Field(default_factory=list)
  confidence: Confidence = 0.6


class DomEvidence(BaseModel):
  source: EvidenceSource = EvidenceSource.DOM
  selectors: dict[str, str] = Field(default_factory=dict)
  snapshot: dict[str, Any] = Field(default_factory=dict)
  confidence: Confidence = 0.9


class VisionInference(BaseModel):
  source: EvidenceSource = EvidenceSource.VLM
  model_id: str
  raw_output: str
  structured: dict[str, Any] = Field(default_factory=dict)
  confidence: Confidence = 0.5


class ObservationConfidence(BaseModel):
  overall: Confidence
  game_state: Confidence = 0.0
  game_elements: Confidence = 0.0
  chat_visible: Confidence = 0.0

  @property
  def table_state(self) -> Confidence:
    return self.game_state

  @property
  def hand_state(self) -> Confidence:
    return self.game_elements


class ObservationDiscrepancy(BaseModel):
  field: str
  expected: Any | None = None
  observed: Any | None = None
  severity: str = "warning"


class Observation(BaseModel):
  observation_id: ObservationId
  session_id: SessionId
  timestamp_ms: TimestampMs
  game_type: str | None = None
  game_state: dict[str, Any] | None = None
  game_elements: list[dict[str, Any]] = Field(default_factory=list)
  visible_chat: list[str] = Field(default_factory=list)
  confidence: ObservationConfidence
  evidence: list[UiEvidence | OcrEvidence | DomEvidence | VisionInference] = Field(
    default_factory=list
  )
  discrepancies: list[ObservationDiscrepancy] = Field(default_factory=list)

  # Deprecated UNO-specific fields — kept for backward compatibility
  # Will be removed after all consumers migrate to game_state/game_elements
  @property
  def table_state(self) -> Any | None:
    if self.game_type == "uno" and self.game_state:
      try:
        from uno_schemas.game import PublicTableState
        return PublicTableState.model_validate(self.game_state)
      except Exception:
        return None
    return None

  @property
  def hand_cards(self) -> list[Any]:
    if self.game_type == "uno" and self.game_elements:
      try:
        from uno_schemas.game import Card
        return [Card.model_validate(e) for e in self.game_elements]
      except Exception:
        return []
    return []

  @property
  def inferred_wild_color(self) -> Any | None:
    if self.game_type == "uno" and self.game_state:
      try:
        from uno_schemas.game import CardColor
        raw = self.game_state.get("inferred_wild_color")
        if raw:
          return CardColor(raw)
      except Exception:
        pass
    return None
