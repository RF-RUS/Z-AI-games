"""Integration: Windows draw_card vertical slice.

Proves the minimal end-to-end loop for the Windows game path:
  screenshot → perception → decision → action grounding → execute → verify

Specifically tests:
  1. Target locator falls back to layout_targets when UIA tree is empty
  2. Action mapping produces correct selector_key for draw_card
  3. Full orchestrator cycle completes with observe → execute steps
  4. The action grounding chain works without real UIA elements
"""

import pytest
from uno_adapter_windows.profiles import load_profile
from uno_adapter_windows.rpa.perception.target_locator import locate_selector
from uno_orchestrator.clients import binding_for
from uno_orchestrator.flow_controller import RuntimeSession
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.adapter_windows import TargetAcquisitionMethod
from uno_schemas.decision import DecisionExplanation, DecisionResult
from uno_schemas.game import ActionType, LegalAction
from uno_schemas.orchestrator import SessionSpec
from uno_schemas.perception import Observation, ObservationConfidence, UiEvidence
from uno_schemas.session import AdapterType, SessionConfig
from uno_shared.adapter_protocol import GenericActionResult, GenericEvidenceBundle
from uno_shared.adapter_registry import GenericAdapterClient

# ── 1. Target locator: layout_targets fallback ──

def test_real_profile_has_layout_targets():
    """real-uno-desktop profile now has layout_targets for coordinate fallback."""
    profile = load_profile("real-uno-desktop")
    assert profile.layout_targets, "layout_targets should not be empty"
    assert "draw_button" in profile.layout_targets
    assert "play_button" in profile.layout_targets


def test_draw_card_finds_target_via_layout_when_uia_empty():
    """When UIA tree is empty, locate_selector falls back to layout_targets."""
    profile = load_profile("real-uno-desktop")
    window_bounds = {"left": 0.0, "top": 0.0, "right": 1920.0, "bottom": 1080.0}
    target = locate_selector("draw", profile, [], window_bounds=window_bounds)
    assert target is not None, "layout_targets should provide a fallback target"
    assert target.method == TargetAcquisitionMethod.COORDINATE
    assert target.confidence >= 0.55
    assert target.click_point is not None
    # draw_button x_ratio=0.44, y_ratio=0.34 → 0.44*1920=844.8, 0.34*1080=367.2
    assert 800 < target.click_point["x"] < 900
    assert 340 < target.click_point["y"] < 400


def test_play_card_finds_target_via_layout_when_uia_empty():
    """play_card action resolves to play_button layout target."""
    profile = load_profile("real-uno-desktop")
    window_bounds = {"left": 100.0, "top": 50.0, "right": 1920.0, "bottom": 1080.0}
    target = locate_selector("play_red_five", profile, [], window_bounds=window_bounds)
    assert target is not None
    assert target.method == TargetAcquisitionMethod.COORDINATE
    assert target.label == "Play Red 5"


def test_action_mapping_enables_coordinate_fallback():
    """Windows action mapping now sets allow_coordinate_fallback=True."""
    client = GenericAdapterClient("windows", "http://noop")
    req = client.map_action("draw_card")
    assert req.extra.get("allow_coordinate_fallback") is True
    req_play = client.map_action("play_card")
    assert req_play.extra.get("allow_coordinate_fallback") is True


# ── 2. Full orchestrator cycle with Windows adapter ──

def _make_orch():
    from uno_orchestrator.in_process_clients import (
        InProcessClients,
        setup_in_process_adapter_registry,
    )
    setup_in_process_adapter_registry()
    return SessionOrchestrator(clients=InProcessClients())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_windows_draw_card_cycle_completes():
    """Full orchestrator cycle with Windows adapter completes observe→execute."""
    from unittest.mock import AsyncMock, MagicMock, patch

    orch = _make_orch()
    legal = [LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="draw-1")]
    chosen = legal[0]
    observation = Observation(
        observation_id="obs-draw",
        session_id="s",
        timestamp_ms=1,
        game_type="uno",
        game_state={"top_card": {"color": "red", "value": "5"}, "screen_type": "in_game"},
        confidence=ObservationConfidence(overall=0.8, game_state=0.75),
    )
    decision = DecisionResult(
        chosen_action=chosen,
        confidence=0.8,
        explanation=DecisionExplanation(summary="draw_card: heuristic"),
        correlation_id="c-draw",
    )

    ui = UiEvidence(confidence=0.7, element_tree={"extracted": {}})
    evidence_bundle = GenericEvidenceBundle(
        adapter_id="win-draw",
        session_id="s",
        ui_evidence=ui.model_dump(mode="json"),
    )

    mock_adapter_client = MagicMock()
    mock_adapter_client.capture_evidence = AsyncMock(return_value=evidence_bundle)
    mock_adapter_client.execute_action = AsyncMock(return_value=GenericActionResult(
        success=True, action_type="click_input", duration_ms=50,
    ))
    # map_action is sync on GenericAdapterClient — provide a real implementation
    from uno_shared.adapter_registry import GenericAdapterClient
    real_client = GenericAdapterClient("windows", "http://noop")
    mock_adapter_client.map_action = real_client.map_action

    mock_registry = MagicMock()
    mock_registry.get_client = MagicMock(return_value=mock_adapter_client)

    orch._clients.perceive = AsyncMock(return_value=observation)
    orch._clients.legal_actions = AsyncMock(return_value=legal)
    orch._clients.decide = AsyncMock(return_value=decision)
    orch._clients.guard_decision = AsyncMock(return_value={"allowed": True, "violation": None})
    orch._clients.apply_action = AsyncMock(return_value={"ok": True})
    orch._clients.replay_event = AsyncMock()
    orch._clients.replay_observation = AsyncMock()
    orch._clients.send_bot_message = AsyncMock(return_value=None)

    with patch("uno_orchestrator.flow_controller.get_adapter_registry", return_value=mock_registry):
        spec = SessionSpec(
            config=SessionConfig(adapter_type=AdapterType.WINDOWS, adapter_id="win-draw"),
            windows_profile_id="real-uno-desktop",
            automatic=False,
        )
        detail = await orch.create_session_with_game(spec)
        detail.adapter_bindings = [binding_for(AdapterType.WINDOWS, "win-draw", "real-uno-desktop")]
        orch._sessions[detail.session_id] = RuntimeSession(detail=detail, spec=spec)
        await orch.start(detail.session_id)

        result = await orch.run_tick(detail.session_id)

        assert "action" in result, f"cycle should produce action result, got {result}"
        assert result.get("error") is None, f"cycle should have no error, got {result.get('error')}"
        assert detail.metrics.total_steps == 1
        assert detail.error is None

        step_names = [s.step_name.value for s in orch.get_steps(detail.session_id)]
        assert "observe" in step_names
        assert "perceive" in step_names
        assert "decide" in step_names
        assert "execute" in step_names
        assert "record" in step_names

        mock_adapter_client.execute_action.assert_awaited_once()
        call_args = mock_adapter_client.execute_action.call_args
        action_req = call_args[0][1]
        assert action_req.selector_key == "draw"
        assert action_req.domain_action == "draw_card"


@pytest.mark.integration
def test_mock_evidence_to_perception_produces_observation():
    """Mock Windows evidence flows through perception and produces a valid observation."""
    from fastapi.testclient import TestClient
    from uno_adapter_windows.api import app as win_app
    from uno_perception.api import app as perception_app
    from uno_schemas.adapter_windows import AttachWindowsAdapterRequest, WindowsAdapterMode

    client = TestClient(win_app)
    attach = client.post("/attach", json=AttachWindowsAdapterRequest(
        session_id="draw-perception-test", mode=WindowsAdapterMode.MOCK,
    ).model_dump(mode="json"))
    aid = attach.json()["adapter_id"]
    evidence = client.get(f"/adapters/{aid}/evidence").json()

    p = TestClient(perception_app)
    obs = p.post("/perceive", json={
        "session_id": "draw-perception-test",
        "ui": evidence["ui_evidence"],
    }).json()
    assert obs["confidence"]["overall"] > 0
    assert obs.get("game_state") is not None or obs.get("visible_chat")
