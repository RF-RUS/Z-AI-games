"""End-to-end perceive → decide → guard → execute loop."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from uno_orchestrator.clients import ServiceClients
from uno_orchestrator.recovery import (
  classify_error,
  decide_attach_recovery,
  decide_recovery,
  format_exception_message,
)
from uno_schemas.chat import ChatMessage
from uno_schemas.decision import DecisionRequest, DecisionResult, StrategyId
from uno_schemas.game import ActionType, DomainEvent, EventType, LegalAction
from uno_schemas.model import ModelInvocationContext, ModelInvocationRequest, ModelUseCase
from uno_schemas.orchestrator import (
  AdapterBinding,
  ErrorClass,
  FlowState,
  FlowStep,
  FlowStepName,
  RecoveryMode,
  SessionDetail,
  SessionSpec,
  StepResult,
)
from uno_schemas.perception import DomEvidence, Observation, ScreenshotFrame, UiEvidence
from uno_schemas.session import AdapterType, SessionPhase
from uno_shared.adapter_registry import get_adapter_registry
from uno_shared.game_registry import _ensure_default_plugins, get_game_plugin
from uno_shared.logging import get_logger

logger = get_logger("orchestrator")


@dataclass
class RuntimeSession:
  detail: SessionDetail
  spec: SessionSpec
  steps: list[FlowStep] = field(default_factory=list)
  observe_ready: bool = False
  warmup_task: asyncio.Task | None = None
  latest_observation: Any = None
  latest_decision: Any = None
  pre_action_state: str | None = None
  last_execute_success: bool | None = None
  last_action_type: str | None = None
  pre_action_confidence: float | None = None
  pre_action_had_error: bool = False
  chat_messages: list[ChatMessage] = field(default_factory=list)
  retry_counts: dict[str, int] = field(default_factory=dict)
  last_recovery: Any = None
  loop_task: Any = None


class LowConfidenceError(Exception):
  pass


class FlowController:
  def __init__(self, clients: ServiceClients | None = None) -> None:
    self.clients = clients or ServiceClients()

  def _get_adapter_policy(self, adapter_type):
    """Get the retry/recovery policy for an adapter type from the registry."""
    registry = get_adapter_registry()
    return registry.get_retry_policy(adapter_type)

  def _classify_state_for_verification(self, observation, detail) -> str:
    """Classify state for before/after verification — same as strategy classifier."""
    has_adapter = any(b.attached for b in detail.adapter_bindings) if detail.adapter_bindings else False
    if observation and getattr(observation, "game_state", None):
      return "in_game"
    if observation and getattr(observation, "game_elements", None):
      return "in_game"
    if has_adapter:
      return "not_in_game"
    return "unknown"

  def _extract_action_type(self, decision) -> str | None:
    """Extract action type string from decision for verification."""
    if not decision:
      return None
    chosen = getattr(decision, "chosen_action", None)
    if not chosen:
      return None
    at = getattr(chosen, "action_type", None)
    if at is None:
      return None
    return at.value if hasattr(at, "value") else str(at)

  def _extract_observation_confidence(self, observation, decision) -> float | None:
    """Extract confidence score for before/after comparison."""
    if decision and hasattr(decision, "confidence") and decision.confidence is not None:
      return decision.confidence
    if observation and hasattr(observation, "confidence") and observation.confidence:
      overall = getattr(observation.confidence, "overall", None)
      if overall is not None:
        return overall
    return None

  async def run_cycle(self, session: RuntimeSession) -> dict:
    detail = session.detail
    if detail.flow_state == FlowState.ATTACHING:
      if session.observe_ready:
        detail.flow_state = FlowState.ACTIVE
      else:
        return {"skipped": True, "reason": "observe warmup in progress"}
    if detail.flow_state not in (FlowState.ACTIVE, FlowState.IDLE):
      return {"skipped": True, "reason": f"flow_state={detail.flow_state.value}"}

    cid = str(uuid4())
    detail.correlation_id = cid
    started = time.perf_counter()
    failed_at: FlowStepName | None = None

    try:
      binding = self._primary_binding(detail)
      if not binding or not binding.adapter_id:
        raise RuntimeError("no adapter attached")

      failed_at = FlowStepName.OBSERVE
      await self._run_step(session, cid, FlowStepName.OBSERVE, SessionPhase.OBSERVE)
      dom, ui, obs_conf, screenshot = await self._observe(binding, cid)

      failed_at = FlowStepName.PERCEIVE
      await self._run_step(session, cid, FlowStepName.PERCEIVE, SessionPhase.OBSERVE)
      observation = await self.clients.perceive(detail.session_id, dom=dom, ui=ui, screenshot=screenshot)
      session.latest_observation = observation
      if observation.confidence.overall < detail.config.min_confidence:
        raise LowConfidenceError(f"confidence {observation.confidence.overall} < {detail.config.min_confidence}")

      if observation.confidence.game_state == 0.0 and dom is None and ui is not None:
        detail.metrics.policy_blocks += 1
        detail.error = (
          "Game state not extractable from UI automation tree. "
          "Continuing with heuristic fallback."
        )
        logger.warning(
          "extraction_low_confidence_continuing",
          session_id=detail.session_id,
          adapter_type=detail.config.adapter_type,
          game_state_confidence=observation.confidence.game_state,
        )

      failed_at = FlowStepName.LEGAL_ACTIONS
      await self._run_step(session, cid, FlowStepName.LEGAL_ACTIONS, SessionPhase.DECIDE)
      legal_actions = await self._legal_actions(detail.game_id)

      if detail.config.model_assist_enabled:
        failed_at = FlowStepName.MODEL_ADVISORY
        await self._run_step(session, cid, FlowStepName.MODEL_ADVISORY, SessionPhase.DECIDE)
        await self._model_advisory(detail, cid)

      failed_at = FlowStepName.DECIDE
      await self._run_step(session, cid, FlowStepName.DECIDE, SessionPhase.DECIDE)
      decision = await self._decide(detail, observation, legal_actions, cid)
      session.latest_decision = decision

      # Send pre-action chat message
      action_type_str = self._extract_action_type(decision)
      model_used = getattr(decision.explanation, 'model_used', False) if decision.explanation else False
      source_label = "AI" if model_used else "heuristic"
      pre_msg = await self.clients.send_bot_message(
        detail.session_id,
        f"Planning: {action_type_str}. Reason: {decision.explanation.summary if decision.explanation else 'no explanation'} [{source_label}]",
        correlation_id=cid,
      )
      session.chat_messages.append(pre_msg)

      failed_at = FlowStepName.GUARD
      await self._run_step(session, cid, FlowStepName.GUARD, SessionPhase.VERIFY)
      guard = await self.clients.guard_decision(decision, legal_actions, detail.config.min_confidence)
      if not guard["allowed"]:
        detail.metrics.policy_blocks += 1
        detail.phase = SessionPhase.IDLE
        return {"correlation_id": cid, "guard_blocked": True, "guard": guard}

      if cid in detail.executed_correlation_ids:
        return {"correlation_id": cid, "deduplicated": True}

      failed_at = FlowStepName.EXECUTE
      session.pre_action_state = self._classify_state_for_verification(observation, detail)
      session.last_action_type = self._extract_action_type(decision)
      session.pre_action_confidence = self._extract_observation_confidence(observation, decision)
      session.pre_action_had_error = bool(detail.error)
      await self._run_step(session, cid, FlowStepName.EXECUTE, SessionPhase.EXECUTE)
      try:
        await self._execute(binding, decision, detail, cid)
        session.last_execute_success = True
      except Exception:
        session.last_execute_success = False
        raise
      detail.executed_correlation_ids.append(cid)

      # Send post-action chat message
      post_msg = await self.clients.send_bot_message(
        detail.session_id,
        f"Executed: {action_type_str}. Confidence: {decision.confidence:.0%}. Steps this session: {detail.metrics.total_steps + 1}",
        correlation_id=cid,
      )
      session.chat_messages.append(post_msg)

      failed_at = FlowStepName.RECORD
      await self._run_step(session, cid, FlowStepName.RECORD, SessionPhase.REPLAY)
      await self._record(detail, cid, observation)

      detail.phase = SessionPhase.IDLE
      detail.metrics.total_steps += 1
      detail.metrics.avg_step_latency_ms = int((time.perf_counter() - started) * 1000)
      session.observe_ready = True
      session.retry_counts.clear()
      detail.error = None
      return {
        "correlation_id": cid,
        "observation_id": observation.observation_id,
        "action": decision.chosen_action.model_dump(),
        "guard": guard,
      }
    except Exception as exc:
      return await self._handle_failure(session, cid, exc, failed_at)

  async def _run_step(self, session: RuntimeSession, cid: str, name: FlowStepName, phase: SessionPhase) -> None:
    session.detail.phase = phase
    session.steps.append(FlowStep(
      step_id=str(uuid4()), correlation_id=cid, step_name=name, phase=phase,
      flow_state=session.detail.flow_state,
      result=StepResult(success=True, latency_ms=0),
      timestamp_ms=int(time.time() * 1000),
    ))
    if len(session.steps) > 200:
      session.steps = session.steps[-100:]

  async def _observe(self, binding: AdapterBinding, cid: str) -> tuple[DomEvidence | None, UiEvidence | None, float, ScreenshotFrame | None]:
    registry = get_adapter_registry()
    client = registry.get_client(binding.adapter_type)
    bundle = await client.capture_evidence(binding.adapter_id, correlation_id=cid)

    dom = None
    ui = None
    screenshot = None
    conf = 0.3

    if bundle.dom_evidence:
      dom = DomEvidence.model_validate(bundle.dom_evidence)
      conf = float(dom.confidence)
    elif bundle.ui_evidence:
      ui = UiEvidence.model_validate(bundle.ui_evidence)
      conf = float(ui.confidence)

    # Extract screenshot from evidence bundle (works for both web and windows adapters)
    if hasattr(bundle, 'screenshot') and bundle.screenshot:
      from uno_schemas.perception import ScreenshotFrame
      screenshot = ScreenshotFrame.model_validate(bundle.screenshot)

    return dom, ui, conf, screenshot

  async def _legal_actions(self, game_id: str | None) -> list[LegalAction]:
    if not game_id:
      return [LegalAction(action_type=ActionType.DRAW_CARD, player_id="bot", action_id="fallback")]
    # Try game plugin first, fall back to direct HTTP call
    game_state = self._get_game_snapshot(game_id)
    if game_state:
      _ensure_default_plugins()
      plugin = get_game_plugin(game_state.game_type)
      actions = plugin.get_legal_actions(game_state)
      return [LegalAction(action_type=ActionType.PLAY_CARD, player_id="bot", action_id=str(a)) for a in actions]
    return await self.clients.legal_actions(game_id)

  def _get_game_snapshot(self, game_id: str):
    """Get game snapshot from orchestrator's game state store."""
    # The orchestrator stores game snapshots in session detail
    # For now, return None to fall back to HTTP call
    # This will be wired properly when orchestrator stores snapshots
    return None

  async def _model_advisory(self, detail: SessionDetail, cid: str) -> None:
    detail.metrics.model_advisory_calls += 1
    # Resolve model profile from GameModelConfig
    game_type = detail.config.adapter_type or "unknown"
    model_profile_id = None
    try:
      from uno_shared.model_config import resolve_model_profile
      model_profile_id = resolve_model_profile(game_type, "strategy")
    except Exception:
      pass

    try:
      await self.clients.model_invoke(ModelInvocationRequest(
        context=ModelInvocationContext(
          use_case=ModelUseCase.EXPLANATION, correlation_id=cid, session_id=detail.session_id,
        ),
        profile_id=model_profile_id or "mock/uno-assistant",
        prompt_id="action_explanation",
        variables={"action_type": "draw_card", "card": ""},
        expect_json=True,
      ))
    except Exception:
      detail.metrics.fallbacks += 1

  async def _decide(
    self, detail: SessionDetail, observation: Observation, legal_actions: list[LegalAction], cid: str
  ) -> DecisionResult:
    # Resolve model profile from GameModelConfig if game_type is known
    game_type = getattr(observation, 'game_type', None) or detail.config.adapter_type or "unknown"
    model_profile_id = None
    try:
      from uno_shared.model_config import resolve_model_profile
      model_profile_id = resolve_model_profile(game_type, "strategy")
    except Exception:
      pass  # fallback to no model profile

    # Auto-enable model assist if a real model is configured for this game
    use_model = detail.config.model_assist_enabled
    strategy_id = detail.config.strategy_id
    if model_profile_id and not use_model:
      use_model = True
      strategy_id = StrategyId.MODEL_ASSIST

    return await self.clients.decide(DecisionRequest(
      session_id=detail.session_id, observation=observation, legal_actions=legal_actions,
      strategy_id=strategy_id, use_model_assist=use_model,
      model_profile_id=model_profile_id,
      correlation_id=cid,
      game_type=game_type,
    ))

  async def _execute(self, binding: AdapterBinding, decision: DecisionResult, detail: SessionDetail, cid: str) -> None:
    action = decision.chosen_action
    if detail.game_id:
      await self.clients.apply_action(detail.game_id, action, detail.session_id, cid)

    registry = get_adapter_registry()
    client = registry.get_client(binding.adapter_type)

    # Extract action type — works for both LegalAction and GameAction
    action_type = getattr(action, 'action_type', None)
    action_type_str = action_type.value if hasattr(action_type, 'value') else str(action_type) if action_type else "unknown"

    # Extract payload from action — pass full payload to adapter for game-specific mapping
    payload = getattr(action, 'payload', None)
    if payload is None:
      # Backward compatibility: build payload from card fields if present
      card = getattr(action, 'card', None)
      if card:
        payload = {}
        card_color = getattr(card, 'color', None)
        if card_color:
          payload["card_color"] = card_color.value if hasattr(card_color, 'value') else str(card_color)
        card_value = getattr(card, 'value', None)
        if card_value:
          payload["card_value"] = card_value.value if hasattr(card_value, 'value') else str(card_value)
        payload["card"] = {
          "color": payload.get("card_color"),
          "value": payload.get("card_value"),
        }
      chosen_color = getattr(action, 'chosen_color', None)
      if chosen_color:
        if payload is None:
          payload = {}
        payload["chosen_color"] = chosen_color.value if hasattr(chosen_color, 'value') else str(chosen_color)
      if payload is None:
        payload = {}

    player_id = getattr(action, 'player_id', 'unknown')

    action_req = client.map_action(
      action_type=action_type_str,
      profile_id=binding.profile_id or "local-mock-uno",
      player_id=player_id,
      payload=payload,
    )

    await client.execute_action(binding.adapter_id, action_req, correlation_id=cid)

  async def _record(self, detail: SessionDetail, cid: str, observation: Observation) -> None:
    if not detail.replay_id:
      return
    event = DomainEvent(
      event_id=str(uuid4()), event_type=EventType.ACTION_EXECUTED, game_id=detail.game_id or "unknown",
      session_id=detail.session_id, sequence=len(detail.executed_correlation_ids),
      timestamp_ms=int(time.time() * 1000), correlation_id=cid,
      payload={"flow_state": detail.flow_state.value, "game_type": observation.game_type or "unknown"},
    )
    try:
      await self.clients.replay_event(detail.replay_id, event)
      await self.clients.replay_observation(detail.replay_id, {
        "observation_id": observation.observation_id,
        "session_id": detail.session_id,
        "correlation_id": cid,
        "observation": observation.model_dump(mode="json"),
      })
    except Exception as exc:
      logger.warning("replay_record_failed", error=str(exc), session_id=detail.session_id)

  async def _handle_failure(
    self,
    session: RuntimeSession,
    cid: str,
    exc: Exception,
    failed_at: FlowStepName | None,
  ) -> dict:
    detail = session.detail
    adapter_type = detail.config.adapter_type
    exc_msg = format_exception_message(exc)
    if exc_msg == "no adapter attached" and detail.error:
      err_class = ErrorClass.PERMANENT
      recovery = decide_attach_recovery(err_class, detail.error, adapter_type)
      detail.error = detail.error
    else:
      err_class = classify_error(exc, low_confidence=isinstance(exc, LowConfidenceError))
      retry_key = err_class.value
      retry_count = session.retry_counts.get(retry_key, 0)
      policy = self._get_adapter_policy(adapter_type)
      recovery = decide_recovery(
        err_class,
        retry_count,
        session.spec.recovery,
        classify_all_permanent=policy.classify_all_permanent,
        fallback_to_mock=policy.fallback_to_mock,
        fallback_to_manual=policy.fallback_to_manual,
        message=exc_msg,
      )
      detail.error = exc_msg
      if recovery.action == RecoveryMode.RETRY:
        session.retry_counts[retry_key] = retry_count + 1
        detail.metrics.retries += 1
      else:
        session.retry_counts.pop(retry_key, None)
    if failed_at is not None:
      self._mark_step_failed(session, cid, failed_at, exc_msg, err_class)
    session.last_recovery = recovery
    logger.warning(
      "flow_cycle_failed",
      session_id=detail.session_id,
      failed_step=failed_at.value if failed_at else None,
      error=exc_msg,
      error_type=type(exc).__name__,
      recovery=recovery.action.value,
      recovery_reason=recovery.reason,
    )
    if recovery.action == RecoveryMode.PAUSE:
      detail.flow_state = FlowState.PAUSED
    elif recovery.action == RecoveryMode.FALLBACK_MANUAL:
      detail.flow_state = FlowState.PAUSED
      detail.automatic = False
    elif recovery.action == RecoveryMode.FALLBACK_MOCK:
      detail.metrics.fallbacks += 1
      detail.config.adapter_type = AdapterType.MOCK
    elif recovery.action == RecoveryMode.STOP:
      detail.flow_state = FlowState.ERROR
      detail.automatic = False
    elif recovery.action == RecoveryMode.RETRY:
      detail.flow_state = FlowState.ACTIVE
    detail.metrics.failed_steps += 1
    return {
      "correlation_id": cid,
      "error": exc_msg,
      "failed_step": failed_at.value if failed_at else None,
      "error_type": type(exc).__name__,
      "recovery": recovery.model_dump(mode="json"),
    }

  def _mark_step_failed(
    self,
    session: RuntimeSession,
    cid: str,
    step_name: FlowStepName,
    exc_msg: str,
    err_class: ErrorClass,
  ) -> None:
    for step in reversed(session.steps):
      if step.correlation_id == cid and step.step_name == step_name:
        step.result = StepResult(success=False, error=exc_msg, error_class=err_class)
        return
    session.steps.append(FlowStep(
      step_id=str(uuid4()),
      correlation_id=cid,
      step_name=step_name,
      phase=session.detail.phase,
      flow_state=session.detail.flow_state,
      result=StepResult(success=False, error=exc_msg, error_class=err_class),
      timestamp_ms=int(time.time() * 1000),
    ))

  def _primary_binding(self, detail: SessionDetail) -> AdapterBinding | None:
    for b in detail.adapter_bindings:
      if b.attached and b.adapter_id:
        return b
    return None


# REMOVED: _game_action_to_legal() shim — no longer needed.
# The orchestrator now works with GameAction directly and passes
# payload to adapters via map_action(payload=...).
# UNO-specific LegalAction conversion is handled by the UNO game plugin.
