"""Heuristic and model-assist decision policies — game-agnostic.

The heuristic policy works with both LegalAction and GameAction via
duck-typing. Model-assist calls model-runtime-service for strategy advice.
"""

from __future__ import annotations

import json
import os
import random
import re
from typing import Any

import httpx
from uno_schemas.decision import (
    DecisionCandidate,
    DecisionExplanation,
    DecisionRequest,
    DecisionResult,
    ShadowComparison,
    StrategyId,
)
from uno_shared.logging import get_logger
from uno_shared.wild_color import choose_wild_color, score_wild_color, color_counts

# structlog, NOT logging.getLogger(): the project configures structlog to print to
# STDOUT, which is what lands in logs/<service>.log. A bare stdlib logger is never
# configured, so its records fall through to Python's lastResort handler — WARNING+
# only, unformatted, on STDERR. Every fallback below was therefore invisible in the
# service log, which is exactly how the perception-side failures went unnoticed for
# days. NOTE: structlog's warning() takes kwargs, NOT %s interpolation.
logger = get_logger("decision")

MODEL_RUNTIME_URL = os.getenv("MODEL_RUNTIME_URL", "http://127.0.0.1:8111")
MODEL_TIMEOUT_S = float(os.getenv("MODEL_TIMEOUT_S", "10"))


def _extract_json_object(text: str) -> str | None:
    """Pull the first valid JSON object from a model response.

    Mirrors uno_perception.vlm_provider._extract_json_object — the same two
    failure modes apply here: markdown code fences around the JSON, or a
    reasoning preamble when the model ignores /no_think.  Returns the raw
    JSON string (not parsed), or None if no {...} block can be found.
    """
    if not text:
        return None
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


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


def _score_action(action, wild_counts=None, wild_top_color=None) -> tuple[float, str]:
  """Score an action — game-agnostic heuristic.

  `wild_counts` / `wild_top_color` (computed once by `decide_heuristic`) let a
  wild play be ranked by the shared colour strategy: when the engine expands a
  wild into one action per colour (`chosen_color`), the most-held / top-matching
  colour wins instead of "first red in the list".
  """
  action_type = _get_action_type(action)
  card = _get_card_info(action)
  if wild_counts is None:
    wild_counts = {}

  if action_type in ("play_card", "play") and card:
    value = str(card.get("value", "")).lower() if isinstance(card.get("value"), str) else str(card.get("value", ""))
    color = str(card.get("color", "")).lower() if isinstance(card.get("color"), str) else str(card.get("color", ""))

    if "wild" in value and "draw" in value and "four" in value:
      score, why = 0.9, "aggressive wild draw four"
    elif "draw" in value and "two" in value:
      score, why = 0.85, "draw two pressure"
    elif color == "wild":
      score, why = 0.7, "wild flexibility"
    elif value in ("skip", "reverse"):
      score, why = 0.75, "skip/reverse tempo"
    elif value == "unknown":
      # Colour-only perception (VLM down): the hand was read by colour alone and
      # this action matched that colour against the top card. Scoring it just
      # "play card" (0.5) would make the heuristic prefer draw_card (0.55) and
      # stall the game forever — a known-colour play must beat a blind draw.
      score, why = 0.6, "colour-match play (value unreadable)"
    elif value.isdigit():
      score, why = 0.5 + (0.05 * int(value)), "number card"
    else:
      score, why = 0.5, "play card"

    # Wild plays: rank the per-colour variants by the shared strategy so the
    # most-held / sequence-continuing colour wins, not list order.
    if color == "wild":
      chosen = getattr(action, "chosen_color", None)
      chosen_color = chosen.value if hasattr(chosen, "value") else str(chosen or "").lower()
      bonus = score_wild_color(chosen_color, wild_counts, wild_top_color)
      if bonus > 0:
        score += bonus
        why = f"wild: set {chosen_color} ({why})"
    return score, why

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

def _wild_context(req: DecisionRequest) -> tuple[dict[str, int], str | None]:
  """(hand colour counts, top colour) from the perceived board, or empties.

  Feeds the wild-colour strategy in `_score_action`. When the observation has
  no readable hand/top (engine-only path) both come back empty and wild
  variants keep their flat score — same behaviour as before this strategy.
  """
  observation = req.observation
  gs = getattr(observation, "game_state", None) or {}
  hand_cards = gs.get("hand_cards") if isinstance(gs, dict) else None
  top = gs.get("top_card") if isinstance(gs, dict) else None
  top_color = None
  if isinstance(top, dict):
    tc = str(top.get("color") or "").lower().strip()
    top_color = tc or None
  return color_counts(hand_cards), top_color


def decide_heuristic(req: DecisionRequest) -> DecisionResult:
  wild_counts, wild_top_color = _wild_context(req)
  candidates: list[DecisionCandidate] = []
  for action in req.legal_actions:
    score, reason = _score_action(action, wild_counts, wild_top_color)
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
        # Explicit, because the policy JSON carries a free-text "reasoning"
        # field and profiles may default low (schema floor is 256): at 256 this
        # call came back with finish_reason=length and an EMPTY content, which
        # silently dropped every decision to the heuristic path.
        "max_tokens": 768,
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
        cleaned = _extract_json_object(model_text)
        if cleaned:
          try:
            structured = json.loads(cleaned)
          except json.JSONDecodeError:
            pass
      if not structured:
        logger.warning("model_response_parse_failed", text=model_text[:200])
        tracker.complete(record, success=False, fallback_used=True, fallback_reason="parse_failed", parse_success=False)
        return decide_heuristic(req)

    action_index = structured.get("action_index", 0)
    model_confidence = structured.get("confidence", 0.5)
    reasoning = structured.get("reasoning", "Model recommendation")

    # Validate action_index
    if 0 <= action_index < len(req.legal_actions):
      chosen_action = req.legal_actions[action_index]
    else:
      logger.warning("model_invalid_action_index", index=action_index, max=len(req.legal_actions) - 1)
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
    # Never str(exc) alone: httpx transport errors (ReadTimeout, ConnectError) have
    # an EMPTY str(), so the log would read `error=` and say nothing at all.
    logger.warning(
      "model_decision_failed",
      error=f"{type(exc).__name__}: {exc}",
      note="falling back to heuristic",
    )
    tracker.complete(record, success=False, fallback_used=True, fallback_reason=str(exc))
    return decide_heuristic(req)


# ── Shadow mode ──

async def _run_shadow(req: DecisionRequest, primary_result: DecisionResult) -> ShadowComparison | None:
  """Run the opposite strategy as a non-binding observer; never affects the result.

  The point of shadow mode is measuring disagreement before trusting a strategy:
  e.g. primary=heuristic, shadow=model_assist logs how often the model would have
  chosen a different card (and at what confidence), so promotion to primary is a
  data-backed decision instead of a vibe. Any shadow failure degrades silently —
  the primary decision must never be at risk because of an observer.
  """
  try:
    if req.strategy_id == StrategyId.MODEL_ASSIST:
      shadow_req = req.model_copy(update={"strategy_id": StrategyId.HEURISTIC, "use_model_assist": False})
      shadow_strategy = "heuristic"
      shadow_result = decide_heuristic(shadow_req)
    else:
      shadow_req = req.model_copy(update={"strategy_id": StrategyId.MODEL_ASSIST, "use_model_assist": True})
      shadow_strategy = "model_assist"
      shadow_result = await decide_model(shadow_req)
    shadow_action_id = getattr(shadow_result.chosen_action, "action_id", None)
    primary_action_id = getattr(primary_result.chosen_action, "action_id", None)
    agree = (
      shadow_action_id == primary_action_id
      or shadow_result.chosen_action.model_dump(mode="json") == primary_result.chosen_action.model_dump(mode="json")
    )
    logger.info(
      "shadow_comparison",
      primary_strategy=req.strategy_id.value,
      shadow_strategy=shadow_strategy,
      agree=agree,
      shadow_confidence=shadow_result.confidence,
      correlation_id=req.correlation_id,
    )
    return ShadowComparison(
      shadow_strategy=shadow_strategy,
      shadow_confidence=shadow_result.confidence,
      shadow_summary=shadow_result.explanation.summary if shadow_result.explanation else "",
      agree_with_primary=agree,
    )
  except Exception as exc:  # noqa: BLE001 — shadow is observational, never fatal
    logger.warning("shadow_failed", error=f"{type(exc).__name__}: {exc}")
    return None


# ── Main dispatch ──

async def decide(req: DecisionRequest) -> DecisionResult:
  """Route to appropriate strategy based on strategy_id."""
  if req.shadow_mode:
    base_req = req.model_copy(update={"shadow_mode": False})
    if base_req.strategy_id == StrategyId.RANDOM:
      primary = decide_random(base_req)
    elif base_req.strategy_id == StrategyId.MODEL_ASSIST or base_req.use_model_assist:
      primary = await _primary_with_model(base_req)
    else:
      primary = decide_heuristic(base_req)
    shadow = await _run_shadow(req, primary)
    if shadow is not None:
      primary = primary.model_copy(deep=True)
      primary.explanation = primary.explanation.model_copy(update={"shadow_comparison": shadow})
    return primary
  if req.strategy_id == StrategyId.RANDOM:
    return decide_random(req)
  if req.strategy_id == StrategyId.MODEL_ASSIST:
    return await decide_model(req)
  if req.use_model_assist:
    return await _primary_with_model(req)
  return decide_heuristic(req)


async def _primary_with_model(req: DecisionRequest) -> DecisionResult:
  """Heuristic-primary decision with the model as a secondary opinion."""
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
