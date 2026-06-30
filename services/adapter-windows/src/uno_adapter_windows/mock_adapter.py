"""Mock Windows adapter — deterministic CI default."""

from __future__ import annotations

from uno_adapter_windows.extraction import build_window_snapshot, window_snapshot_to_ui_evidence
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.rpa.session_state import RpaSessionState
from uno_adapter_windows.rpa.synthetic_frame import build_mock_synthetic_frame
from uno_adapter_windows.runtime import ARTIFACTS_DIR
from uno_schemas.adapter_windows import (
  OperatorPreviewState,
  UiNodeSnapshot,
  WindowAttachment,
  WindowsActionExecutionRequest,
  WindowsActionExecutionResult,
  WindowsAdapterMode,
  WindowsEvidenceBundle,
  WindowsRpaStatus,
)


class MockWindowsAdapter:
  def __init__(self, session_id: str, profile_id: str = "local-mock-uno", window_title: str = "UNO Mock Test Target") -> None:
    self.session_id = session_id
    self.profile_id = profile_id
    self.window_title = window_title
    self.attached = False
    self.backend = "mock"
    self.artifacts_dir = ARTIFACTS_DIR / session_id
    self._state = RpaSessionState("", session_id)

  def bind_adapter_id(self, adapter_id: str) -> None:
    self._state.adapter_id = adapter_id

  def get_preview_state(self) -> OperatorPreviewState:
    return self._state.to_preview()

  async def attach(self) -> bool:
    try:
      profile = load_profile(self.profile_id)
      if profile.window.title_regex:
        self.window_title = profile.window.title_regex.replace("^", "").replace("$", "")
    except FileNotFoundError:
      pass
    self.attached = True
    self._state.attachment = WindowAttachment(window_title=self.window_title, backend=self.backend)
    snap = await self._build_snapshot()
    labels = [n.name for n in snap.nodes if n.name]
    frame = build_mock_synthetic_frame(self.artifacts_dir, self.window_title, labels, self.session_id)
    self._state.push_synthetic_frame(frame)
    self._state.set_status(
      WindowsRpaStatus.READY,
      "mock windows adapter — synthetic preview (pywinauto unavailable or window not found)",
    )
    return True

  async def capture_ui_tree(self) -> dict:
    snap = await self._build_snapshot()
    return {"window": snap.window_title, "extracted": snap.extracted, "nodes_count": len(snap.nodes)}

  async def capture_evidence(self, adapter_id: str) -> WindowsEvidenceBundle:
    snap = await self._build_snapshot()
    return WindowsEvidenceBundle(
      adapter_id=adapter_id,
      session_id=self.session_id,
      window_snapshot=snap,
      ui_evidence=window_snapshot_to_ui_evidence(snap),
      chat_messages=snap.extracted.get("chat_messages", []),
    )

  async def _build_snapshot(self):
    profile = load_profile(self.profile_id)
    nodes = [
      UiNodeSnapshot(node_id="n1", control_type="Text", name="Discard: Red 5"),
      UiNodeSnapshot(node_id="n2", control_type="Text", name="Current: bot"),
      UiNodeSnapshot(node_id="n3", control_type="Text", name="Draw pile: 80"),
      UiNodeSnapshot(node_id="n4", control_type="Text", name="Player2: hey bot, what are the rules?"),
      UiNodeSnapshot(node_id="n5", control_type="Button", name="Draw"),
      UiNodeSnapshot(node_id="n6", control_type="Button", name="Play Red 5"),
    ]
    return build_window_snapshot(profile, nodes, self.window_title, self.backend)

  async def execute(self, req: WindowsActionExecutionRequest, correlation_id: str | None = None) -> WindowsActionExecutionResult:
    from uno_schemas.adapter_windows import WindowsActionExecutionResult as Result
    return Result(
      success=self.attached,
      action_type=req.action_type,
      target_metadata={"selector_key": req.selector_key, "title": req.title},
      duration_ms=1,
      correlation_id=correlation_id,
    )

  async def detach(self) -> None:
    self.attached = False

  @property
  def mode(self) -> WindowsAdapterMode:
    return WindowsAdapterMode.MOCK
