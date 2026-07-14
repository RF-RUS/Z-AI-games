"""Heuristic and model-assist decision policies — game-agnostic.

The heuristic policy works with both LegalAction and GameAction via
duck-typing. Model-assist calls model-runtime-service for strategy advice.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any

import httpx
from uno_schemas.decision import (
  DecisionCandidate,
  DecisionExplanation,
  DecisionRequest,
  DecisionResult,
  StrategyId,
)

logger = logging.getLogger("decision")

MODEL_RUNTIME_URL = "http://127.0.0.1:8111"
MODEL_TIMEOUT_S = 10.0


def _get_action_type(action) -> str:
  """Get action type string from either LegalAction or GameAction."""
  at = getattr(action, 'action_type', None)
  if at is None:
    return "unknown"
  return at.value if hasattr(at, 'value') else str(at)


def _get_card_info(action) -> dict[str, Any] | None:
  """Extract card info from either LegalAction or GameAction."""
  card = getattr(action, 'card', None)
  if card is None:
    payload = getattr(action, 'payload', {})
    card = payload.get('card')
  if card is None:
    return None
  if isinstance(card, dict):
    return card
  return {
    "color": getattr(card, 'color', None),
    "value": getattr(card, 'value', None),
  }


def _score_action(action) -> tuple[float, str]:
  """Score an action — game-agnostic heuristic."""
  action_type = _get_action_type(action)
  card = _get_card_info(action)

  if action_type in ("play_card", "play") and card:
    value = str(card.get("value", "")).lower() if isinstance(card.get("value"), str) else str(card.get("value", ""))
    color = str(card.get("color", "")).lower() if isinstance(card.get("color"), str) else str(card.get("color", ""))

    if "wild" in value and "draw" in value and "four" in value:
      return 0.9, "aggressive wild draw four"
    if "draw" in value and "two" in value:
      return 0.85, "draw two pressure"
    if color == "wild":
      return 0.7, "wild flexibility"
    if value in ("skip", "reverse"):
      return 0.75, "skip/reverse tempo"
    if value.isdigit():
      return 0.5 + (0.05 * int(value)), "number card"
    return 0.5, "play card"

  if action_type in ("draw_card", "draw"):
    return 0.55, "draw card"
  if "call" in action_type or "uno" in action_type:
    return 0.95, "call special"
  if action_type in ("pass", "accept_penalty"):
    return 0.5, "pass/penalty"
  return 0.4, "other"


def _is_play_action(action) -> bool:
  action_type = _get_action_type(action)
  return action_type in ("play_card", "play")


def _format_actions_for_prompt(actions: list) -> str:
  """Format legal actions as readable text for model prompt."""
  lines = []
  for i, action in enumerate(actions):
    action_type = _get_action_type(action)
    card = _get_card_info(action)
    if card:
      lines.append(f"{i}: {action_type} ({card.get('color', '?')} {card.get('value', '?')})")
    else:
      lines.append(f"{i}: {action_type}")
  return "\n".join(lines)


def _format_state_for_prompt(observation: Any) -> str:
  """Format observation as readable text for model prompt."""
  if observation is None:
    return "No observation available"
  game_state = getattr(observation, 'game_state', None)
  if game_state:
    return json.dumps(game_state, default=str, indent=2)
  return str(observation)


# ── Heuristic strategy ──

def decide_heuristic(req: DecisionRequest) -> DecisionResult:
  candidates: list[DecisionCandidate] = []
  for action in req.legal_actions:
    score, reason = _score_action(action)
    candidates.append(DecisionCandidate(action=action, score=score, reason=reason))

  play_candidates = [c for c in candidates if _is_play_action(c.action)]
  chosen = max(play_candidates, key=lambda c: c.score) if play_candidates else max(candidates, key=lambda c: c.score)

  return DecisionResult(
    chosen_action=chosen.action,
    confidence=min(0.95, chosen.score),
    explanation=DecisionExplanation(
      summary=f"Heuristic chose {_get_action_type(chosen.action)}: {chosen.reason}",
      candidates=sorted(candidates, key=lambda c: -c.score)[:5],
    ),
    correlation_id=req.correlation_id,
  )


def decide_random(req: DecisionRequest) -> DecisionResult:
  action = random.choice(req.legal_actions)
  return DecisionResult(
    chosen_action=action,
    confidence=0.5,
    explanation=DecisionExplanation(summary="Random policy", candidates=[]),
    correlation_id=req.correlation_id,
  )


# ── Model-assisted strategy ──

async def decide_model(req: DecisionRequest) -> DecisionResult:
  """Call model-runtime-service for strategy advice, fall back to heuristic on failure."""
  from uno_shared.model_observability import get_usage_tracker
  tracker = get_usage_tracker()
  record = tracker.start(
    task="strategy",
    game_type=req.game_type or "unknown",
    provider="openai_compat",
    profile_id=req.model_profile_id,
    session_id=req.session_id,
    correlation_id=req.correlation_id,
  )

  try:
    game_state_text = _format_state_for_prompt(req.observation)
    actions_text = _format_actions_for_prompt(req.legal_actions)

    prompt_variables = {
      "game_state": game_state_text,
      "legal_actions": actions_text,
      "strategy_context": f"Game type: {getattr(req.observation, 'game_type', 'unknown')}",
    }

    async with httpx.AsyncClient(timeout=MODEL_TIMEOUT_S) as client:
      resp = await client.post(f"{MODEL_RUNTIME_URL}/invoke", json={
        "context": {
          "use_case": "policy_advice",
          "correlation_id": req.correlation_id,
          "session_id": req.session_id,
        },
        "profile_id": req.model_profile_id or None,
        "prompt_id": "policy_advice",
        "variables": prompt_variables,
        "expect_json": True,
      })
      resp.raise_for_status()
      result = resp.json()

    # Parse model response
    model_text = result.get("text", "")
    structured = result.get("structured") or {}
    if not structured and model_text:
      try:
        structured = json.loads(model_text)
      except json.JSONDecodeError:
        logger.warning("model_response_parse_failed text=%s", model_text[:200])
        tracker.complete(record, success=False, fallback_used=True, fallback_reason="parse_failed", parse_success=False)
        return decide_heuristic(req)

    action_index = structured.get("action_index", 0)
    model_confidence = structured.get("confidence", 0.5)
    reasoning = structured.get("reasoning", "Model recommendation")

    # Validate action_index
    if 0 <= action_index < len(req.legal_actions):
      chosen_action = req.legal_actions[action_index]
    else:
      logger.warning("model_invalid_action_index index=%d max=%d", action_index, len(req.legal_actions) - 1)
      tracker.complete(record, success=False, fallback_used=True, fallback_reason="invalid_action_index")
      return decide_heuristic(req)

    candidates = []
    for i, action in enumerate(req.legal_actions):
      is_chosen = i == action_index
      candidates.append(DecisionCandidate(
        action=action,
        score=model_confidence if is_chosen else 0.3,
        reason=reasoning if is_chosen else "not selected",
      ))

    tracker.complete(record, success=True, confidence=model_confidence)

    return DecisionResult(
      chosen_action=chosen_action,
      confidence=min(0.95, model_confidence),
      explanation=DecisionExplanation(
        summary=f"Model chose {_get_action_type(chosen_action)}: {reasoning}",
        candidates=sorted(candidates, key=lambda c: -c.score)[:5],
        model_used=True,
        model_id=result.get("model_id"),
      ),
      correlation_id=req.correlation_id,
    )

  except Exception as exc:
    logger.warning("model_decision_failed error=%s — falling back to heuristic", str(exc))
    tracker.complete(record, success=False, fallback_used=True, fallback_reason=str(exc))
    return decide_heuristic(req)


# ── Main dispatch ──

async def decide(req: DecisionRequest) -> DecisionResult:
  """Route to appropriate strategy based on strategy_id."""
  if req.strategy_id == StrategyId.RANDOM:
    return decide_random(req)
  if req.strategy_id == StrategyId.MODEL_ASSIST:
    return await decide_model(req)
  if req.use_model_assist:
    # Heuristic first, model as secondary opinion
    heuristic_result = decide_heuristic(req)
    try:
      model_result = await decide_model(req)
      # If model agrees with heuristic, use model's confidence
      if model_result.chosen_action == heuristic_result.chosen_action:
        return DecisionResult(
          chosen_action=heuristic_result.chosen_action,
          confidence=max(heuristic_result.confidence, model_result.confidence),
          explanation=DecisionExplanation(
            summary=f"Heuristic + model agree: {_get_action_type(heuristic_result.chosen_action)}",
            candidates=heuristic_result.explanation.candidates,
            model_used=True,
            model_id=model_result.explanation.model_id,
          ),
          correlation_id=req.correlation_id,
        )
      # If model disagrees, use heuristic but note disagreement
      return DecisionResult(
        chosen_action=heuristic_result.chosen_action,
        confidence=heuristic_result.confidence,
        explanation=DecisionExplanation(
          summary=f"Heuristic chose {_get_action_type(heuristic_result.chosen_action)} (model suggested {_get_action_type(model_result.chosen_action)})",
          candidates=heuristic_result.explanation.candidates,
          model_used=True,
          model_id=model_result.explanation.model_id,
        ),
        correlation_id=req.correlation_id,
      )
    except Exception:
      return heuristic_result
  return decide_heuristic(req)
