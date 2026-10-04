"""Wild-colour strategy — the single rule shared by the orchestrator prompt
branch and the decision-service heuristic (gap #1: "pick a winning colour")."""

import pytest

from uno_shared.wild_color import (
    WILD_COLOR_ORDER,
    choose_wild_color,
    color_counts,
    score_wild_color,
)


# ── color_counts ─────────────────────────────────────────────────────────────

def test_color_counts_counts_non_wild_only():
    hand = [
        {"color": "red", "value": "5"},
        {"color": "red", "value": "2"},
        {"color": "green", "value": "9"},
        {"color": "wild", "value": "wild"},          # ignored
        {"color": "wild", "value": "wild_draw_four"},  # ignored
        {"color": "", "value": ""},                    # unreadable, ignored
        None,                                           # junk, ignored
    ]
    counts = color_counts(hand)
    assert counts["red"] == 2
    assert counts["green"] == 1
    assert counts["yellow"] == 0
    assert counts["blue"] == 0
    assert "wild" not in counts


def test_color_counts_empty_hand_gives_all_zero():
    counts = color_counts(None)
    assert counts == {c: 0 for c in WILD_COLOR_ORDER}


# ── score_wild_color ─────────────────────────────────────────────────────────

def test_score_bounded_by_three_cards():
    counts = {c: 0 for c in WILD_COLOR_ORDER}
    counts["green"] = 5
    # A 4th/5th green is no more useful than a 3rd. (approx: 0.1*3 isn't 0.3
    # in binary float.)
    assert score_wild_color("green", counts, None) == pytest.approx(0.3)


def test_top_match_bonus_applied():
    counts = {c: 0 for c in WILD_COLOR_ORDER}
    assert score_wild_color("blue", counts, "blue") == 0.05
    assert score_wild_color("blue", counts, "red") == 0.0


def test_score_rejects_unknown_colour():
    assert score_wild_color("purple", {c: 1 for c in WILD_COLOR_ORDER}, "red") == 0.0


# ── choose_wild_color ────────────────────────────────────────────────────────

def test_most_held_colour_wins():
    hand = [
        {"color": "green", "value": "1"},
        {"color": "green", "value": "7"},
        {"color": "blue", "value": "2"},
    ]
    color, reason = choose_wild_color(hand, top_color="red")
    assert color == "green"
    assert "green" in reason and "most" in reason


def test_hand_lead_outranks_top_match():
    # One green in hand must beat "continue the red sequence".
    hand = [{"color": "green", "value": "3"}]
    color, _ = choose_wild_color(hand, top_color="red")
    assert color == "green"


def test_empty_hand_continues_top_sequence():
    color, reason = choose_wild_color([], top_color="blue")
    assert color == "blue"
    assert "continue the blue sequence" in reason


def test_unreadable_everything_falls_back_to_red():
    color, reason = choose_wild_color(None, top_color=None)
    assert color == "red"
    assert "fallback" in reason


def test_deterministic_on_tie():
    # No hand, no top → same click every time (traces reproducible).
    first = choose_wild_color([], None)
    second = choose_wild_color([], None)
    assert first == second
    assert first[0] == "red"
