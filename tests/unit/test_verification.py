"""Unit tests for action-aware coarse verification with expected outcome profiles.

These tests protect against regressions that would:
- Treat execute success as outcome confirmed
- Show "verified" when outcome is only unknown
- Treat in-game action + unchanged coarse state as not_confirmed (should be unknown)
- Treat observability action unchanged as not_confirmed (should be unknown)
- Treat state_may_advance unchanged as not_confirmed (should be unknown)
- Hide missing pre-action state
- Misclassify action categories or families
"""


from uno_orchestrator.orchestrator import (
    build_verification,
    classify_action_category,
    derive_expected_outcome_profile,
    derive_observability_improvement,
)

# --- classify_action_category tests ---

def test_category_navigation():
    assert classify_action_category("click_play") == "navigation"

def test_category_in_game():
    assert classify_action_category("play_card") == "in_game"

def test_category_unknown():
    assert classify_action_category("some_weird_action") == "unknown"

def test_category_none():
    assert classify_action_category(None) == "unknown"

def test_category_click_prefix():
    assert classify_action_category("click_start_match") == "navigation"

def test_category_draw_card():
    assert classify_action_category("draw_card") == "in_game"

def test_category_call_uno():
    assert classify_action_category("call_uno") == "in_game"


# --- derive_expected_outcome_profile tests ---

def test_profile_state_advance():
    p = derive_expected_outcome_profile("click_play")
    assert p["action_family"] == "state_advance"
    assert p["expectation_strength"] == "strong"

def test_profile_state_may_advance():
    p = derive_expected_outcome_profile("click_ready")
    assert p["action_family"] == "state_may_advance"
    assert p["expectation_strength"] == "soft"

def test_profile_observability():
    p = derive_expected_outcome_profile("inspect_screen")
    assert p["action_family"] == "observability"
    assert p["expectation_strength"] == "soft"

def test_profile_observability_focus():
    p = derive_expected_outcome_profile("focus_game_window")
    assert p["action_family"] == "observability"

def test_profile_in_game_effect():
    p = derive_expected_outcome_profile("play_card")
    assert p["action_family"] == "in_game_effect"
    assert p["expectation_strength"] == "unknown"

def test_profile_in_game_draw():
    p = derive_expected_outcome_profile("draw_card")
    assert p["action_family"] == "in_game_effect"

def test_profile_unknown_action():
    p = derive_expected_outcome_profile("totally_random")
    assert p["action_family"] == "unknown"

def test_profile_none_action():
    p = derive_expected_outcome_profile(None)
    assert p["action_family"] == "unknown"

def test_profile_unknown_click_prefix():
    p = derive_expected_outcome_profile("some_custom_click_action")
    assert p["action_family"] == "state_advance"

def test_profile_unknown_inspect_prefix():
    p = derive_expected_outcome_profile("some_inspect_thing")
    assert p["action_family"] == "observability"


# --- state_advance family tests ---

def test_state_advance_confirmed():
    v = build_verification("not_in_game", True, "in_game", "click_play")
    assert v.action_family == "state_advance"
    assert v.outcome_status == "confirmed"
    assert "state advance confirmed" in v.summary.lower()

def test_state_advance_not_confirmed():
    v = build_verification("not_in_game", True, "not_in_game", "click_play")
    assert v.action_family == "state_advance"
    assert v.outcome_status == "not_confirmed"
    assert "unchanged" in v.summary.lower()


# --- state_may_advance family tests ---

def test_state_may_advance_confirmed():
    v = build_verification("not_in_game", True, "in_game", "click_ready")
    assert v.action_family == "state_may_advance"
    assert v.outcome_status == "confirmed"

def test_state_may_advance_unchanged_is_unknown():
    v = build_verification("not_in_game", True, "not_in_game", "click_ready")
    assert v.action_family == "state_may_advance"
    assert v.outcome_status == "unknown"
    assert v.outcome_status != "not_confirmed"


# --- observability family tests ---

def test_observability_unchanged_is_unknown():
    v = build_verification("not_in_game", True, "not_in_game", "inspect_screen")
    assert v.action_family == "observability"
    assert v.outcome_status == "unknown"

def test_observability_changed_is_confirmed():
    v = build_verification("unknown", True, "not_in_game", "inspect_screen")
    assert v.action_family == "observability"
    assert v.outcome_status == "confirmed"

def test_observability_focus_unchanged():
    v = build_verification("not_in_game", True, "not_in_game", "focus_game_window")
    assert v.action_family == "observability"
    assert v.outcome_status == "unknown"


# --- in_game_effect family tests ---

def test_in_game_effect_unchanged_is_unknown():
    v = build_verification("in_game", True, "in_game", "play_card")
    assert v.action_family == "in_game_effect"
    assert v.outcome_status == "unknown"
    assert "not confirmable" in v.summary.lower()

def test_in_game_effect_draw_card_unchanged():
    v = build_verification("in_game", True, "in_game", "draw_card")
    assert v.action_family == "in_game_effect"
    assert v.outcome_status == "unknown"

def test_in_game_effect_state_changed():
    v = build_verification("in_game", True, "not_in_game", "play_card")
    assert v.action_family == "in_game_effect"
    assert v.outcome_status == "confirmed"


# --- Backward-compatible tests ---

def test_delivered_confirmed_no_action():
    v = build_verification("not_in_game", True, "in_game")
    assert v.delivery_status == "delivered"
    assert v.outcome_status == "confirmed"
    assert v.action_family == "unknown"

def test_delivered_not_confirmed_no_action():
    v = build_verification("not_in_game", True, "not_in_game")
    assert v.delivery_status == "delivered"
    assert v.outcome_status == "not_confirmed"


# --- Failure and edge cases ---

def test_failed_unknown():
    v = build_verification("in_game", False, "in_game", "play_card")
    assert v.delivery_status == "failed"
    assert v.outcome_status == "unknown"
    assert "failed" in v.summary.lower()

def test_delivered_unknown_post():
    v = build_verification("not_in_game", True, "unknown", "click_play")
    assert v.delivery_status == "delivered"
    assert v.outcome_status == "unknown"

def test_no_pre_action_state():
    v = build_verification(None, None, "in_game", "play_card")
    assert v.delivery_status == "unknown"
    assert v.outcome_status == "unknown"
    assert "no pre-action" in v.summary.lower()

def test_execute_result_unknown():
    v = build_verification("in_game", None, "in_game", "play_card")
    assert v.delivery_status == "unknown"
    assert v.outcome_status == "unknown"


# --- Regression safety tests ---

def test_in_game_unchanged_not_not_confirmed():
    v = build_verification("in_game", True, "in_game", "play_card")
    assert v.outcome_status != "not_confirmed"

def test_observability_unchanged_not_not_confirmed():
    v = build_verification("not_in_game", True, "not_in_game", "inspect_screen")
    assert v.outcome_status != "not_confirmed"

def test_state_may_advance_unchanged_not_not_confirmed():
    v = build_verification("not_in_game", True, "not_in_game", "click_ready")
    assert v.outcome_status != "not_confirmed"

def test_unknown_post_state_not_confirmed():
    v = build_verification("not_in_game", True, "unknown")
    assert v.outcome_status == "unknown"
    assert v.outcome_status != "confirmed"

def test_summary_not_misleading():
    v = build_verification("not_in_game", True, "in_game", "click_play")
    assert "verified" not in v.summary.lower()

def test_action_family_always_present():
    for args in [
        (None, None, "in_game", None),
        ("in_game", True, "in_game", "play_card"),
        ("not_in_game", True, "in_game", "click_play"),
        ("in_game", False, "in_game", "play_card"),
        ("not_in_game", True, "not_in_game", "inspect_screen"),
        ("not_in_game", True, "not_in_game", "click_ready"),
    ]:
        v = build_verification(*args)
        assert v.action_family in ("state_advance", "state_may_advance", "observability", "in_game_effect", "unknown")

def test_expected_transition_reflects_family():
    v = build_verification("not_in_game", True, "not_in_game", "click_play")
    assert "state advance expected" in v.expected_transition.lower()

    v2 = build_verification("not_in_game", True, "not_in_game", "inspect_screen")
    assert "observability" in v2.expected_transition.lower()

    v3 = build_verification("in_game", True, "in_game", "play_card")
    assert "may stay" in v3.expected_transition.lower()


# --- derive_observability_improvement tests ---


def test_obs_improvement_unknown_to_known():
    r = derive_observability_improvement("unknown", "not_in_game", None, None, False, False)
    assert r["improved"] is True
    assert "unknown_to_known" in r["signals"]
    assert r["strength"] == "strong"

def test_obs_improvement_confidence_jump():
    r = derive_observability_improvement("not_in_game", "not_in_game", 0.35, 0.81, False, False)
    assert r["improved"] is True
    assert "confidence_increased" in r["signals"]
    assert r["strength"] == "weak"

def test_obs_improvement_error_cleared():
    r = derive_observability_improvement("not_in_game", "not_in_game", None, None, True, False)
    assert r["improved"] is True
    assert "error_cleared" in r["signals"]
    assert r["strength"] == "weak"

def test_obs_improvement_multiple_signals():
    r = derive_observability_improvement("unknown", "not_in_game", 0.3, 0.8, True, False)
    assert r["improved"] is True
    assert len(r["signals"]) == 3
    assert r["strength"] == "moderate"

def test_obs_improvement_no_change():
    r = derive_observability_improvement("not_in_game", "not_in_game", 0.7, 0.72, False, False)
    assert r["improved"] is False
    assert r["signals"] == []
    assert r["strength"] == "none"

def test_obs_improvement_tiny_confidence_below_threshold():
    r = derive_observability_improvement("not_in_game", "not_in_game", 0.70, 0.72, False, False)
    assert r["improved"] is False

def test_obs_improvement_no_confidence_data():
    r = derive_observability_improvement("not_in_game", "not_in_game", None, None, False, False)
    assert r["improved"] is False
    assert r["signals"] == []


# --- Observability signals in build_verification ---

def test_observability_confirmed_by_state_change():
    v = build_verification("unknown", True, "not_in_game", "inspect_screen")
    assert v.outcome_status == "confirmed"
    assert v.observability_signals is not None
    assert "unknown_to_known" in v.observability_signals

def test_observability_confirmed_by_confidence_jump():
    v = build_verification("not_in_game", True, "not_in_game", "inspect_screen",
                           pre_confidence=0.3, post_confidence=0.8)
    assert v.outcome_status == "unknown"
    assert v.observability_signals is not None
    assert "confidence_increased" in v.observability_signals
    assert v.evidence_strength == "weak"

def test_observability_weak_signal_stays_unknown():
    v = build_verification("not_in_game", True, "not_in_game", "inspect_screen",
                           pre_confidence=0.7, post_confidence=0.72)
    assert v.outcome_status == "unknown"
    assert v.observability_signals is None or len(v.observability_signals) == 0

def test_observability_moderate_signal_confirmed():
    v = build_verification("not_in_game", True, "not_in_game", "inspect_screen",
                           pre_confidence=0.3, post_confidence=0.8,
                           pre_had_error=True, post_has_error=False)
    assert v.outcome_status == "confirmed"
    assert v.observability_signals is not None
    assert len(v.observability_signals) >= 2

def test_observability_signals_only_for_observability_family():
    v = build_verification("in_game", True, "in_game", "play_card",
                           pre_confidence=0.3, post_confidence=0.8)
    assert v.observability_signals is None
    assert v.evidence_strength is None
