"""Session lifecycle orchestration."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from uno_orchestrator.clients import ServiceClients, binding_for
from uno_orchestrator.flow_controller import FlowController, RuntimeSession
from uno_orchestrator.recovery import (
  classify_attach_error,
  decide_attach_recovery,
  format_exception_message,
)
from uno_orchestrator.state_machine import transition
from uno_orchestrator.web_attach_trace import log_attach_diagnostics_checkpoint
from uno_schemas.orchestrator import (
  AdapterBinding,
  AttachAdapterBody,
  DetectedCard,
  ErrorClass,
  FlowControlResponse,
  FlowState,
  OrchestratorStatus,
  RecoveryDecision,
  RecoveryMode,
  SessionDetail,
  SessionSpec,
  StrategySnapshot,
  VerificationResult,
)
from uno_schemas.session import AdapterType, SessionConfig, SessionPhase, SessionState
from uno_shared.adapter_registry import get_adapter_registry
from uno_shared.event_bus import BusEvent, get_event_bus
from uno_shared.logging import get_logger

logger = get_logger("orchestrator")


# --- Testable pure functions for classifier / planner ---
# These are extracted as module-level functions so they can be unit-tested
# without instantiating the full orchestrator.

def _to_detected_card(card: Any) -> DetectedCard | None:
  """Map a perception card dict → DetectedCard for the operator snapshot.

  Accepts the `recognition_to_dict` shape ({color, value, *_confidence, center}).
  Returns None for missing/empty input so callers can filter cleanly.
  """
  if not isinstance(card, dict):
    return None
  color = str(card.get("color") or "")
  value = str(card.get("value") or "")
  if not color and not value and not card.get("center"):
    return None
  center = card.get("center") if isinstance(card.get("center"), dict) else None
  return DetectedCard(
    color=color,
    value=value,
    color_confidence=card.get("color_confidence"),
    value_confidence=card.get("value_confidence"),
    center={"x": int(center["x"]), "y": int(center["y"])}
    if center and "x" in center and "y" in center else None,
  )

def classify_screen_state(
  observation: Any,
  has_adapter: bool,
  previous_state: str | None = None,
) -> str:
  """MVP screen-state classifier — rule-based, not VLM-based.

  Honest classification based on available observation data:
  - in_game: observation has game_state with data
  - not_in_game: adapter attached but no game_state (pre-game state)
  - unknown: no observation or no adapter

  Grace period: if previous state was in_game and current observation
  exists but game_state is temporarily absent (transient DOM gap during
  animation/re-render), maintain in_game for one cycle rather than
  switching to not_in_game. Only switch to not_in_game if we've been
  without game_state for 2+ consecutive cycles.
  """
  if observation and getattr(observation, "game_state", None):
    return "in_game"
  if observation and getattr(observation, "game_elements", None):
    return "in_game"

  if has_adapter and observation:
    if previous_state == "in_game":
      return "in_game"

  if has_adapter:
    return "not_in_game"
  return "unknown"


def derive_goal(decision: Any, detected_state: str, has_steps: bool) -> str:
  """Derive goal from decision or pre-game state."""
  if decision and hasattr(decision, "explanation") and decision.explanation:
    return decision.explanation.summary or "Decision made"
  if detected_state == "in_game":
    return "Play the game"
  if detected_state == "not_in_game":
    return "Reach game state"
  if not has_steps:
    return "Initialize session"
  return "Pipeline active"


def derive_next_action(decision: Any, detected_state: str) -> str | None:
  """Derive next action from decision or pre-game navigation."""
  if decision and hasattr(decision, "chosen_action") and decision.chosen_action:
    at = getattr(decision, "chosen_action", None)
    action_type = getattr(at, "action_type", None)
    return action_type.value if hasattr(action_type, "value") else str(action_type) if action_type else None
  if detected_state == "not_in_game":
    return "Inspect screen"
  if detected_state == "in_game":
    return "Awaiting decision"
  return None


# Extensible action category registry — games register their action types here
_NAVIGATION_ACTIONS: set[str] = {
  "focus_game_window", "click_play", "click_ready", "click_start",
  "inspect_screen", "attach", "navigate", "start_match", "join_match",
}
_IN_GAME_ACTIONS: set[str] = set()  # games register their in-game actions here


def register_action_categories(navigation: set[str] | None = None, in_game: set[str] | None = None) -> None:
  """Register game-specific action types for verification classification."""
  if navigation:
    _NAVIGATION_ACTIONS.update(navigation)
  if in_game:
    _IN_GAME_ACTIONS.update(in_game)


def classify_action_category(action_type: str | None) -> str:
  """Classify action type into a verification category.

  Categories determine how verification interprets coarse state changes:
  - navigation: pre-game actions where state change is expected
  - in_game: gameplay actions where coarse state may remain in_game (normal)
  - unknown: conservative default — no assumptions
  """
  if not action_type:
    return "unknown"
  if action_type in _NAVIGATION_ACTIONS:
    return "navigation"
  if action_type in _IN_GAME_ACTIONS:
    return "in_game"
  if "click" in action_type.lower() or "navigate" in action_type.lower() or "focus" in action_type.lower():
    return "navigation"
  return "unknown"


# Register UNO-specific action categories (reference implementation)
register_action_categories(
  in_game={"play_card", "draw_card", "pass", "pass_turn", "choose_color", "call_uno", "challenge", "accept_penalty"},
)


def derive_expected_outcome_profile(action_type: str | None, pre_state: str | None = None) -> dict:
  """Derive expected outcome profile for a given action type.

  Returns a profile that determines verification semantics:
  - action_family: the expected outcome family
  - expectation_strength: strong (state change required) | soft (may not change) | unknown
  - summary_hint: honest description of what verification can confirm

  Families:
  - state_advance: coarse state change IS the expected result (click_play, start_match)
  - state_may_advance: state may change but unchanged is not a failure (click_ready)
  - observability: goal is improved understanding, not state transition (inspect_screen, focus_game_window)
  - in_game_effect: in-game actions where coarse state naturally stays in_game
  - unknown: conservative default
  """
  if not action_type:
    return {
      "action_family": "unknown",
      "expectation_strength": "unknown",
      "summary_hint": "action type unknown",
    }

  state_advance_actions = {
    "click_play", "click_start", "start_match", "join_match", "navigate",
  }
  state_may_advance_actions = {
    "click_ready", "wait", "lobby",
  }
  observability_actions = {
    "inspect_screen", "focus_game_window", "attach", "capture_screenshot", "observe",
  }
  in_game_actions = {
    "play_card", "draw_card", "pass", "pass_turn", "choose_color",
    "call_uno", "challenge", "accept_penalty",
  }

  if action_type in state_advance_actions:
    return {
      "action_family": "state_advance",
      "expectation_strength": "strong",
      "summary_hint": "start-match action expected to advance coarse state",
    }
  if action_type in state_may_advance_actions:
    return {
      "action_family": "state_may_advance",
      "expectation_strength": "soft",
      "summary_hint": "ready action may advance state but unchanged is acceptable",
    }
  if action_type in observability_actions:
    return {
      "action_family": "observability",
      "expectation_strength": "soft",
      "summary_hint": "observability action delivered; coarse state comparison may not reflect improvement",
    }
  if action_type in in_game_actions:
    return {
      "action_family": "in_game_effect",
      "expectation_strength": "unknown",
      "summary_hint": "in-game action delivered; coarse state unchanged, outcome not confirmable",
    }

  lower = action_type.lower()
  if "click" in lower or "navigate" in lower or "focus" in lower:
    return {
      "action_family": "state_advance",
      "expectation_strength": "soft",
      "summary_hint": "navigation action expected to advance state",
    }
  if "inspect" in lower or "observe" in lower or "capture" in lower:
    return {
      "action_family": "observability",
      "expectation_strength": "soft",
      "summary_hint": "observability action delivered; improvement not verifiable by coarse state",
    }

  return {
    "action_family": "unknown",
    "expectation_strength": "unknown",
    "summary_hint": "outcome not verifiable for this action type",
  }


CONFIDENCE_INCREASE_THRESHOLD = 0.15

def derive_observability_improvement(
  pre_state: str | None,
  post_state: str | None,
  pre_confidence: float | None,
  post_confidence: float | None,
  pre_had_error: bool,
  post_has_error: bool,
) -> dict:
  """Derive observability-improvement signals from before/after evidence quality.

  NOT full semantic verification. Only checks whether the operator/system
  can now see more clearly after an observability action.

  Returns:
  - improved: bool — whether any meaningful improvement detected
  - signals: list[str] — specific improvement signals found
  - strength: "none" | "weak" | "moderate" | "strong"

  Signal types:
  - unknown_to_known: coarse state went from unknown to a known state
  - confidence_increased: confidence rose by >= threshold (0.15)
  - error_cleared: previous error resolved
  """
  signals = []

  if pre_state == "unknown" and post_state is not None and post_state != "unknown":
    signals.append("unknown_to_known")

  if pre_confidence is not None and post_confidence is not None:
    delta = post_confidence - pre_confidence
    if delta >= CONFIDENCE_INCREASE_THRESHOLD:
      signals.append("confidence_increased")

  if pre_had_error and not post_has_error:
    signals.append("error_cleared")

  n = len(signals)
  if n == 0:
    strength = "none"
  elif n == 1 and "unknown_to_known" in signals:
    strength = "strong"
  elif n == 1:
    strength = "weak"
  elif n >= 2:
    strength = "moderate"
  else:
    strength = "none"

  return {
    "improved": n > 0,
    "signals": signals,
    "strength": strength,
  }


def build_verification(
  pre_state: str | None,
  execute_success: bool | None,
  post_state: str,
  action_type: str | None = None,
  pre_confidence: float | None = None,
  post_confidence: float | None = None,
  pre_had_error: bool = False,
  post_has_error: bool = False,
) -> Any:
  """Build action-aware coarse verification with expected outcome profiles.

  This is NOT full semantic verification. It compares coarse screen states
  (in_game/not_in_game/unknown) before and after action, using action families
  to set honest expectations. For observability actions, it also checks
  evidence-quality signals (confidence change, error clearance).
  """
  category = classify_action_category(action_type)
  profile = derive_expected_outcome_profile(action_type, pre_state)
  family = profile["action_family"]
  hint = profile["summary_hint"]

  obs_improvement = derive_observability_improvement(
    pre_state, post_state, pre_confidence, post_confidence, pre_had_error, post_has_error,
  )

  if pre_state is None:
    return VerificationResult(
      delivery_status="unknown",
      outcome_status="unknown",
      action_category=category,
      action_family=family,
      summary="No pre-action state recorded",
    )

  if execute_success is False:
    return VerificationResult(
      delivery_status="failed",
      outcome_status="unknown",
      action_category=category,
      action_family=family,
      expected_transition=f"{pre_state} → ?",
      observed_transition=f"{pre_state} → {post_state}",
      summary="Action delivery failed",
    )

  if execute_success is None:
    return VerificationResult(
      delivery_status="unknown",
      outcome_status="unknown",
      action_category=category,
      action_family=family,
      summary="No execute result recorded",
    )

  delivery = "delivered"
  state_changed = pre_state != post_state
  both_known = pre_state != "unknown" and post_state != "unknown"
  obs_signals = obs_improvement["signals"]
  obs_strength = obs_improvement["strength"]

  if family == "state_advance":
    if state_changed and both_known:
      outcome = "confirmed"
      summary = f"State advance confirmed: {pre_state} → {post_state}"
    elif not state_changed:
      outcome = "not_confirmed"
      summary = f"{hint}; coarse state unchanged: {pre_state}"
    else:
      outcome = "unknown"
      summary = f"Navigation delivered; transition unclear: {pre_state} → {post_state}"

  elif family == "state_may_advance":
    if state_changed and both_known:
      outcome = "confirmed"
      summary = f"State advance observed: {pre_state} → {post_state}"
    elif not state_changed:
      outcome = "unknown"
      summary = f"{hint}; coarse state unchanged: {pre_state}"
    else:
      outcome = "unknown"
      summary = f"Action delivered; transition unclear: {pre_state} → {post_state}"

  elif family == "observability":
    if state_changed:
      outcome = "confirmed"
      summary = f"Observability improved: {pre_state} → {post_state}"
    elif obs_improvement["improved"] and obs_strength in ("moderate", "strong"):
      outcome = "confirmed"
      summary = f"Observability improved: {', '.join(obs_signals)}"
    elif obs_improvement["improved"] and obs_strength == "weak":
      outcome = "unknown"
      summary = f"Weak evidence improvement ({', '.join(obs_signals)}); coarse state unchanged"
    else:
      outcome = "unknown"
      summary = f"{hint}; no observable improvement"

  elif family == "in_game_effect":
    if pre_state == "in_game" and post_state == "in_game":
      outcome = "unknown"
      summary = "In-game action delivered; coarse state unchanged, outcome not confirmable"
    elif state_changed and both_known:
      outcome = "confirmed"
      summary = f"In-game action; state changed: {pre_state} → {post_state}"
    elif not state_changed:
      outcome = "unknown"
      summary = f"In-game action delivered; coarse state unchanged: {pre_state}"
    else:
      outcome = "unknown"
      summary = f"In-game action delivered; transition unclear: {pre_state} → {post_state}"

  else:
    if not state_changed:
      outcome = "not_confirmed"
      summary = f"Coarse state unchanged: {pre_state}"
    elif both_known:
      outcome = "confirmed"
      summary = f"Coarse state changed: {pre_state} → {post_state}"
    else:
      outcome = "unknown"
      summary = f"Post-action state unclear: {pre_state} → {post_state}"

  expected = f"{pre_state} → ?"
  if family == "state_advance":
    expected = f"{pre_state} → in_game (state advance expected)"
  elif family == "state_may_advance":
    expected = f"{pre_state} → in_game (may advance)"
  elif family == "observability":
    expected = f"{pre_state} → ? (observability, not state transition)"
  elif family == "in_game_effect":
    expected = f"{pre_state} → {pre_state} (state may stay)"

  return VerificationResult(
    delivery_status=delivery,
    outcome_status=outcome,
    action_category=category,
    action_family=family,
    expected_transition=expected,
    observed_transition=f"{pre_state} → {post_state}",
    summary=summary,
    observability_signals=obs_signals if obs_signals and family in ("observability", "state_may_advance") else None,
    evidence_strength=obs_strength if family in ("observability", "state_may_advance") and obs_strength != "none" else None,
  )


# --- End testable pure functions ---


def _extract_diagnostics(resp, adapter_type: str):
  """Extract adapter-specific diagnostics from attach response."""
  if adapter_type == "web":
    raw = resp.extra.get("startup_diagnostics")
    if raw is None:
      return None
    if isinstance(raw, dict):
      from uno_schemas.adapter_web import WebStartupDiagnostics
      return WebStartupDiagnostics.model_validate(raw)
    return raw
  return None


class WebAttachFailedError(RuntimeError):
  def __init__(self, message: str, diagnostics=None) -> None:
    super().__init__(message)
    self.diagnostics = diagnostics


class SessionOrchestrator:
  def __init__(self, clients: ServiceClients | None = None) -> None:
    self._sessions: dict[str, RuntimeSession] = {}
    self._clients = clients or ServiceClients()
    self._flow = FlowController(self._clients)
    self._bus = get_event_bus()
    self._adapter_registry = None

  @property
  def _registry(self):
    return self._adapter_registry or get_adapter_registry()

  @staticmethod
  def _resolve_default_profile(spec: SessionSpec, adapter_type: AdapterType) -> str:
    if adapter_type == AdapterType.WEB:
      return spec.web_profile_id
    if adapter_type == AdapterType.WINDOWS:
      return spec.windows_profile_id
    return "local-mock-uno"

  def create_session(self, spec: SessionSpec) -> SessionDetail:
    sid = str(uuid4())
    detail = SessionDetail(
      session_id=sid,
      flow_state=FlowState.IDLE,
      phase=SessionPhase.IDLE,
      config=spec.config,
      correlation_id=str(uuid4()),
      automatic=spec.automatic,
    )
    self._sessions[sid] = RuntimeSession(detail=detail, spec=spec)
    return detail

  async def create_session_with_game(self, spec: SessionSpec) -> SessionDetail:
    detail = self.create_session(spec)
    try:
      game = await self._clients.create_game(spec.game_player_names)
      detail.game_id = game["game_id"]
      detail.replay_id = f"replay-{detail.session_id[:8]}"
    except Exception as exc:
      detail.error = f"game create failed: {exc}"
      logger.warning("game_create_failed", session_id=detail.session_id, error=str(exc))
    return detail

  def list_sessions(self) -> list[SessionDetail]:
    return [s.detail for s in self._sessions.values()]

  def get_session(self, session_id: str) -> SessionDetail | None:
    s = self._sessions.get(session_id)
    return s.detail if s else None

  def get_steps(self, session_id: str) -> list:
    s = self._sessions.get(session_id)
    return s.steps if s else []

  def status(self, session_id: str) -> OrchestratorStatus | None:
    s = self._sessions.get(session_id)
    if not s:
      return None
    d = s.detail
    log_attach_diagnostics_checkpoint(
      4,
      session_id,
      failed_stage=d.attach_startup_diagnostics.failed_stage if d.attach_startup_diagnostics else None,
      has_diagnostics=d.attach_startup_diagnostics is not None,
      flow_state=d.flow_state.value,
    )
    snapshot = self._build_strategy_snapshot(s)
    return OrchestratorStatus(
      session_id=d.session_id,
      flow_state=d.flow_state,
      phase=d.phase,
      game_id=d.game_id,
      replay_id=d.replay_id,
      correlation_id=d.correlation_id,
      adapter_bindings=d.adapter_bindings,
      automatic=d.automatic,
      error=d.error,
      last_recovery=s.last_recovery,
      attach_startup_diagnostics=d.attach_startup_diagnostics,
      metrics=d.metrics,
      strategy_snapshot=snapshot,
    )

  def _build_strategy_snapshot(self, session: RuntimeSession) -> StrategySnapshot:
    """Build semantic strategy snapshot from real observation/decision data."""
    detail = session.detail
    steps = session.steps
    observation = session.latest_observation
    decision = session.latest_decision
    status_error = detail.error

    last_execute = None
    for step in reversed(steps):
      if step.step_name == "execute" and step.result.success:
        last_execute = "Action executed"
        break
      if step.step_name == "execute" and not step.result.success:
        last_execute = f"Action failed: {step.result.error or 'unknown'}"
        break

    blocked_reason = None
    if status_error:
      blocked_reason = f"Error: {status_error}"
    elif detail.flow_state == FlowState.PAUSED:
      blocked_reason = "Session paused"
    elif detail.flow_state == FlowState.ERROR:
      blocked_reason = "Agent stopped — needs recovery"
    elif len(steps) == 0:
      blocked_reason = "Awaiting first observation"

    detected_state = self._classify_state(observation, detail)
    goal = self._derive_goal(decision, detected_state, steps)
    next_action = self._derive_next_action(decision, detected_state)

    why_action = None
    if decision and hasattr(decision, "explanation") and decision.explanation:
      candidates = decision.explanation.candidates
      if candidates:
        why_action = candidates[0].reason if candidates[0].reason else None

    confidence = None
    if decision and hasattr(decision, "confidence"):
      confidence = decision.confidence

    verification = self._build_verification(session, detected_state, observation, decision)

    # Surface the perceived game state (hand/top card) so the operator UI can
    # render what the agent actually SEES, not just a text summary. Empty until
    # perception detects cards. Read straight off the game_state dict.
    gs = getattr(observation, "game_state", None) or {}
    top_card = _to_detected_card(gs.get("top_card"))
    hand_cards = [c for c in (_to_detected_card(h) for h in (gs.get("hand_cards") or [])) if c]

    return StrategySnapshot(
      goal=goal,
      detected_state=detected_state,
      hypothesis=self._build_hypothesis(observation, steps),
      next_action=next_action,
      why_action=why_action,
      confidence=confidence,
      blocked_reason=blocked_reason,
      last_executed=last_execute,
      game_type=detail.config.adapter_type,
      verification=verification,
      screen_type=gs.get("screen_type"),
      whose_turn=gs.get("whose_turn"),
      top_card=top_card,
      hand_cards=hand_cards,
      hand_count=(len(hand_cards) if hand_cards else gs.get("hand_count")),
    )

  def _classify_state(self, observation, detail) -> str:
    has_adapter = any(b.attached for b in detail.adapter_bindings) if detail.adapter_bindings else False
    previous_state = getattr(detail, '_last_detected_state', None)
    state = classify_screen_state(observation, has_adapter, previous_state)
    detail._last_detected_state = state
    return state

  def _derive_goal(self, decision, detected_state: str, steps: list) -> str:
    return derive_goal(decision, detected_state, len(steps) > 0)

  def _derive_next_action(self, decision, detected_state: str) -> str | None:
    return derive_next_action(decision, detected_state)

  def _build_hypothesis(self, observation, steps: list) -> str:
    if not observation:
      if len(steps) == 0:
        return "No observations yet"
      return "Awaiting observation"
    if observation.confidence.overall < 0.3:
      return "Low confidence observation — may be inaccurate"
    if observation.game_state:
      return f"Game state detected with confidence {observation.confidence.overall:.0%}"
    if observation.game_elements:
      return f"Game elements detected ({len(observation.game_elements)} items)"
    return "Observation received — processing"

  def _build_verification(self, session, current_state: str, observation=None, decision=None):
    """Build action-aware coarse verification — delegates to pure function."""
    post_confidence = None
    if decision and hasattr(decision, "confidence") and decision.confidence is not None:
      post_confidence = decision.confidence
    elif observation and hasattr(observation, "confidence") and observation.confidence:
      post_confidence = getattr(observation.confidence, "overall", None)

    return build_verification(
      session.pre_action_state,
      session.last_execute_success,
      current_state,
      session.last_action_type,
      pre_confidence=session.pre_action_confidence,
      post_confidence=post_confidence,
      pre_had_error=session.pre_action_had_error,
      post_has_error=bool(session.detail.error),
    )

  async def attach_adapter(self, session_id: str, body: AttachAdapterBody) -> SessionDetail:
    session = self._require(session_id)
    detail = session.detail
    detail.flow_state = transition(detail.flow_state, FlowState.ATTACHING)
    adapter_type = body.adapter_type or detail.config.adapter_type
    profile_id = body.profile_id or self._resolve_default_profile(session.spec, adapter_type)
    try:
      binding = await self._attach_with_retry(session, adapter_type, profile_id, body)
      detail.adapter_bindings = [b for b in detail.adapter_bindings if b.adapter_type != adapter_type]
      detail.adapter_bindings.append(binding)
      detail.config.adapter_id = binding.adapter_id or detail.config.adapter_id
      detail.config.adapter_type = adapter_type
      detail.flow_state = transition(detail.flow_state, FlowState.IDLE)
      detail.error = None
    except Exception as exc:
      message = str(exc)
      err_class = classify_attach_error(exc, adapter_type)
      session.last_recovery = decide_attach_recovery(err_class, message, adapter_type)
      exc_diagnostics = getattr(exc, "diagnostics", None) if isinstance(exc, WebAttachFailedError) else None
      if exc_diagnostics is not None:
        detail.attach_startup_diagnostics = exc_diagnostics
      log_attach_diagnostics_checkpoint(
        3,
        session_id,
        failed_stage=detail.attach_startup_diagnostics.failed_stage if detail.attach_startup_diagnostics else None,
        has_diagnostics=detail.attach_startup_diagnostics is not None,
        exc_type=type(exc).__name__,
      )
      detail.flow_state = FlowState.ERROR
      detail.error = message
      raise
    return detail

  async def detach_adapter(self, session_id: str, adapter_type: AdapterType | None = None) -> SessionDetail:
    session = self._require(session_id)
    detail = session.detail
    registry = self._registry
    for binding in list(detail.adapter_bindings):
      if adapter_type and binding.adapter_type != adapter_type:
        continue
      if binding.adapter_id:
        try:
          client = registry.get_client(binding.adapter_type)
          await client.detach(binding.adapter_id)
        except Exception:
          pass
      binding.attached = False
    detail.adapter_bindings = [b for b in detail.adapter_bindings if b.attached]
    return detail

  async def start(self, session_id: str) -> FlowControlResponse:
    session = self._require(session_id)
    detail = session.detail
    if detail.flow_state == FlowState.ACTIVE and session.observe_ready:
      return FlowControlResponse(session_id=session_id, flow_state=detail.flow_state, message="already active")
    if not self._has_attached_adapter(detail):
      message = detail.error or "cannot start session without attached adapter"
      detail.error = message
      detail.flow_state = FlowState.ERROR
      return FlowControlResponse(session_id=session_id, flow_state=detail.flow_state, message=message)
    detail.error = None
    policy = self._registry.get_retry_policy(detail.config.adapter_type)
    if policy.requires_warmup:
      detail.flow_state = transition(detail.flow_state, FlowState.ATTACHING)
      session.observe_ready = False
      if session.warmup_task and not session.warmup_task.done():
        session.warmup_task.cancel()
      session.warmup_task = asyncio.create_task(self._warmup_observe(session))
      return FlowControlResponse(
        session_id=session_id,
        flow_state=detail.flow_state,
        message="started — observe warmup in progress",
      )
    detail.flow_state = transition(detail.flow_state, FlowState.ACTIVE)
    session.observe_ready = True
    if detail.automatic and (not session.loop_task or session.loop_task.done()):
      session.loop_task = asyncio.create_task(self._run_loop(session))
      logger.info("autonomous_loop_started", session_id=session_id)
    return FlowControlResponse(session_id=session_id, flow_state=detail.flow_state, message="started")

  async def pause(self, session_id: str) -> FlowControlResponse:
    session = self._require(session_id)
    detail = session.detail
    detail.flow_state = transition(detail.flow_state, FlowState.PAUSED)
    return FlowControlResponse(session_id=session_id, flow_state=detail.flow_state, message="paused")

  async def resume(self, session_id: str) -> FlowControlResponse:
    session = self._require(session_id)
    detail = session.detail
    detail.flow_state = transition(detail.flow_state, FlowState.ACTIVE)
    if detail.automatic and (not session.loop_task or session.loop_task.done()):
      session.loop_task = asyncio.create_task(self._run_loop(session))
    return FlowControlResponse(session_id=session_id, flow_state=detail.flow_state, message="resumed")

  async def stop(self, session_id: str) -> FlowControlResponse:
    session = self._require(session_id)
    detail = session.detail
    if session.loop_task and not session.loop_task.done():
      session.loop_task.cancel()
    detail.flow_state = transition(detail.flow_state, FlowState.IDLE)
    detail.automatic = False
    return FlowControlResponse(session_id=session_id, flow_state=detail.flow_state, message="stopped")

  async def run_tick(self, session_id: str, dom_snapshot: dict | None = None) -> dict:
    session = self._require(session_id)
    if session.detail.flow_state == FlowState.ATTACHING and not session.observe_ready:
      return {"skipped": True, "reason": "observe warmup in progress"}
    if dom_snapshot and session.detail.adapter_bindings:
      pass
    prev = session.detail.flow_state
    if prev not in (FlowState.ACTIVE, FlowState.IDLE, FlowState.PAUSED):
      session.detail.flow_state = FlowState.ACTIVE
    result = await self._flow.run_cycle(session)
    await self._bus.publish(BusEvent(
      event_type="orchestrator.tick",
      payload={"session_id": session_id, "result": result},
      correlation_id=session.detail.correlation_id,
    ))
    return result

  async def _warmup_observe(self, session: RuntimeSession) -> None:
    detail = session.detail
    binding = next((b for b in detail.adapter_bindings if b.attached and b.adapter_id), None)
    if not binding or not binding.adapter_id:
      detail.error = "cannot warm up observe without attached adapter"
      detail.flow_state = FlowState.ERROR
      return
    cid = str(uuid4())
    try:
      registry = self._registry
      client = registry.get_client(binding.adapter_type)
      await client.capture_evidence(binding.adapter_id, correlation_id=cid)
      session.observe_ready = True
      detail.flow_state = transition(detail.flow_state, FlowState.ACTIVE)
      detail.error = None
      logger.info("adapter_observe_warmup_ok", session_id=detail.session_id, adapter_type=binding.adapter_type)
      # Warm the VLM model into VRAM off the critical path. The first real
      # perceive otherwise pays Ollama's cold-start load (tens of seconds), which
      # made the model look "not working" while the GPU spun up mid-tick. Fire and
      # forget: no-op when VLM is disabled, never blocks loop start.
      asyncio.create_task(self._warmup_vlm(session, binding))
      if detail.automatic and (not session.loop_task or session.loop_task.done()):
        session.loop_task = asyncio.create_task(self._run_loop(session))
        logger.info("autonomous_loop_started", session_id=detail.session_id)
    except Exception as exc:
      msg = format_exception_message(exc)
      detail.error = msg
      detail.flow_state = FlowState.ERROR
      session.last_recovery = decide_attach_recovery(
        classify_attach_error(exc, binding.adapter_type),
        msg,
        binding.adapter_type,
      )
      logger.warning(
        "adapter_observe_warmup_failed",
        session_id=detail.session_id,
        error=msg,
        error_type=type(exc).__name__,
        adapter_type=binding.adapter_type,
      )

  async def _warmup_vlm(self, session: RuntimeSession, binding) -> None:
    """Best-effort: run one perceive so the vision model loads before tick #1.

    Non-fatal and non-blocking — any failure (VLM off, slow load, transport) is
    swallowed. The point is only to trigger the cold-start model load early; the
    first real tick's perceive then hits a warm model.
    """
    try:
      cid = str(uuid4())
      _dom, _ui, _conf, screenshot = await self._flow._observe(binding, cid)
      await self._clients.perceive(session.detail.session_id, screenshot=screenshot)
      logger.info("vlm_warmup_ok", session_id=session.detail.session_id)
    except Exception as exc:  # noqa: BLE001 — warmup is best-effort, never fatal
      logger.info("vlm_warmup_skipped", session_id=session.detail.session_id, reason=str(exc))

  def create_session_legacy(self, config: SessionConfig) -> SessionState:
    spec = SessionSpec(config=config)
    detail = self.create_session(spec)
    return SessionState(
      session_id=detail.session_id, game_id=detail.game_id, phase=detail.phase,
      config=config, correlation_id=detail.correlation_id, error=detail.error,
    )

  async def _run_loop(self, session: RuntimeSession) -> None:
    logger.info("autonomous_loop_running", session_id=session.detail.session_id)
    while session.detail.automatic:
      if session.detail.flow_state == FlowState.PAUSED:
        # Pause must HOLD: stop ticking and end the loop. resume() spawns a
        # fresh loop task. (Previously PAUSED was force-reset to ACTIVE, so
        # Pause appeared to do nothing — the agent kept acting.)
        logger.info("autonomous_loop_paused", session_id=session.detail.session_id)
        break
      if session.detail.flow_state not in (FlowState.ACTIVE, FlowState.IDLE):
        if session.detail.flow_state == FlowState.ERROR:
          # ERROR is recoverable — keep the agent alive by resuming.
          logger.warning(
            "autonomous_loop_flow_not_active",
            session_id=session.detail.session_id,
            flow_state=session.detail.flow_state.value,
            error=session.detail.error,
          )
          session.detail.flow_state = FlowState.ACTIVE
        else:
          break
      try:
        result = await self._flow.run_cycle(session)
        if result.get("skipped"):
          logger.info("cycle_skipped", session_id=session.detail.session_id, reason=result.get("reason"))
        else:
          logger.info("cycle_completed", session_id=session.detail.session_id, cycle_id=result.get("correlation_id"))
        await asyncio.sleep(1.0)
      except asyncio.CancelledError:
        logger.info("autonomous_loop_cancelled", session_id=session.detail.session_id)
        break
      except Exception as exc:
        logger.error(
          "autonomous_loop_error",
          session_id=session.detail.session_id,
          error=str(exc),
          error_type=type(exc).__name__,
        )
        if session.detail.flow_state == FlowState.ACTIVE:
          await asyncio.sleep(1.0)
    logger.info("autonomous_loop_stopped", session_id=session.detail.session_id, flow_state=session.detail.flow_state.value)

  async def _attach_with_retry(
    self, session: RuntimeSession, adapter_type: AdapterType, profile_id: str, body: AttachAdapterBody
  ) -> AdapterBinding:
    cfg = session.spec.recovery
    policy = self._registry.get_retry_policy(adapter_type)
    last_exc: Exception | None = None
    attempts = policy.max_retries + 1 if policy.retry_on_transient else 1
    for attempt in range(attempts):
      try:
        return await self._do_attach(session.detail.session_id, adapter_type, profile_id, body)
      except Exception as exc:
        last_exc = exc
        if not policy.retry_on_transient:
          break
        session.detail.metrics.retries += 1
        if attempt < attempts - 1:
          await asyncio.sleep(cfg.backoff_ms * (attempt + 1) / 1000)
    if (
      policy.supports_launch_retry
      and body.windows_use_pywinauto
      and not body.launch_test_target
      and body.window_handle is None
    ):
      try:
        logger.info(
          "adapter_attach_launch_retry",
          session_id=session.detail.session_id,
          adapter_type=adapter_type,
          reason=str(last_exc),
        )
        launch_body = body.model_copy(update={"launch_test_target": True})
        return await self._do_attach(session.detail.session_id, adapter_type, profile_id, launch_body)
      except Exception as exc:
        last_exc = exc
    if policy.fallback_to_mock:
      session.detail.metrics.fallbacks += 1
      reason = f"attach failed ({last_exc}) — falling back to mock adapter"
      session.last_recovery = RecoveryDecision(
        error_class=ErrorClass.PERMANENT,
        action=RecoveryMode.FALLBACK_MOCK,
        reason=reason,
      )
      logger.warning("adapter_attach_mock_fallback", session_id=session.detail.session_id, adapter_type=adapter_type, reason=reason)
      fallback_body = body.model_copy(update={"windows_use_pywinauto": False, "launch_test_target": True})
      return await self._do_attach(session.detail.session_id, adapter_type, profile_id, fallback_body)
    if policy.classify_all_permanent:
      message = str(last_exc or f"{adapter_type} attach failed")
      diagnostics = getattr(last_exc, "diagnostics", None) if last_exc else None
      if diagnostics is not None:
        session.detail.attach_startup_diagnostics = diagnostics
      session.last_recovery = decide_attach_recovery(
        classify_attach_error(last_exc or RuntimeError(message), adapter_type),
        message,
        adapter_type,
      )
      logger.error(
        "adapter_attach_failed_no_fallback",
        session_id=session.detail.session_id,
        adapter_type=adapter_type,
        profile_id=profile_id,
        error=message,
        has_diagnostics=diagnostics is not None,
        failed_stage=diagnostics.failed_stage if diagnostics else None,
      )
    raise last_exc or RuntimeError("attach failed")

  async def _do_attach(
    self, session_id: str, adapter_type: AdapterType, profile_id: str, body: AttachAdapterBody
  ) -> AdapterBinding:
    registry = self._registry
    client = registry.get_client(adapter_type)

    request = client.normalize_attach_request(
      session_id=session_id,
      profile_id=profile_id,
      target_url=body.target_url,
      window_title=body.window_title,
      window_handle=body.window_handle,
      window_pid=body.window_pid,
      launch_test_target=body.launch_test_target,
      use_real_backend=body.windows_use_pywinauto,
      cdp_url=body.cdp_url,
    )

    resp = await client.attach(request)

    if not resp.attached:
      diagnostics = _extract_diagnostics(resp, adapter_type)
      if adapter_type == AdapterType.WEB:
        raise WebAttachFailedError(resp.message or "web attach failed", diagnostics)
      raise RuntimeError(resp.message or f"{adapter_type} attach failed")

    return binding_for(adapter_type, resp.adapter_id, profile_id)

  def _require(self, session_id: str) -> RuntimeSession:
    s = self._sessions.get(session_id)
    if not s:
      raise KeyError(f"session not found: {session_id}")
    return s

  @staticmethod
  def _has_attached_adapter(detail: SessionDetail) -> bool:
    return any(b.attached and b.adapter_id for b in detail.adapter_bindings)
