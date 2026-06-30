"""Integration-style tests for action-aware verification wiring.

Verifies the data path from chosen_action → session.last_action_type →
verification action_category + action_family, without requiring a full
orchestrator lifecycle.
"""

from unittest.mock import MagicMock

from uno_orchestrator.flow_controller import FlowController, RuntimeSession
from uno_orchestrator.orchestrator import (
    build_verification,
    classify_action_category,
    derive_expected_outcome_profile,
)
from uno_schemas.orchestrator import (
    FlowState,
    SessionConfig,
    SessionDetail,
    SessionSpec,
)


def _make_session_with_action(action_type, pre_state="not_in_game", execute_success=True, post_state="in_game"):
    """Create a RuntimeSession with pre-populated verification fields."""
    config = SessionConfig(
        adapter_type="mock",
        adapter_id="test-adapter",
        profile_id="local-mock-uno",
    )
    detail = SessionDetail(
        session_id="test-session",
        flow_state=FlowState.ACTIVE,
        phase="execute",
        config=config,
        correlation_id="test-corr",
        automatic=False,
    )
    spec = SessionSpec(config=config)
    session = RuntimeSession(detail=detail, spec=spec)
    session.pre_action_state = pre_state
    session.last_execute_success = execute_success
    session.last_action_type = action_type
    return session


class TestWiringNavigationStateAdvance:
    """click_play → family=state_advance, confirmed if state changed."""

    def test_click_play_advanced(self):
        v = build_verification("not_in_game", True, "in_game", "click_play")
        assert v.action_family == "state_advance"
        assert v.outcome_status == "confirmed"

    def test_click_play_unchanged(self):
        v = build_verification("not_in_game", True, "not_in_game", "click_play")
        assert v.action_family == "state_advance"
        assert v.outcome_status == "not_confirmed"

    def test_start_match_advanced(self):
        v = build_verification("not_in_game", True, "in_game", "start_match")
        assert v.action_family == "state_advance"
        assert v.outcome_status == "confirmed"


class TestWiringStateMayAdvance:
    """click_ready → family=state_may_advance, unknown if unchanged."""

    def test_click_ready_advanced(self):
        v = build_verification("not_in_game", True, "in_game", "click_ready")
        assert v.action_family == "state_may_advance"
        assert v.outcome_status == "confirmed"

    def test_click_ready_unchanged(self):
        v = build_verification("not_in_game", True, "not_in_game", "click_ready")
        assert v.action_family == "state_may_advance"
        assert v.outcome_status == "unknown"
        assert v.outcome_status != "not_confirmed"


class TestWiringObservability:
    """inspect_screen / focus_game_window → family=observability, unknown if unchanged."""

    def test_inspect_screen_unchanged(self):
        v = build_verification("not_in_game", True, "not_in_game", "inspect_screen")
        assert v.action_family == "observability"
        assert v.outcome_status == "unknown"

    def test_inspect_screen_improved(self):
        v = build_verification("unknown", True, "not_in_game", "inspect_screen")
        assert v.action_family == "observability"
        assert v.outcome_status == "confirmed"

    def test_focus_game_window_unchanged(self):
        v = build_verification("not_in_game", True, "not_in_game", "focus_game_window")
        assert v.action_family == "observability"
        assert v.outcome_status == "unknown"


class TestWiringInGameEffect:
    """play_card / draw_card → family=in_game_effect, unknown if unchanged."""

    def test_play_card_unchanged(self):
        v = build_verification("in_game", True, "in_game", "play_card")
        assert v.action_family == "in_game_effect"
        assert v.outcome_status == "unknown"
        assert v.outcome_status != "not_confirmed"

    def test_draw_card_unchanged(self):
        v = build_verification("in_game", True, "in_game", "draw_card")
        assert v.action_family == "in_game_effect"
        assert v.outcome_status == "unknown"

    def test_call_uno_unchanged(self):
        v = build_verification("in_game", True, "in_game", "call_uno")
        assert v.action_family == "in_game_effect"
        assert v.outcome_status == "unknown"


class TestWiringUnknownAction:
    """Unknown action type → family=unknown."""

    def test_none_action(self):
        v = build_verification("not_in_game", True, "not_in_game", None)
        assert v.action_family == "unknown"

    def test_weird_action(self):
        v = build_verification("in_game", True, "in_game", "totally_unknown_action")
        assert v.action_family == "unknown"


class TestExtractActionType:
    """Verify FlowController._extract_action_type works correctly."""

    def _make_controller(self):
        clients = MagicMock()
        return FlowController(clients)

    def test_extracts_from_real_decision(self):
        ctrl = self._make_controller()
        decision = MagicMock()
        decision.chosen_action.action_type.value = "play_card"
        assert ctrl._extract_action_type(decision) == "play_card"

    def test_returns_none_for_no_decision(self):
        ctrl = self._make_controller()
        assert ctrl._extract_action_type(None) is None

    def test_returns_none_for_no_chosen_action(self):
        ctrl = self._make_controller()
        decision = MagicMock()
        decision.chosen_action = None
        assert ctrl._extract_action_type(decision) is None

    def test_extracts_string_action_type(self):
        ctrl = self._make_controller()
        decision = MagicMock()
        decision.chosen_action.action_type = "click_play"
        assert ctrl._extract_action_type(decision) == "click_play"


class TestSnapshotVerificationIntegration:
    """Test full path: action type → verification → snapshot-like result."""

    def test_full_path_state_advance(self):
        action_type = "click_play"
        category = classify_action_category(action_type)
        profile = derive_expected_outcome_profile(action_type)
        v = build_verification("not_in_game", True, "in_game", action_type)
        assert category == "navigation"
        assert profile["action_family"] == "state_advance"
        assert v.action_category == "navigation"
        assert v.action_family == "state_advance"
        assert v.delivery_status == "delivered"
        assert v.outcome_status == "confirmed"

    def test_full_path_observability(self):
        action_type = "inspect_screen"
        category = classify_action_category(action_type)
        profile = derive_expected_outcome_profile(action_type)
        v = build_verification("not_in_game", True, "not_in_game", action_type)
        assert category == "navigation"
        assert profile["action_family"] == "observability"
        assert v.action_category == "navigation"
        assert v.action_family == "observability"
        assert v.delivery_status == "delivered"
        assert v.outcome_status == "unknown"

    def test_full_path_in_game_effect(self):
        action_type = "play_card"
        category = classify_action_category(action_type)
        profile = derive_expected_outcome_profile(action_type)
        v = build_verification("in_game", True, "in_game", action_type)
        assert category == "in_game"
        assert profile["action_family"] == "in_game_effect"
        assert v.action_category == "in_game"
        assert v.action_family == "in_game_effect"
        assert v.delivery_status == "delivered"
        assert v.outcome_status == "unknown"

    def test_full_path_state_may_advance(self):
        action_type = "click_ready"
        category = classify_action_category(action_type)
        profile = derive_expected_outcome_profile(action_type)
        v = build_verification("not_in_game", True, "not_in_game", action_type)
        assert category == "navigation"
        assert profile["action_family"] == "state_may_advance"
        assert v.action_family == "state_may_advance"
        assert v.outcome_status == "unknown"
        assert v.outcome_status != "not_confirmed"
