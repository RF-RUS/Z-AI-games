"""Decision and policy guard tests."""


from uno_decision.policy import decide_heuristic
from uno_policy.guard import validate_chat_reply, validate_decision
from uno_schemas.chat import ChatReply
from uno_schemas.decision import DecisionExplanation, DecisionRequest, DecisionResult
from uno_schemas.game import ActionType, LegalAction
from uno_schemas.perception import Observation, ObservationConfidence


def _make_request(actions):
  return DecisionRequest(
    session_id="s1",
    observation=Observation(
      observation_id="o1",
      session_id="s1",
      timestamp_ms=0,
      confidence=ObservationConfidence(overall=0.9),
    ),
    legal_actions=actions,
    correlation_id="c1",
  )


def test_heuristic_prefers_play_over_draw():
  actions = [
    LegalAction(action_type=ActionType.DRAW_CARD, player_id="p1", action_id="a1"),
    LegalAction(
      action_type=ActionType.PLAY_CARD,
      player_id="p1",
      card=None,
      action_id="a2",
    ),
  ]
  # Fix card for play action
  from uno_schemas.game import Card, CardColor, CardValue
  actions[1].card = Card(color=CardColor.RED, value=CardValue.FIVE)
  result = decide_heuristic(_make_request(actions))
  assert result.chosen_action.action_type == ActionType.PLAY_CARD


def test_policy_blocks_illegal():
  legal = [LegalAction(action_type=ActionType.DRAW_CARD, player_id="p1", action_id="a1")]
  decision = DecisionResult(
    chosen_action=LegalAction(action_type=ActionType.PASS, player_id="p1", action_id="bad"),
    confidence=0.9,
    explanation=DecisionExplanation(summary="test"),
    correlation_id="c1",
  )
  allowed, violation = validate_decision(decision, legal)
  assert not allowed
  assert violation is not None


def test_chat_policy_blocks_leak():
  reply = ChatReply(text="My hand has a red 5 hidden", correlation_id="c1")
  allowed, violations = validate_chat_reply(reply, "c1")
  assert not allowed
  assert any("leak" in v for v in violations)
