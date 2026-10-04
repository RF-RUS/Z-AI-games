"""Prompt clicks must be verified against the screen, not just dispatched.

Regression, session 8b4cefc1 (2026-08-24): two consecutive Play clicks came back
success=True while the game kept showing the same Play/Keep modal. The flow used to
announce success on dispatch alone, so every later cycle decided on a board that
never moved. Now each prompt click re-captures the screen and requires a visible
change in the zone around the clicked point (see uno_shared.click_verification).
Ignored clicks are retried with offsets and reported UNCONFIRMED instead of being
passed off as played.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_orchestrator.clients import binding_for
from uno_orchestrator.flow_controller import FlowController, RuntimeSession
from uno_schemas.orchestrator import FlowState, SessionSpec
from uno_schemas.perception import Observation, ObservationConfidence
from uno_schemas.session import AdapterType, SessionConfig, SessionPhase
from uno_shared.adapter_protocol import GenericEvidenceBundle


def _mk_session():
    spec = SessionSpec(config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="a1"))
    from uno_schemas.orchestrator import SessionDetail

    detail = SessionDetail(
        session_id="s-clickv",
        flow_state=FlowState.ACTIVE,
        phase=SessionPhase.OBSERVE,
        correlation_id="c1",
        config=spec.config,
        adapter_bindings=[binding_for(AdapterType.WEB, "a1", "scuffed-uno-web")],
    )
    return detail, spec


def _observation() -> Observation:
    return Observation(
        observation_id="o1",
        session_id="s-clickv",
        timestamp_ms=0,
        game_type="uno_canvas",
        game_state={
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "green", "value": "4"}],
            "drawn_card": {"color": "red", "value": "5"},
            "prompts": [
                {"label": "Play", "center": {"x": 768, "y": 630}},
                {"label": "Keep", "center": {"x": 1070, "y": 630}},
            ],
        },
        confidence=ObservationConfidence(overall=0.9, game_state=0.9),
    )


class TestVerifiedPromptClick:
    def _make_flow(self, tmp_path, shots_per_capture=True):
        """Flow with a stubbed perceive and a mocked adapter that CAN capture frames."""
        flow = FlowController()
        flow.clients = MagicMock()
        flow.clients.perceive = AsyncMock(return_value=_observation())

        def _bot_message(session_id, text, correlation_id=""):
            from uno_schemas.chat import ChatMessage

            return ChatMessage(
                message_id=f"bot-{correlation_id[:8]}", sender="bot",
                text=text, timestamp_ms=0, is_bot=True,
            )

        flow.clients.send_bot_message = AsyncMock(side_effect=_bot_message)

        # Each evidence capture returns a fresh, readable frame path so the
        # before/after bracketing works end to end.
        shot = tmp_path / "frame.png"
        shot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)

        def _bundle(**kwargs):
            base = dict(adapter_id="a1", session_id="s-clickv")
            if shots_per_capture:
                base["screenshot_path"] = str(shot)
            return GenericEvidenceBundle(**base)

        client = AsyncMock()
        client.execute_action = AsyncMock(return_value=MagicMock(success=True, error=None))
        client.capture_evidence = AsyncMock(side_effect=lambda *a, **k: _bundle())
        registry = MagicMock()
        registry.get_client = MagicMock(return_value=client)
        return flow, client, registry

    @pytest.mark.asyncio
    async def test_reactive_screen_confirms_on_first_attempt(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        flow, client, registry = self._make_flow(tmp_path)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        with (
          patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry),
          patch("uno_orchestrator.flow_controller.verify_zone_change", return_value=0.4),
        ):
            result = await flow.run_cycle(session)

        assert result["prompt_clicked"] == "Play"
        assert result["prompt_status"] == "confirmed"
        # One delivery, one verification — no retries needed.
        assert client.execute_action.await_count == 1
        req = client.execute_action.await_args.args[1]
        assert (req.extra["target_x"], req.extra["target_y"]) == (768, 630)
        # The verdict travels to chat and to the offline trace.
        msgs = [m.text for m in session.chat_messages]
        assert any("confirmed" in t for t in msgs)
        trace = (tmp_path / "trace" / "s-clickv" / "0001" / "cycle.json").read_text(encoding="utf-8")
        import json

        rec = json.loads(trace)
        assert rec["click"]["status"] == "confirmed"
        assert rec["click"]["attempts"] == 1
        assert rec["timings_ms"]["execute"] >= 0

    @pytest.mark.asyncio
    async def test_ignored_click_is_retried_with_offsets_and_flagged_unconfirmed(
      self, tmp_path, monkeypatch,
    ):
        """The exact 8b4cefc1 failure: the game shows the same modal after the click.

        Dispatch alone said success; now the zone diff says nothing happened, the
        flow probes offsets around the perceived centre, and the operator sees
        UNCONFIRMED instead of a phantom move.
        """
        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        monkeypatch.setenv("CLICK_RETRY_SETTLE_S", "0")
        monkeypatch.setenv("CLICK_PROMPT_MAX_ATTEMPTS", "3")
        flow, client, registry = self._make_flow(tmp_path)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        with (
          patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry),
          patch("uno_orchestrator.flow_controller.verify_zone_change", return_value=0.01),
        ):
            result = await flow.run_cycle(session)

        assert result["prompt_status"] == "unconfirmed"
        assert client.execute_action.await_count == 3
        targets = [
          (c.args[1].extra["target_x"], c.args[1].extra["target_y"])
          for c in client.execute_action.await_args_list
        ]
        # Centre first, then offsets around it — never the same point twice.
        assert targets[0] == (768, 630)
        assert len(set(targets)) == 3
        msgs = [m.text for m in session.chat_messages]
        assert any("UNCONFIRMED" in t for t in msgs)

    @pytest.mark.asyncio
    async def test_second_offset_confirming_stops_retrying(self, tmp_path, monkeypatch):
        """A reaction on attempt N ends the loop — no wasted further clicks."""
        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        monkeypatch.setenv("CLICK_RETRY_SETTLE_S", "0")
        flow, client, registry = self._make_flow(tmp_path)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        ratios = iter([0.01, 0.42])
        with (
          patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry),
          patch("uno_orchestrator.flow_controller.verify_zone_change", side_effect=lambda *a, **k: next(ratios)),
        ):
            result = await flow.run_cycle(session)

        assert result["prompt_status"] == "confirmed"
        assert client.execute_action.await_count == 2

    @pytest.mark.asyncio
    async def test_missing_frames_report_unverifiable_not_failed(self, tmp_path, monkeypatch):
        """No before/after capture means 'I cannot tell' — not 'it failed'.

        Guessing either way reintroduces the original bug from the opposite side
        (claiming a move that did not happen, or hiding one that did).
        """
        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        flow, client, registry = self._make_flow(tmp_path, shots_per_capture=False)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            result = await flow.run_cycle(session)

        assert result["prompt_status"] == "unverifiable"
        assert client.execute_action.await_count == 1
        msgs = [m.text for m in session.chat_messages]
        assert any("unverified" in t for t in msgs)
