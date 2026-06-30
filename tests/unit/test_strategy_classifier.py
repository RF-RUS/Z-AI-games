"""Unit tests for screen-state classifier, goal derivation, and next-action derivation.

These tests protect against regressions that would:
- Re-add launcher/menu/lobby states without VLM
- Make planner claim actions without sufficient data
- Hide unknown states under false certainty
"""

from unittest.mock import MagicMock

from uno_orchestrator.orchestrator import classify_screen_state, derive_goal, derive_next_action

# --- classify_screen_state tests ---

def test_in_game_by_game_state():
    """Observation with game_state → in_game."""
    obs = MagicMock()
    obs.game_state = {"top_card": {"color": "red", "value": "5"}}
    obs.game_elements = None
    assert classify_screen_state(obs, has_adapter=True) == "in_game"


def test_in_game_by_game_elements():
    """Observation with game_elements but no game_state → in_game."""
    obs = MagicMock()
    obs.game_state = None
    obs.game_elements = [{"color": "blue", "value": "3"}]
    assert classify_screen_state(obs, has_adapter=True) == "in_game"


def test_not_in_game():
    """Adapter attached, observation present, but no game_state → not_in_game."""
    obs = MagicMock()
    obs.game_state = None
    obs.game_elements = None
    assert classify_screen_state(obs, has_adapter=True) == "not_in_game"


def test_unknown_no_adapter():
    """No adapter attached → unknown."""
    obs = MagicMock()
    obs.game_state = None
    obs.game_elements = None
    assert classify_screen_state(obs, has_adapter=False) == "unknown"


def test_unknown_no_observation():
    """No observation at all → unknown."""
    assert classify_screen_state(None, has_adapter=False) == "unknown"
    assert classify_screen_state(None, has_adapter=True) == "not_in_game"


def test_no_false_launcher_menu_lobby():
    """Classifier must NOT produce launcher/menu/lobby states."""
    obs = MagicMock()
    obs.game_state = None
    obs.game_elements = None
    result = classify_screen_state(obs, has_adapter=True)
    assert result in ("in_game", "not_in_game", "unknown")
    assert result != "launcher"
    assert result != "menu"
    assert result != "lobby"


def test_grace_period_maintains_in_game():
    """If previous state was in_game and observation exists but game_state is None,
    classifier maintains in_game (grace period for transient DOM gaps)."""
    obs = MagicMock()
    obs.game_state = None
    obs.game_elements = None
    result = classify_screen_state(obs, has_adapter=True, previous_state="in_game")
    assert result == "in_game"


def test_grace_period_does_not_apply_without_observation():
    """Grace period requires observation to be present."""
    result = classify_screen_state(None, has_adapter=True, previous_state="in_game")
    assert result == "not_in_game"


def test_grace_period_does_not_apply_for_unknown_previous():
    """Grace period only activates when previous was in_game."""
    obs = MagicMock()
    obs.game_state = None
    obs.game_elements = None
    result = classify_screen_state(obs, has_adapter=True, previous_state="not_in_game")
    assert result == "not_in_game"


# --- derive_goal tests ---

def test_goal_from_decision():
    """When decision exists, use explanation.summary."""
    decision = MagicMock()
    decision.explanation.summary = "Heuristic chose play_card"
    assert derive_goal(decision, "in_game", True) == "Heuristic chose play_card"


def test_goal_in_game_no_decision():
    """in_game without decision → Play the game."""
    assert derive_goal(None, "in_game", True) == "Play the game"


def test_goal_not_in_game():
    """not_in_game → Reach game state."""
    assert derive_goal(None, "not_in_game", True) == "Reach game state"


def test_goal_no_steps():
    """No steps → Initialize session."""
    assert derive_goal(None, "unknown", False) == "Initialize session"


def test_goal_with_steps():
    """Has steps but no decision → Pipeline active."""
    assert derive_goal(None, "unknown", True) == "Pipeline active"


# --- derive_next_action tests ---

def test_next_action_from_decision():
    """When decision exists, use chosen_action."""
    decision = MagicMock()
    decision.chosen_action.action_type.value = "play_card"
    assert derive_next_action(decision, "in_game") == "play_card"


def test_next_action_not_in_game():
    """not_in_game without decision → Inspect screen."""
    assert derive_next_action(None, "not_in_game") == "Inspect screen"


def test_next_action_in_game_no_decision():
    """in_game without decision → Awaiting decision."""
    assert derive_next_action(None, "in_game") == "Awaiting decision"


def test_next_action_unknown():
    """unknown → None."""
    assert derive_next_action(None, "unknown") is None


# --- Regression safety tests ---

def test_no_fake_precision_in_unknown_state():
    """When state is unknown, goal and next_action must not claim specific knowledge."""
    goal = derive_goal(None, "unknown", False)
    next_action = derive_next_action(None, "unknown")
    assert "Click" not in goal
    assert "Ready" not in goal
    assert "Start" not in goal
    assert next_action is None


def test_not_in_game_does_not_claim_in_game_actions():
    """not_in_game must not produce in-game actions."""
    goal = derive_goal(None, "not_in_game", True)
    next_action = derive_next_action(None, "not_in_game")
    assert "Play the game" not in goal
    assert "play_card" not in (next_action or "")
    assert next_action == "Inspect screen"
