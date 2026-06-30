"""Mock web adapter — deterministic, no browser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from uno_adapter_web.extraction import build_extracted_snapshot, dom_snapshot_to_evidence
from uno_adapter_web.profiles import load_profile
from uno_schemas.adapter_web import (
  ActionExecutionRequest,
  ActionExecutionResult,
  AdapterEvidenceBundle,
  AdapterMode,
  DomNodeEvidence,
  WebActionType,
)


@dataclass
class MockWebAdapter:
  session_id: str
  profile_id: str = "local-mock-uno"
  url: str = "http://mock-uno.local"
  attached: bool = False
  dom_snapshot: dict[str, Any] = field(default_factory=dict)

  async def attach(self) -> bool:
    self.attached = True
    try:
      profile = load_profile(self.profile_id)
      self.url = profile.launch_url
    except FileNotFoundError:
      pass
    self.dom_snapshot = {
      "top_card": {"color": "red", "value": "5"},
      "current_player_id": "bot",
      "draw_pile_count": 80,
      "discard_pile_count": 5,
      "direction": 1,
      "pending_draw": 0,
      "chat_messages": ["Player2: hey bot, what are the rules?"],
    }
    return True

  async def read_dom(self) -> dict[str, Any]:
    return self.dom_snapshot

  async def capture_evidence(self, adapter_id: str) -> AdapterEvidenceBundle:
    profile = load_profile(self.profile_id)
    nodes = [
      DomNodeEvidence(selector="[mock]", text="Red 5", test_id="discard-top-card", attributes={"data-color": "red", "data-value": "5"}),
      DomNodeEvidence(selector="[mock-chat]", text="Player2: hey bot, what are the rules?", test_id="chat-line"),
    ]
    snapshot = build_extracted_snapshot(profile, nodes, self.url)
    snapshot.extracted = dict(self.dom_snapshot)
    return AdapterEvidenceBundle(
      adapter_id=adapter_id,
      session_id=self.session_id,
      dom_snapshot=snapshot,
      dom_evidence=dom_snapshot_to_evidence(snapshot),
      chat_messages=self.dom_snapshot.get("chat_messages", []),
    )

  async def execute(self, req: ActionExecutionRequest, correlation_id: str | None = None) -> ActionExecutionResult:
    click_point = None
    canvas_bounds = None
    if req.action_type == WebActionType.CLICK_COORDINATE and req.selector_key:
      profile = load_profile(self.profile_id)
      canvas_bounds = {"x": 0.0, "y": 0.0, "width": 1280.0, "height": 800.0}
      from uno_adapter_web.canvas_coords import build_coordinate_click_payload

      click_point, _ = build_coordinate_click_payload(req.selector_key, profile, canvas_bounds)
    return ActionExecutionResult(
      success=self.attached,
      action_type=req.action_type,
      selector=req.selector,
      selector_key=req.selector_key,
      click_point=click_point,
      canvas_bounds=canvas_bounds,
      duration_ms=1,
      correlation_id=correlation_id,
    )

  async def detach(self) -> None:
    self.attached = False

  @property
  def mode(self) -> AdapterMode:
    return AdapterMode.MOCK
