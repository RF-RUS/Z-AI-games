"""Playability gate: an in-game action is only executed on a playable board.

Session 56c1564a (2026-08-29): the agent reached card play (the anti-
hallucination guards worked — a real Keep was confirmed at change_ratio 0.65,
a grounded play_card was delivered). But the cycle right after the real Keep
closed was a TRANSITION frame — the game animating back to the table. perception
read `screen_type=menu`, `gs_conf=0.00`, `hand_cards=4`. The desynced simulated
engine still "decided" play_card from its stale belief; that card had no
on-screen coordinate to ground to, so the adapter refused
("…not supported via Windows UIA…") and the cycle died with flow_state=error.

The fix: before EXECUTING an in-game action, require the frame it was decided on
to look like a real board — perception says `screen_type=in_game` (or ambiguous
"unknown", NOT a non-board) with a non-zero game-state confidence. Otherwise the
move is DEFERRED (observe again) and the next healthy in_game cycle plays it.
The prompt branch (Play/Keep) is deliberately NOT gated — a modal exists on
screen regardless of the coarse board state.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_orchestrator.flow_controller import FlowController, RuntimeSession
from uno_orchestrator.clients import binding_for
from uno_schemas.decision import DecisionExplanation, DecisionResult
from uno_schemas.game import ActionType, Card, CardColor, CardValue, LegalAction
from uno_schemas.orchestrator import FlowState, SessionDetail, SessionSpec
from uno_schemas.perception import Observation, ObservationConfidence
from uno_schemas.session import AdapterType, SessionConfig, SessionPhase


def _observation(screen_type: str, gs_conf: float, hand: list | None = None) -> Observation:
  gs = {"screen_type": screen_type}
  if hand is not None:
    gs["hand_cards"] = hand
    gs["top_card"] = {"color": "red", "value": "2"}
  # `overall` is kept high so the min_confidence gate does NOT fire first — the
  # 56c1564a regression is specifically that a frame with a healthy overall
  # confidence still had game_state=0.0 (the board itself unreadable), which the
  # old code executed anyway. gs_conf is what the playability gate reads.
  return Observation(
    observation_id="o1",
    session_id="s-gate",
    timestamp_ms=0,
    game_type="uno_canvas",
    game_state=gs,
    confidence=ObservationConfidence(overall=0.9, game_state=gs_conf),
  )


class TestBoardIsPlayable:
  """Direct helper tests — no adapter wiring needed."""

  def _flow(self):
    return FlowController()

  def test_in_game_with_confidence_is_playable(self):
    f = self._flow()
    assert f._board_is_playable(_observation("in_game", 0.8, hand=[{"color": "red", "value": "2"}]), {"screen_type": "in_game"})

  def test_menu_is_not_playable(self):
    f = self._flow()
    assert not f._board_is_playable(_observation("menu", 0.0), {"screen_type": "menu"})

  def test_lobby_is_not_playable(self):
    f = self._flow()
    assert not f._board_is_playable(_observation("lobby", 0.5), {"screen_type": "lobby"})

  def test_unknown_screen_but_confidence_is_playable(self):
    """An ambiguous screen_type with real game-state confidence still passes —
    only an explicit non-board vetoes the move."""
    f = self._flow()
    assert f._board_is_playable(_observation("unknown", 0.7, hand=[{"color": "red", "value": "2"}]), {"screen_type": "unknown"})

  def test_in_game_but_zero_confidence_is_not_playable(self):
    f = self._flow()
    assert not f._board_is_playable(_observation("in_game", 0.0), {"screen_type": "in_game"})

  def test_no_game_state_data_is_playable(self):
    """No perception data at all → cannot know what's on screen → NOT deferred
    (legacy behaviour, same rule as replan_ungrounded_play: no data → act as
    decided). Only an explicit non-board/zero-confidence reading vetoes."""
    f = self._flow()
    assert f._board_is_playable(_observation("in_game", 0.8), None)
    assert f._board_is_playable(_observation("in_game", 0.8), {})


class TestPlayabilityGate:
  """Flow-level: a non-board frame defers the in-game action (adapter untouched)."""

  def _flow_and_client(self, obs):
    from uno_shared.adapter_protocol import GenericEvidenceBundle

    flow = FlowController()
    flow.clients = MagicMock()
    flow.clients.perceive = AsyncMock(return_value=obs)
    flow.clients.guard_decision = AsyncMock(return_value={"allowed": True, "violation": None})

    def _bot_message(session_id, text, correlation_id=""):
      from uno_schemas.chat import ChatMessage

      return ChatMessage(
        message_id=f"bot-{correlation_id[:8]}", sender="bot",
        text=text, timestamp_ms=0, is_bot=True,
      )

    flow.clients.send_bot_message = AsyncMock(side_effect=_bot_message)
    flow._execute = AsyncMock()  # the gate must prevent this from being called

    client = AsyncMock()
    client.capture_evidence = AsyncMock(
      return_value=GenericEvidenceBundle(adapter_id="a1", session_id="s-gate"),
    )
    registry = MagicMock()
    registry.get_client = MagicMock(return_value=client)
    return flow, client, registry

  def _session(self):
    spec = SessionSpec(config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="a1"))
    detail = SessionDetail(
      session_id="s-gate",
      flow_state=FlowState.ACTIVE,
      phase=SessionPhase.OBSERVE,
      correlation_id="c1",
      config=spec.config,
      adapter_bindings=[binding_for(AdapterType.WEB, "a1", "scuffed-uno-web")],
    )
    return RuntimeSession(detail=detail, spec=spec, observe_ready=True), detail

  def _play_decision(self) -> DecisionResult:
    return DecisionResult(
      chosen_action=LegalAction(
        action_type=ActionType.PLAY_CARD,
        player_id="p1",
        card=Card(color=CardColor.RED, value=CardValue.TWO),
        action_id="play-1",
      ),
      confidence=0.8,
      explanation=DecisionExplanation(summary="heuristic"),
      correlation_id="c1",
    )

  @pytest.mark.asyncio
  async def test_menu_frame_defers_play_card(self, tmp_path, monkeypatch):
    """The 56c1564a regression: a menu/zero-confidence frame must NOT deliver a
    play_card to the adapter — it is deferred and observed again."""
    monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
    obs = _observation("menu", 0.0, hand=[{"color": "red", "value": "2"}])
    flow, client, registry = self._flow_and_client(obs)
    session, detail = self._session()
    flow._decide = AsyncMock(return_value=self._play_decision())
    flow._legal_actions = AsyncMock(return_value=[])

    with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
      result = await flow.run_cycle(session)

    # The in-game action was deferred, not executed: the adapter was never asked
    # to map or deliver a click.
    assert result.get("deferred") is True
    assert result.get("planned_action") == "play_card"
    flow._execute.assert_not_awaited()

  @pytest.mark.asyncio
  async def test_in_game_frame_executes_play_card(self, tmp_path, monkeypatch):
    """A healthy in_game frame with confidence passes the gate and executes."""
    monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
    obs = _observation("in_game", 0.8, hand=[{"color": "red", "value": "2", "center": {"x": 500, "y": 650}}])
    flow, client, registry = self._flow_and_client(obs)
    session, detail = self._session()
    flow._decide = AsyncMock(return_value=self._play_decision())
    flow._legal_actions = AsyncMock(return_value=[])

    with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
      result = await flow.run_cycle(session)

    # Not deferred — the play_card went through to execute.
    assert not result.get("deferred")
    flow._execute.assert_awaited()
