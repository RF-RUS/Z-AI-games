"""Tests for perceived legal actions (9d) — play the RIGHT card, not the leftmost.

Pure-function tests: legal moves come from the detected hand + top card via the
UNO match rule, so a chosen action carries the real card's colour+value. The
board in test_matches_real_screenshot mirrors the user's Ubisoft UNO frame
(top = yellow reverse; hand = red 6, green reverse, yellow reverse).
"""

from __future__ import annotations

from uno_orchestrator.perceived_actions import (
    _to_card,
    choose_prompt,
    choose_prompt_with_strategy,
    decide_drawn_play_or_keep,
    legal_actions_from_perception,
)
from uno_schemas.game import ActionType, CardColor, CardValue


def test_to_card_maps_aliases():
    c = _to_card({"color": "yellow", "value": "reverse"})
    assert c is not None and c.color == CardColor.YELLOW and c.value == CardValue.REVERSE
    assert _to_card({"color": "red", "value": "6"}).value == CardValue.SIX
    assert _to_card({"color": "wild", "value": "+4"}).value == CardValue.WILD_DRAW_FOUR


def test_to_card_rejects_unreadable():
    assert _to_card({"color": "red", "value": ""}) is None       # colour-only
    assert _to_card({"color": "", "value": "6"}) is None          # no colour
    assert _to_card({"color": "chartreuse", "value": "6"}) is None
    assert _to_card("nope") is None


def test_matches_real_screenshot_board():
    """User's frame: top yellow reverse; hand red6 / green reverse / yellow reverse.

    Playable = green reverse (value match) + yellow reverse (colour+value). Red 6
    does not match. DRAW is always present. Each play action carries its card.
    """
    top = {"color": "yellow", "value": "reverse"}
    hand = [
        {"color": "red", "value": "6"},
        {"color": "green", "value": "reverse"},
        {"color": "yellow", "value": "reverse"},
    ]
    actions = legal_actions_from_perception(hand, top)
    assert actions is not None
    plays = [a for a in actions if a.action_type == ActionType.PLAY_CARD]
    draws = [a for a in actions if a.action_type == ActionType.DRAW_CARD]
    assert len(draws) == 1
    played = {(a.card.color.value, a.card.value.value) for a in plays}
    assert played == {("green", "reverse"), ("yellow", "reverse")}
    # red 6 (no match) must NOT be offered as a play
    assert ("red", "6") not in played


def test_wild_always_playable():
    top = {"color": "red", "value": "6"}
    hand = [{"color": "wild", "value": "wild"}, {"color": "blue", "value": "2"}]
    actions = legal_actions_from_perception(hand, top)
    played = {(a.card.color.value, a.card.value.value)
              for a in actions if a.action_type == ActionType.PLAY_CARD}
    assert ("wild", "wild") in played
    assert ("blue", "2") not in played  # no colour/value match to red 6


def test_falls_back_when_board_unreadable():
    """No top card, empty hand, or fully unreadable hand → None (use the engine)."""
    assert legal_actions_from_perception(None, {"color": "red", "value": "6"}) is None
    assert legal_actions_from_perception([{"color": "red", "value": "6"}], None) is None
    # no colours at all → still nothing to decide from
    assert legal_actions_from_perception(
        [{"color": "", "value": ""}, {"color": "chartreuse", "value": "x"}],
        {"color": "red", "value": "6"},
    ) is None


# --- colour-only perception (VLM down, heuristic CV read colours) -------------
# Regression for session de3856d6: values were "unknown" in every cycle, so the
# old code returned None and the decision went to the desynced simulator, which
# demanded cards absent from the real hand → adapter refused / hung 12s.


def _hand(*colors):
    return [{"color": c, "value": "unknown"} for c in colors]


def test_color_only_offers_colour_match_not_simulator():
    """Cycle 2 of de3856d6: top green, hand has greens but NO blues.

    The old path produced play blue 3 (simulated hand). Now the decision may
    only name what is on screen: the green, plus draw. No blue anywhere.
    """
    actions = legal_actions_from_perception(
        _hand("red", "green", "green", "yellow", "yellow", "yellow", "yellow"),
        {"color": "green", "value": "0"},
    )
    assert actions is not None
    played = {(a.card.color.value, a.card.value.value) for a in actions if a.action_type == ActionType.PLAY_CARD}
    draws = [a for a in actions if a.action_type == ActionType.DRAW_CARD]
    assert len(draws) == 1
    assert ("blue", "3") not in played  # the simulator's phantasm must be gone
    assert played == {("green", "unknown")}  # one representative per colour
    # the chosen action names CardValue.UNKNOWN — provenance, never a deck card
    play = next(a for a in actions if a.action_type == ActionType.PLAY_CARD)
    assert play.card.color == CardColor.GREEN
    assert play.card.value.value == "unknown"


def test_color_only_no_match_still_returns_draw():
    """Hand with no card matching the top colour → [DRAW], never None.

    The board IS readable (colours known) — "nothing playable" is a real answer
    (draw), not an excuse to hand the decision to the desynced simulator, which
    would demand a phantom card that can't be grounded (de3856d6 error).
    """
    actions = legal_actions_from_perception(
        _hand("red", "yellow"),
        {"color": "blue", "value": "7"},
    )
    assert actions is not None
    assert [a.action_type for a in actions] == [ActionType.DRAW_CARD]


def test_color_only_multiple_colours_deduped():
    """Two greens in hand → one play action, not two."""
    actions = legal_actions_from_perception(
        _hand("green", "green", "green"),
        {"color": "green", "value": "reverse"},
    )
    plays = [a for a in actions if a.action_type == ActionType.PLAY_CARD]
    assert len(plays) == 1


def test_color_only_top_with_bad_color_returns_none():
    """Perceived top card with an unparseable colour → can't match, defer."""
    assert legal_actions_from_perception(
        _hand("red"),
        {"color": "purple", "value": "7"},
    ) is None


def test_readable_values_still_use_exact_rules():
    """Mixed hand where some values ARE readable: exact-value rules still apply,
    AND the colour-only neighbour is a distinct physical card — it is NOT shadowed
    by the readable one. Both a red 6 and a red-unknown are red, and grounding
    (`_find_card_center`) resolves a colour-only decision to the unreadable
    candidate's own measured coordinate. So the decision offers both."""
    actions = legal_actions_from_perception(
        [
            {"color": "red", "value": "6"},       # readable, matches by colour
            {"color": "red", "value": "unknown"}, # colour-only neighbour (CV recovered)
        ],
        {"color": "red", "value": "6"},
    )
    played = {(a.card.color.value, a.card.value.value) for a in actions if a.action_type == ActionType.PLAY_CARD}
    assert played == {("red", "6"), ("red", "unknown")}


def test_recovered_hand_collapse_case():
    """Regression for the 2026-08-28 live failure: the 3b VLM collapsed a 9-card
    hand to a single card (red 7, identical to the top) while CV measured 9 slots.
    After CV count-recovery the hand is mixed: 1 readable + N colour-only cards,
    each with a measured coordinate. The decision must offer the colour match of
    the recovered cards too, not just the single readable one."""
    hand = [
        {"color": "red", "value": "7", "center": {"x": 416, "y": 651}},   # VLM (readable)
        {"color": "red", "value": "unknown", "center": {"x": 300, "y": 655}},
        {"color": "green", "value": "unknown", "center": {"x": 500, "y": 648}},
        {"color": "blue", "value": "unknown", "center": {"x": 580, "y": 645}},
        {"color": "red", "value": "unknown", "center": {"x": 660, "y": 650}},
    ]
    actions = legal_actions_from_perception(hand, {"color": "red", "value": "7"})
    assert actions is not None
    plays = [a for a in actions if a.action_type == ActionType.PLAY_CARD]
    played = {(a.card.color.value, a.card.value.value) for a in plays}
    # red 7 (readable) and red-unknown (recovered, one representative per colour)
    assert played == {("red", "7"), ("red", "unknown")}
    # green / blue recovered cards do NOT match a red top
    assert ("green", "unknown") not in played and ("blue", "unknown") not in played


def test_no_playable_still_offers_draw():
    top = {"color": "red", "value": "6"}
    hand = [{"color": "green", "value": "2"}, {"color": "blue", "value": "9"}]
    actions = legal_actions_from_perception(hand, top)
    assert actions is not None
    assert [a.action_type for a in actions] == [ActionType.DRAW_CARD]


# --- choose_prompt (Play/Keep, colour picker, Continue) ---------------------


def test_choose_prompt_prefers_play_over_keep():
    prompts = [
        {"label": "Keep", "center": {"x": 1070, "y": 630}},
        {"label": "Play", "center": {"x": 768, "y": 630}},
    ]
    p = choose_prompt(prompts)
    assert p["label"] == "Play"


def test_choose_prompt_colour_picker():
    prompts = [
        {"label": "Red", "center": {"x": 1, "y": 1}},
        {"label": "Green", "center": {"x": 2, "y": 2}},
        {"label": "Blue", "center": {"x": 3, "y": 3}},
    ]
    assert choose_prompt(prompts, prefer_color="green")["label"] == "Green"


# --- decide_drawn_play_or_keep (game strategy for the Play/Keep prompt) ------


def _play_keep_prompts():
    return [
        {"label": "Play", "center": {"x": 768, "y": 630}},
        {"label": "Keep", "center": {"x": 1070, "y": 630}},
    ]


class TestDecideDrawnPlayOrKeep:
    def test_readable_matching_number_played(self):
        action, reason = decide_drawn_play_or_keep(
            {"color": "red", "value": "5"}, {"color": "red", "value": "2"}
        )
        assert action == "play"
        assert "matches top red 2" in reason

    def test_non_matching_colour_kept(self):
        action, reason = decide_drawn_play_or_keep(
            {"color": "blue", "value": "5"}, {"color": "red", "value": "2"}
        )
        assert action == "keep"
        assert "does not match" in reason

    def test_unreadable_drawn_card_kept(self):
        action, reason = decide_drawn_play_or_keep(
            {"color": "", "value": ""}, {"color": "red", "value": "2"}
        )
        assert action == "keep"
        assert "unreadable" in reason

    def test_action_card_played_for_pressure(self):
        action, reason = decide_drawn_play_or_keep(
            {"color": "green", "value": "+2"}, {"color": "green", "value": "4"}
        )
        assert action == "play"
        assert "action card" in reason

    def test_wild_hoarded_when_hand_can_play(self):
        action, reason = decide_drawn_play_or_keep(
            {"color": "wild", "value": "wild"},
            {"color": "red", "value": "2"},
            [{"color": "red", "value": "7"}],
        )
        assert action == "keep"
        assert "hoard" in reason and "red 7" in reason

    def test_wild_spent_when_nothing_else_plays(self):
        action, _ = decide_drawn_play_or_keep(
            {"color": "wild", "value": "wild"},
            {"color": "red", "value": "2"},
            [{"color": "blue", "value": "9"}],
        )
        assert action == "play"

    def test_reverse_by_value_match_played(self):
        action, _ = decide_drawn_play_or_keep(
            {"color": "blue", "value": "reverse"}, {"color": "red", "value": "reverse"}
        )
        assert action == "play"


class TestChoosePromptWithStrategy:
    def test_matching_drawn_card_clicks_play(self):
        button, reason = choose_prompt_with_strategy(
            _play_keep_prompts(),
            top_card={"color": "red", "value": "2"},
            drawn_card={"color": "red", "value": "5"},
        )
        assert button is not None and button["label"] == "Play"
        assert reason  # the verdict must be surfaced

    def test_non_matching_drawn_card_clicks_keep(self):
        button, reason = choose_prompt_with_strategy(
            _play_keep_prompts(),
            top_card={"color": "red", "value": "2"},
            drawn_card={"color": "blue", "value": "5"},
        )
        assert button is not None and button["label"] == "Keep"
        assert "does not match" in reason

    def test_wild_hoard_clicks_keep_over_static_play_priority(self):
        """The old static priority always clicked Play first. Strategy must not."""
        button, _ = choose_prompt_with_strategy(
            _play_keep_prompts(),
            top_card={"color": "red", "value": "2"},
            hand_cards=[{"color": "red", "value": "7"}],
            drawn_card={"color": "wild", "value": "wild"},
        )
        assert button is not None and button["label"] == "Keep"

    def test_variant_labels_resolved(self):
        prompts = [
            {"label": "Play Card", "center": {"x": 1, "y": 1}},
            {"label": "Keep in Hand", "center": {"x": 2, "y": 2}},
        ]
        button, _ = choose_prompt_with_strategy(
            prompts,
            top_card={"color": "red", "value": "2"},
            drawn_card={"color": "blue", "value": "5"},
        )
        assert button is not None and button["label"] == "Keep in Hand"

    def test_only_one_button_visible_uses_legacy_choice(self):
        """Not a dilemma — progress with whatever is on screen (old behaviour)."""
        prompts = [{"label": "Continue", "center": {"x": 5, "y": 5}}]
        button, reason = choose_prompt_with_strategy(prompts)
        assert button is not None and button["label"] == "Continue"
        assert reason == ""

    def test_missing_buttons_return_none(self):
        assert choose_prompt_with_strategy(None) == (None, "")
        assert choose_prompt_with_strategy([]) == (None, "")
        assert choose_prompt_with_strategy([{"label": "Play"}]) == (None, "")  # no center


# --- Wild colour picker (gap #1: strategy picks the colour, not the first one) -


def _color_picker_prompts(*labels):
    return [
        {"label": label, "center": {"x": i * 100, "y": 400}}
        for i, label in enumerate(labels)
    ]


class TestChoosePromptColorPickerStrategy:
    def test_most_held_colour_in_hand_is_clicked(self):
        prompts = _color_picker_prompts("Red", "Yellow", "Green", "Blue")
        hand = [
            {"color": "green", "value": "2"},
            {"color": "green", "value": "7"},
            {"color": "blue", "value": "9"},
        ]
        button, reason = choose_prompt_with_strategy(
            prompts, hand_cards=hand, top_card={"color": "red", "value": "2"}
        )
        assert button is not None and button["label"] == "Green"
        assert "most of any colour" in reason

    def test_empty_hand_continues_top_sequence(self):
        # Listed red-first: the old static preference clicked "Red".
        # Strategy must follow the top card's colour instead.
        prompts = _color_picker_prompts("Red", "Yellow", "Green", "Blue")
        button, reason = choose_prompt_with_strategy(
            prompts, hand_cards=[], top_card={"color": "blue", "value": "9"}
        )
        assert button is not None and button["label"] == "Blue"
        assert "continue the blue sequence" in reason

    def test_hand_lead_outranks_top_match(self):
        prompts = _color_picker_prompts("Red", "Yellow", "Green", "Blue")
        button, _ = choose_prompt_with_strategy(
            prompts,
            hand_cards=[{"color": "yellow", "value": "3"}],
            top_card={"color": "red", "value": "2"},
        )
        assert button is not None and button["label"] == "Yellow"

    def test_preferred_colour_not_perceived_falls_back_to_first_available(self):
        # Hand wants green, but the VLM only saw Red/Blue buttons.
        prompts = _color_picker_prompts("Red", "Blue")
        button, reason = choose_prompt_with_strategy(
            prompts,
            hand_cards=[{"color": "green", "value": "2"}],
            top_card={"color": "red", "value": "2"},
        )
        assert button is not None and button["label"] == "Red"
        assert "not perceived" in reason

    def test_single_colour_button_is_not_a_picker(self):
        # One colour button is just a button — legacy choice, no strategy.
        prompts = [{"label": "Green", "center": {"x": 1, "y": 1}}]
        button, reason = choose_prompt_with_strategy(
            prompts, hand_cards=[{"color": "blue", "value": "9"}]
        )
        assert button is not None and button["label"] == "Green"
        assert reason == ""

    def test_play_keep_dilemma_still_takes_priority_over_colours(self):
        # A screen with both Play and Keep plus stray colour labels is the
        # dilemma, not a picker.
        prompts = _color_picker_prompts("Red", "Green") + [
            {"label": "Play", "center": {"x": 768, "y": 630}},
            {"label": "Keep", "center": {"x": 1070, "y": 630}},
        ]
        button, _ = choose_prompt_with_strategy(
            prompts,
            top_card={"color": "red", "value": "2"},
            drawn_card={"color": "red", "value": "5"},
        )
        assert button is not None and button["label"] == "Play"


def test_choose_prompt_none_without_coords_or_prompts():
    assert choose_prompt(None) is None
    assert choose_prompt([]) is None
    assert choose_prompt([{"label": "Play"}]) is None  # no center → not clickable
