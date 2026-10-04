"""The drawn-card Play/Keep prompt must be decided by GAME STRATEGY.

Regression for the observed stall: after drawing, the game shows the card with
a "play it or keep it" question and the old code clicked Play first by static
label priority - the AI never analysed what was actually on screen. Now
`choose_prompt_with_strategy` (perceived_actions) gets the perceived drawn card,
top card and hand, returns the button to click plus WHY, and the flow layer
clicks that button and tells the operator the reason in chat and logs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_orchestrator.clients import binding_for
from uno_orchestrator.flow_controller import FlowController, RuntimeSession
from uno_schemas.orchestrator import FlowState, SessionSpec
from uno_schemas.perception import Observation, ObservationConfidence
from uno_schemas.session import AdapterType, SessionConfig, SessionPhase


def _mk_session():
    spec = SessionSpec(config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="a1"))
    from uno_schemas.orchestrator import SessionDetail

    detail = SessionDetail(
        session_id="s-prompt",
        flow_state=FlowState.ACTIVE,
        phase=SessionPhase.OBSERVE,
        correlation_id="c1",
        config=spec.config,
        adapter_bindings=[binding_for(AdapterType.WEB, "a1", "scuffed-uno-web")],
    )
    return detail, spec


def _observation(game_state: dict) -> Observation:
    return Observation(
        observation_id="o1",
        session_id="s-prompt",
        timestamp_ms=0,
        game_type="uno_canvas",
        game_state=game_state,
        confidence=ObservationConfidence(overall=0.9, game_state=0.9),
    )


_PLAY_KEEP = [
    {"label": "Play", "center": {"x": 768, "y": 630}},
    {"label": "Keep", "center": {"x": 1070, "y": 630}},
]


class TestStrategyPromptClick:
    def _make_flow(self, obs: Observation):
        """Flow wired with a stubbed perceive (returns `obs`) and a mocked adapter."""
        from uno_shared.adapter_protocol import GenericEvidenceBundle

        flow = FlowController()
        # Perceive is stubbed: perception already produced the Play/Keep board.
        flow.clients = MagicMock()
        flow.clients.perceive = AsyncMock(return_value=obs)

        def _bot_message(session_id, text, correlation_id=""):
            from uno_schemas.chat import ChatMessage

            return ChatMessage(
                message_id=f"bot-{correlation_id[:8]}", sender="bot",
                text=text, timestamp_ms=0, is_bot=True,
            )

        flow.clients.send_bot_message = AsyncMock(side_effect=_bot_message)
        client = AsyncMock()
        client.map_action = MagicMock(return_value=MagicMock(selector_key="prompt"))
        client.execute_action = AsyncMock(return_value=MagicMock(success=True))
        client.capture_evidence = AsyncMock(
            return_value=GenericEvidenceBundle(adapter_id="a1", session_id="s-prompt"),
        )
        registry = MagicMock()
        registry.get_client = MagicMock(return_value=client)
        return flow, client, registry

    @pytest.mark.asyncio
    async def test_matching_drawn_card_clicks_play_with_reason(self, tmp_path, monkeypatch):
        """Drawn red 5 on top red 2 -> strategy says play; chat carries the why."""
        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        obs = _observation({
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "green", "value": "4"}],
            "drawn_card": {"color": "red", "value": "5"},
            "prompts": _PLAY_KEEP,
        })
        flow, client, registry = self._make_flow(obs)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            result = await flow.run_cycle(session)

        assert result["prompt_clicked"] == "Play"
        assert "matches top red 2" in result["prompt_strategy"]
        req = client.execute_action.await_args.args[1]
        assert req.extra["target_x"] == 768 and req.extra["target_y"] == 630
        assert req.extra["prompt_label"] == "Play"
        assert "matches top red 2" in req.extra["prompt_strategy"]
        # The decision is ANNOUNCED in chat, not just logged.
        msgs = [m.text for m in session.chat_messages]
        assert any("Play" in t and "matches top red 2" in t for t in msgs)

    @pytest.mark.asyncio
    async def test_non_matching_drawn_card_clicks_keep(self, tmp_path, monkeypatch):
        """The whole point: the agent no longer force-clicks Play. Blue 5 on
        top red 2 cannot be played -> Keep is clicked, with the reason."""
        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        obs = _observation({
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "green", "value": "4"}],
            "drawn_card": {"color": "blue", "value": "5"},
            "prompts": _PLAY_KEEP,
        })
        flow, client, registry = self._make_flow(obs)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            result = await flow.run_cycle(session)

        assert result["prompt_clicked"] == "Keep"
        assert "does not match" in result["prompt_strategy"]
        req = client.execute_action.await_args.args[1]
        assert (req.extra["target_x"], req.extra["target_y"]) == (1070, 630)
        msgs = [m.text for m in session.chat_messages]
        assert any("Keep" in t and "does not match" in t for t in msgs)

    @pytest.mark.asyncio
    async def test_wild_hoard_overrides_static_play_priority(self, tmp_path, monkeypatch):
        """Old behaviour would click Play (static rank). Strategy hoards the wild
        when the hand already has a playable card."""
        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        obs = _observation({
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "red", "value": "7"}],
            "drawn_card": {"color": "wild", "value": "wild"},
            "prompts": _PLAY_KEEP,
        })
        flow, client, registry = self._make_flow(obs)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            result = await flow.run_cycle(session)

        assert result["prompt_clicked"] == "Keep"
        assert "hoard" in result["prompt_strategy"]


class TestPromptStallEscalation:
    """A modal that never reacts (unconfirmed clicks) must escalate to the
    operator after N cycles instead of the agent silently re-clicking forever —
    the 'Play, Play, Play…' 20s stall the operator reported.

    `_make_flow` stubs `capture_evidence` with no screenshot path, so every
    prompt click is `unverifiable` (never confirmed) — exactly the stuck case.
    """

    def _make_flow(self, obs):
        from uno_shared.adapter_protocol import GenericEvidenceBundle

        from uno_orchestrator.flow_controller import FlowController

        flow = FlowController()
        flow.clients = MagicMock()
        flow.clients.perceive = AsyncMock(return_value=obs)

        def _bot_message(session_id, text, correlation_id=""):
            from uno_schemas.chat import ChatMessage

            return ChatMessage(
                message_id=f"bot-{correlation_id[:8]}", sender="bot",
                text=text, timestamp_ms=0, is_bot=True,
            )

        flow.clients.send_bot_message = AsyncMock(side_effect=_bot_message)
        client = AsyncMock()
        client.map_action = MagicMock(return_value=MagicMock(selector_key="prompt"))
        client.execute_action = AsyncMock(return_value=MagicMock(success=True))
        client.capture_evidence = AsyncMock(
            return_value=GenericEvidenceBundle(adapter_id="a1", session_id="s-prompt"),
        )
        registry = MagicMock()
        registry.get_client = MagicMock(return_value=client)
        return flow, client, registry

    @pytest.mark.asyncio
    async def test_unconfirmed_prompt_escalates_after_n_cycles(self, tmp_path, monkeypatch):
        from uno_orchestrator.flow_controller import (
            _PROMPT_HALLUCINATION_SUPPRESS_CYCLES,
            _PROMPT_STALL_ESCALATE_AT,
        )

        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        obs = _observation({
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "green", "value": "4"}],
            "prompts": _PLAY_KEEP,
        })
        flow, client, registry = self._make_flow(obs)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)

        stall_texts = []
        seen = 0
        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            for i in range(_PROMPT_STALL_ESCALATE_AT):
                result = await flow.run_cycle(session)
                # Which side (Play/Keep) doesn't matter for the stall test —
                # only that the same modal keeps coming back unconfirmed.
                assert result.get("prompt_clicked") in ("Play", "Keep")
                # Collect only NEW stall messages (the chat accumulates history).
                for m in session.chat_messages[seen:]:
                    if "STALLED" in m.text:
                        stall_texts.append(m.text)
                seen = len(session.chat_messages)

            # The next cycle must NOT re-click the phantom: suppression kicks in
            # and the flow falls through to card play (session 0f7de4cd freeze).
            result = await flow.run_cycle(session)
            assert result.get("prompt_clicked") is None

        # Exactly one escalation, after reaching the threshold — not every cycle.
        assert len(stall_texts) == 1
        assert "STALLED on prompt" in stall_texts[0]
        # The escalation armed the anti-hallucination suppression window, and the
        # 4th cycle consumed exactly one of it.
        assert session.prompt_suppress_cycles == _PROMPT_HALLUCINATION_SUPPRESS_CYCLES - 1
        # Counter reset after escalating, so a fresh stall starts from zero.
        assert session.prompt_stall_count == 0

    @pytest.mark.asyncio
    async def test_phantom_prompt_suppressed_falls_through_to_card_play(self, tmp_path, monkeypatch):
        """While suppression is active the prompt branch is SKIPPED: no click is
        delivered and the cycle proceeds to normal card decision. A prompt-free
        cycle re-arms prompt handling immediately (a dialog that appears after a
        clean board is real, not a lingering phantom)."""
        from uno_orchestrator.flow_controller import _PROMPT_HALLUCINATION_SUPPRESS_CYCLES

        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        obs = _observation({
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "green", "value": "4"}],
            "prompts": _PLAY_KEEP,
        })
        flow, client, registry = self._make_flow(obs)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        session.prompt_suppress_cycles = _PROMPT_HALLUCINATION_SUPPRESS_CYCLES

        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            result = await flow.run_cycle(session)

        # No prompt click was delivered this cycle (the phantom was suppressed);
        # the flow fell through to the normal card path instead of the prompt
        # branch — which is what finally un-freezes the agent.
        assert result.get("prompt_clicked") is None
        assert session.prompt_suppress_cycles == _PROMPT_HALLUCINATION_SUPPRESS_CYCLES - 1
        # The prompt was NOT re-escalated/clicked: stall counter untouched.
        assert session.prompt_stall_count == 0

    @pytest.mark.asyncio
    async def test_prompt_free_cycle_rearms_suppression(self, tmp_path, monkeypatch):
        """A clean (prompt-free) cycle clears suppression, so a REAL dialog that
        appears afterwards is handled on the very next cycle — the guard must
        not blind the agent to genuine prompts."""
        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        with_prompt = _observation({
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "green", "value": "4"}],
            "prompts": _PLAY_KEEP,
        })
        no_prompt = _observation({
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "green", "value": "4"}],
            "prompts": [],
        })
        flow, client, registry = self._make_flow(with_prompt)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        session.prompt_suppress_cycles = 2

        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            flow.clients.perceive = AsyncMock(return_value=no_prompt)
            await flow.run_cycle(session)

        assert session.prompt_suppress_cycles == 0


    @pytest.mark.asyncio
    async def test_stall_counter_resets_when_modal_disappears(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
        with_prompt = _observation({
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "green", "value": "4"}],
            "prompts": _PLAY_KEEP,
        })
        no_prompt = _observation({
            "screen_type": "in_game",
            "top_card": {"color": "red", "value": "2"},
            "hand_cards": [{"color": "green", "value": "4"}],
            "prompts": [],
        })
        flow, client, registry = self._make_flow(with_prompt)
        detail, spec = _mk_session()
        session = RuntimeSession(detail=detail, spec=spec, observe_ready=True)
        with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=registry):
            # One unconfirmed prompt cycle builds the counter…
            await flow.run_cycle(session)
            assert session.prompt_stall_count >= 1
            # …then the modal is gone → the counter resets.
            flow.clients.perceive = AsyncMock(return_value=no_prompt)
            await flow.run_cycle(session)
        assert session.prompt_stall_count == 0

