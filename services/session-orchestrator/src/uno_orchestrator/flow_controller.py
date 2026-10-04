"""End-to-end perceive → decide → guard → execute loop."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from uno_orchestrator.clients import ServiceClients
from uno_orchestrator.perceived_actions import (
  choose_prompt,
  choose_prompt_with_strategy,
  legal_actions_from_perception,
)
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
from uno_shared.adapter_registry import find_draw_target, get_adapter_registry
from uno_shared.click_verification import click_retry_offsets, verify_zone_change, zone_config
from uno_shared.cycle_trace import write_cycle_trace
from uno_shared.game_registry import _ensure_default_plugins, get_game_plugin
from uno_shared.logging import bind_correlation_id, get_logger

logger = get_logger("orchestrator")

# How many consecutive cycles a prompt may stay UNCONFIRMED (click delivered,
# screen never reacted) before the agent tells the operator to take over.
# 3 is deliberately low: each already costs a 15s click+verify, so 3 is ~45s of
# a frozen board. The counter resets on a confirmed click or when the modal is
# gone, so a transient blip never escalates.
_PROMPT_STALL_ESCALATE_AT = 3
# Anti-hallucination guard (2026-08-29 session 0f7de4cd): a REAL Play/Keep
# dialog is closed by a single confirmed click (change_ratio ~0.6). A prompt the
# VLM hallucinates on a static board is never confirmed (change_ratio ~0.02-0.05)
# — and because the prompt branch preempts card play, the agent loops on it for
# minutes and never takes its turn. After escalation, the perceived prompt is
# IGNORED for this many cycles so the flow falls through to normal card
# decision; a real dialog re-asserting itself past the suppression window (or
# confirming a click) ends the suppression.
_PROMPT_HALLUCINATION_SUPPRESS_CYCLES = 2
# Non-board frames that can never host an in-game click. perception's screen_type
# is one of in_game|lobby|menu|unknown. When it is a real non-board (the game is
# animating to the lobby / a result screen / the table is mid-transition), an
# in-game action decided from the (desynced) simulated engine has no on-screen
# target to ground to — the adapter refuses and the cycle dies with
# flow_state=error. See session 56c1564a (2026-08-29): a frame right after a real
# Keep closed was read screen_type=menu gs_conf=0.00, the engine still decided
# play_card, and execute was refused.
_NON_BOARD_SCREEN_TYPES = frozenset({"menu", "lobby", "game_over", "ended", "result"})
# In-game actions that require a readable board before they may be executed.
_IN_GAME_ACTIONS = frozenset({
  "play_card", "draw_card", "choose_color", "pass", "pass_turn",
  "call_uno", "challenge", "accept_penalty",
})
# Anti-hallucination by turn (2026-08-29 session 3bfacb8a): Play/Keep and the
# colour picker are modals that exist only on the human player's OWN turn.
# perception reports whose_turn in the same VLM call, so when it is the
# opponent's turn ANY reported prompt is by definition a phantom — clicking it
# is worse than useless: on a live board the opponent-turn animations fake
# "confirmed" clicks (change_ratio 0.06-0.10 > the 0.05 threshold), which
# defeated the confirmation-based stall guard above.
#
# Anti-hallucination by coordinate stability: a real dialog button stays at the
# same screen position cycle to cycle. A VLM phantom wanders (observed drift
# >100px between cycles on a static board). A label re-reported far from its
# last known position is treated as a phantom for that cycle.
_PROMPT_COORD_STABILITY_PX = 48.0


def _shadow_agree(decision: Any) -> bool | None:
  """Whether the shadow strategy agreed with the primary this tick (None if off)."""
  explanation = getattr(decision, "explanation", None)
  comparison = getattr(explanation, "shadow_comparison", None) if explanation else None
  if comparison is None:
    return None
  return bool(comparison.agree_with_primary)


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
  # Monotonic per-session cycle number for the offline trace. Deliberately NOT
  # metrics.total_steps: that only increments on a COMPLETED cycle, so every failed
  # cycle would overwrite the previous one's trace directory — losing exactly the
  # frames worth keeping.
  cycle_counter: int = 0
  cycle_counter: int = 0
  # Consecutive cycles in which a prompt click was DELIVERED but never confirmed
  # (the screen did not react) — the "Play, Play, Play…" loop that looks like a
  # 20-second stall. A confirmed click or a cycle with no modal on screen resets
  # it. Crossing _PROMPT_STALL_ESCALATE_AT cycles → the operator is told to take
  # over (window focus, an un-drivable dialog, or perception missing the button):
  # further automated retries change nothing, and the agent keeps observing.
  prompt_stall_count: int = 0
  # Anti-hallucination: cycles remaining in which a perceived prompt is IGNORED
  # (treated as absent) so the flow falls through to normal card play. Set when a
  # prompt repeatedly fails to confirm — the signature of a VLM phantom on a
  # static board, not a real dialog.
  prompt_suppress_cycles: int = 0
  # Anti-hallucination by coordinate stability: (x, y) of the prompt button seen
  # last cycle, for its label. A real dialog stays put; a VLM phantom wanders.
  # Reset to None whenever the perceived prompt set changes shape (label appears
  # / disappears) so a brand-new dialog is never compared against a stale one.
  last_prompt_coord: dict[str, tuple[float, float]] = field(default_factory=dict)


class LowConfidenceError(Exception):
  pass


def _filter_phantom_prompts(
  session: RuntimeSession,
  raw_prompts: list[dict] | None,
  whose_turn: str | None,
  session_id: str,
) -> list[dict] | None:
  """Drop prompts that look like VLM hallucinations, BEFORE strategy picks one.

  Two independent, reliable signals — neither depends on click confirmation,
  which is useless on a live board (opponent-turn animations push change_ratio
  over the 0.05 threshold and fake "confirmed" clicks):

  * TURN GATE — Play/Keep and the colour picker are modals that only exist on
    the player's OWN turn. perception reports whose_turn in the very same VLM
    call, so when it says "opponent", ANY button it also reports is a
    logical contradiction: a phantom, always.
  * COORDINATE STABILITY — a real dialog button sits at the same screen
    position every cycle. A label re-reported more than
    _PROMPT_COORD_STABILITY_PX px from where it was last cycle is a phantom for
    this cycle (observed: phantoms wander 100+ px between frames on a static
    board while real buttons don't move).

  Survivors (and only survivors) refresh the per-label coordinate memory. An
  empty prompt set clears the memory so a brand-new real dialog is never
  compared against a stale one.
  """
  prompts = [p for p in (raw_prompts or []) if isinstance(p, dict) and p.get("center")]
  if not prompts:
    session.last_prompt_coord = {}
    return prompts

  # TURN GATE: on the opponent's turn no play modal can exist. Drop everything,
  # and do NOT refresh coordinate memory (phantom positions on a foreign turn
  # must not become the baseline for the next own turn).
  if str(whose_turn or "").strip().lower() == "opponent":
    for p in prompts:
      logger.info(
        "prompt_phantom_filtered", session_id=session_id,
        label=p.get("label"), reason="not_own_turn", whose_turn=whose_turn,
      )
    return []

  kept: list[dict] = []
  # Start from the previous baseline so a label that is filtered this cycle
  # (coordinate jump) KEEPS its stable baseline instead of losing it — otherwise
  # a phantom could wander to a new position and "resync" there as a fresh label.
  new_memory: dict[str, tuple[float, float]] = dict(session.last_prompt_coord)
  for p in prompts:
    label = str(p.get("label", "")).strip().lower()
    try:
      x = float(p["center"]["x"]); y = float(p["center"]["y"])
    except (KeyError, TypeError, ValueError):
      kept.append(p)  # malformed centre — let the normal path handle it
      continue
    prev = new_memory.get(label)
    if prev is not None:
      dist = ((x - prev[0]) ** 2 + (y - prev[1]) ** 2) ** 0.5
      if dist > _PROMPT_COORD_STABILITY_PX:
        logger.info(
          "prompt_phantom_filtered", session_id=session_id, label=label,
          reason="coord_jump", dist_px=round(dist, 1),
          prev=(round(prev[0]), round(prev[1])), now=(round(x), round(y)),
        )
        continue
    kept.append(p)
    new_memory[label] = (x, y)
  session.last_prompt_coord = new_memory
  return kept


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
    gs = getattr(observation, "game_state", None) if observation else None
    # Real gameplay signal only — ignore diagnostic-only keys (cv_error/cv_status)
    # so a failed screenshot decode isn't mistaken for being in-game.
    gameplay_keys = {"screen_type", "hand_cards", "top_card", "regions", "actionable_targets"}
    if gs and (gameplay_keys & set(gs.keys())):
      return "in_game"
    if observation and getattr(observation, "game_elements", None):
      return "in_game"
    if has_adapter:
      return "not_in_game"
    return "unknown"

  def _board_is_playable(self, observation, gs: dict | None) -> bool:
    """True when the perceived frame looks like a real, actionable game board.

    Gate for executing IN-GAME actions (play_card / draw_card / choose_color …).
    A decision is only worth delivering when the frame it was decided on actually
    shows a playable table — perception says `screen_type=in_game` with a
    non-zero game-state confidence. The simulated engine that feeds `_decide`
    keeps its own stale belief about the hand, so on a transition frame
    (menu/lobby/result screen, gs_conf=0.00) it happily "plays" a card that has
    no on-screen coordinate — the adapter then refuses and the cycle dies with
    flow_state=error (session 56c1564a).

    PERMISSIVE DEFAULT: when there is NO game_state data at all, we cannot know
    what is on screen, so the action is NOT deferred (unchanged legacy behaviour
    — same rule as `replan_ungrounded_play`: no perception data → act as decided).
    Only an explicit non-board reading or an explicit zero-confidence frame
    vetoes the move; the next healthy cycle plays it either way. The prompt
    branch (Play/Keep) is NOT gated here: a modal exists on screen regardless of
    the coarse state, and it is handled before this point.
    """
    if not isinstance(gs, dict) or not gs:
      return True
    screen_type = str(gs.get("screen_type") or "").strip().lower()
    if screen_type in _NON_BOARD_SCREEN_TYPES:
      return False
    try:
      gs_conf = float(getattr(getattr(observation, "confidence", None), "game_state", 0.0) or 0.0)
    except (TypeError, ValueError):
      gs_conf = 0.0
    if gs_conf <= 0.0:
      return False
    return True

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
    # Bind the cycle id into the logging context: every structlog line emitted
    # anywhere in this task (perception, adapters included when called
    # in-process) now carries correlation_id=cid, making one full pipeline run
    # greppable across logs/<service>.log files and via /traces/{cid}.
    bind_correlation_id(cid)
    started = time.perf_counter()
    failed_at: FlowStepName | None = None

    # Pre-bound so the `finally` trace below can run after a failure at ANY step —
    # a cycle that died in PERCEIVE still has a frame, and that frame is the most
    # valuable one in the corpus. Without these initializations `finally` would
    # raise NameError and swallow the real exception.
    session.cycle_counter += 1
    cycle_index = session.cycle_counter
    screenshot = None
    observation = None
    legal_actions = None
    decision = None
    guard = None
    # `failed_at` above is a PROGRESS marker, not a failure marker: on a successful
    # cycle it keeps the name of the last step (RECORD), and `detail.error` is reset to
    # None just before the happy-path return. Reading those two in the `finally` labelled
    # every completed cycle `failed_at=record, ok=false` — a corpus that lies about which
    # cycles worked is worse than no corpus. So record the EXCEPTION itself; a cycle that
    # returns without raising (including the prompt_clicked / guard_blocked early
    # returns) is by definition not a failure.
    trace_failed_at = None
    trace_error = None
    click_info: dict | None = None
    t_observe_ms = 0
    t_perceive_ms = 0
    t_decide_ms = 0
    t_execute_ms = 0

    try:
      binding = self._primary_binding(detail)
      if not binding or not binding.adapter_id:
        raise RuntimeError("no adapter attached")

      failed_at = FlowStepName.OBSERVE
      await self._run_step(session, cid, FlowStepName.OBSERVE, SessionPhase.OBSERVE)
      _t0 = time.perf_counter()
      dom, ui, obs_conf, screenshot = await self._observe(binding, cid)
      t_observe_ms = int((time.perf_counter() - _t0) * 1000)

      failed_at = FlowStepName.PERCEIVE
      await self._run_step(session, cid, FlowStepName.PERCEIVE, SessionPhase.OBSERVE)
      _t0 = time.perf_counter()
      observation = await self.clients.perceive(detail.session_id, dom=dom, ui=ui, screenshot=screenshot, vlm_profile_id=detail.vlm_profile_id)
      t_perceive_ms = int((time.perf_counter() - _t0) * 1000)
      session.latest_observation = observation
      # NOTE: the min_confidence gate used to sit HERE, above the diagnostic. It
      # raises LowConfidenceError, so on exactly the runs you most need to debug
      # the [CVv3] line was never produced. Diagnose first, then gate (below).

      # Perception diagnostic — surfaced in the Operator (NEXT ACTION) and logs.
      # The [CVv3] marker confirms THIS build is running: if the operator does not
      # show it, the backend Python services were not restarted with the new code.
      gs = observation.game_state or {}
      hand_n = len(gs.get("hand_cards", []) or [])
      shot_desc = f"{screenshot.width}x{screenshot.height}" if screenshot else "NONE"
      # When no cards were found, read the frame's mean brightness: near-0 means a
      # BLACK capture (GPU/Electron window), which is a capture problem, not a
      # calibration problem.
      bright = ""
      frame_path = ""
      if screenshot and hand_n == 0 and getattr(screenshot, "path", None):
        frame_path = f" frame={screenshot.path}"
        try:
          from PIL import Image
          with Image.open(screenshot.path) as _im:
            _s = _im.convert("RGB").resize((32, 32))
            _px = list(_s.getdata())
          _mean = sum(r + g + b for r, g, b in _px) / (len(_px) * 3) if _px else 0
          bright = f" avg_brightness={_mean:.0f}{'(BLACK)' if _mean < 8 else ''}"
        except Exception:
          bright = " avg_brightness=?"
      cv_fail = ""
      if gs.get("cv_error"):
        cv_fail = f" cv_error={gs['cv_error']}"
      elif gs.get("cv_status"):
        cv_fail = f" cv_status={gs['cv_status']}"
      pcv = gs.get("cv_build") or "MISSING(restart-perception-8103)"
      # Which recognizer actually ran + why VLM did/didn't. Makes "is Ollama
      # being called?" visible in the operator instead of guessing: rec=vlm means
      # the VLM path produced the board; rec=heuristic means it fell back (VLM off,
      # profile disabled, or inference failed — see vlm_status).
      rec = gs.get("recognition_method") or "none"
      vlm_status = gs.get("vlm_status")
      rec_note = f" rec={rec}" + (f" vlm={vlm_status}" if vlm_status else "")
      perception_note = (
        f"[CVv3] pcv={pcv} screenshot={shot_desc} screen_type={gs.get('screen_type', '?')} "
        f"gs_conf={observation.confidence.game_state:.2f} hand_cards={hand_n}"
        f"{rec_note}{bright}{cv_fail}{frame_path}"
      )
      # Log the full [CVv3] note EVERY cycle, not just on failure. It previously
      # existed only inside the `detail.error` branch below, so once perception
      # started working the line vanished entirely — leaving no way to confirm
      # rec=vlm (i.e. that Ollama is actually being used) on a healthy session.
      logger.info(
        "perception_diag", session_id=detail.session_id, note=perception_note,
        screenshot=shot_desc, screen_type=gs.get("screen_type"), recognizer=rec,
        vlm_status=vlm_status,
        hand_cards=hand_n, game_state_confidence=observation.confidence.game_state,
      )

      # Confidence gate, moved down from above so the [CVv3] diagnostic is always
      # emitted first. The note is attached to the error so the operator shows WHY
      # confidence was low (no screenshot? black frame? rec=heuristic?).
      if observation.confidence.overall < detail.config.min_confidence:
        raise LowConfidenceError(
          f"confidence {observation.confidence.overall} < {detail.config.min_confidence}. {perception_note}"
        )

      if observation.confidence.game_state == 0.0 and not gs.get("hand_cards"):
        detail.metrics.policy_blocks += 1
        if screenshot is None:
          detail.error = (
            f"No screenshot reached perception — screenshot CV cannot run. {perception_note}. "
            "Restart the backend services (dev-backend.ps1) so this build is active."
          )
        else:
          detail.error = (
            f"Screenshot received but no cards recognized. {perception_note}. "
            "Likely the captured window / zone calibration doesn't match this game."
          )
        logger.warning(
          "extraction_low_confidence_continuing",
          session_id=detail.session_id,
          adapter_type=detail.config.adapter_type,
          game_state_confidence=observation.confidence.game_state,
          screenshot=shot_desc,
        )

      failed_at = FlowStepName.LEGAL_ACTIONS
      await self._run_step(session, cid, FlowStepName.LEGAL_ACTIONS, SessionPhase.DECIDE)

      # On-screen prompt (Play/Keep after drawing, colour picker, "Continue"…):
      # the game blocks on a modal button that must be clicked before any card
      # move. Handle it FIRST — click the button and end this cycle. Only fires
      # when perception (VLM) reported prompt buttons with coordinates.
      # The Play/Keep dilemma is decided by GAME STRATEGY (drawn card vs top vs
      # hand), not by a static "Play first" preference: choose_prompt_with_strategy
      # returns the button to click plus WHY, which lands in the chat and the log.
      gs_now = observation.game_state or {}
      prompts = _filter_phantom_prompts(
        session, gs_now.get("prompts"), gs_now.get("whose_turn"), detail.session_id,
      )
      prompt, strategy_reason = choose_prompt_with_strategy(
        prompts,
        top_card=gs_now.get("top_card"),
        hand_cards=gs_now.get("hand_cards"),
        drawn_card=gs_now.get("drawn_card"),
      )
      # No modal on screen → a previous prompt stall is resolved (the dialog is
      # gone, or perception degraded to the point we can't see buttons — in which
      # case we honestly stop claiming a stall we can no longer measure).
      if prompt is None:
        if session.prompt_stall_count:
          session.prompt_stall_count = 0
        # A clean board re-arms prompt handling immediately: a dialog that appears
        # after a prompt-free cycle is almost certainly real, not a lingering phantom.
        session.prompt_suppress_cycles = 0
      # Anti-hallucination: a phantom prompt (VLM sees Play/Keep on a static board
      # where no dialog is) is never confirmed — a real one closes on the first
      # confirmed click. While suppression is active we SKIP the prompt branch and
      # let the flow fall through to normal card decision, instead of hammering a
      # button that isn't there (this was the "agent froze and never played" loop).
      if prompt is not None and session.prompt_suppress_cycles > 0:
        session.prompt_suppress_cycles -= 1
        logger.info(
          "prompt_suppressed_phantom", session_id=detail.session_id,
          label=prompt.get("label"), remaining=session.prompt_suppress_cycles,
        )
      elif prompt is not None:
        # OBSERVE-ONLY: the prompt would block the board, so report which button
        # we WOULD click (and why) but never deliver it. Without this guard the
        # prompt branch fires before the dry_run check below and clicks the game
        # even in dry-run — exactly the "test clicks the live game" mixing that
        # made the operator see the window react during a no-op run.
        if detail.config.dry_run:
          announcement = (
            f"[dry-run] Would click prompt '{prompt.get('label')}'. "
            f"Reason: {strategy_reason}"
          )
          pre_msg = await self.clients.send_bot_message(
            detail.session_id, announcement, correlation_id=cid,
          )
          session.chat_messages.append(pre_msg)
          session.last_action_type = "prompt_click_dry_run"
          return {
            "correlation_id": cid,
            "dry_run": True,
            "planned_prompt": prompt,
            "prompt_strategy": strategy_reason or None,
            "prompt_status": "dry_run_skipped",
          }
        _t0 = time.perf_counter()
        announcement, click_info = await self._click_prompt(
          binding, prompt, detail, cid, reason=strategy_reason,
        )
        t_execute_ms = int((time.perf_counter() - _t0) * 1000)
        # Stall escalation: N consecutive unconfirmed prompt clicks means the
        # board is genuinely stuck (coords, focus, un-drivable dialog). Say so
        # ONCE to the operator and keep observing — do not pretend progress.
        if click_info.get("status") == "confirmed":
          session.prompt_stall_count = 0
        else:
          session.prompt_stall_count += 1
          if session.prompt_stall_count >= _PROMPT_STALL_ESCALATE_AT:
            session.prompt_stall_count = 0
            # The signature of a VLM phantom: a real Play/Keep dialog closes on
            # the FIRST confirmed click (change_ratio ~0.6). Three straight
            # unconfirmed clicks (change_ratio ~0.02-0.05, static board) mean
            # there is almost certainly no dialog — so STOP clicking it and let
            # the agent take its actual card turn for a few cycles.
            session.prompt_suppress_cycles = _PROMPT_HALLUCINATION_SUPPRESS_CYCLES
            stall_msg = await self.clients.send_bot_message(
              detail.session_id,
              (
                f"STALLED on prompt '{prompt.get('label')}': clicked it "
                f"{_PROMPT_STALL_ESCALATE_AT} times in a row (last change_ratio="
                f"{click_info.get('change_ratio')}) and the screen never reacted. "
                "This looks like a phantom dialog (the VLM sees a button that "
                "isn't there) — pausing prompt clicks and taking my card turn "
                "instead. If a real dialog is open, click it once manually."
              ),
              correlation_id=cid,
            )
            session.chat_messages.append(stall_msg)
            logger.warning(
              "prompt_stall_escalated", session_id=detail.session_id,
              label=prompt.get("label"), last_change_ratio=click_info.get("change_ratio"),
            )
        pre_msg = await self.clients.send_bot_message(
          detail.session_id, announcement, correlation_id=cid,
        )
        session.chat_messages.append(pre_msg)
        session.last_action_type = "prompt_click"
        return {
          "correlation_id": cid,
          "prompt_clicked": prompt.get("label"),
          "prompt_strategy": strategy_reason or None,
          "prompt_status": click_info["status"],
        }

      legal_actions = await self._legal_actions(detail.game_id, observation)

      if detail.config.model_assist_enabled:
        failed_at = FlowStepName.MODEL_ADVISORY
        await self._run_step(session, cid, FlowStepName.MODEL_ADVISORY, SessionPhase.DECIDE)
        await self._model_advisory(detail, cid)

      failed_at = FlowStepName.DECIDE
      await self._run_step(session, cid, FlowStepName.DECIDE, SessionPhase.DECIDE)
      _t0 = time.perf_counter()
      decision = await self._decide(detail, observation, legal_actions, cid)
      t_decide_ms = int((time.perf_counter() - _t0) * 1000)
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

      # Dry-run safety mode: the full perception→decision→guard pipeline ran, so
      # report exactly what WOULD be executed, but never deliver it to the adapter.
      # The game on screen stays untouched; the operator UI shows the planned action.
      if detail.config.dry_run:
        session.pre_action_state = self._classify_state_for_verification(observation, detail)
        session.last_action_type = self._extract_action_type(decision)
        await self._run_step(session, cid, FlowStepName.EXECUTE, SessionPhase.EXECUTE)
        logger.info(
          "dry_run_action_skipped", session_id=detail.session_id,
          action=self._extract_action_type(decision), confidence=decision.confidence,
        )
        detail.phase = SessionPhase.IDLE
        return {
          "correlation_id": cid,
          "dry_run": True,
          "planned_action": decision.chosen_action.model_dump(mode="json"),
          "confidence": decision.confidence,
          "shadow": _shadow_agree(decision),
        }

      # PLAYABILITY GATE: an in-game action (play/draw/choose_color/…) is only
      # executable when the frame it was decided on actually shows a playable
      # board. perception reads a transition frame (menu/lobby/result screen, or a
      # zero-confidence frame) and the desynced simulated engine still "decides" a
      # card that has no on-screen coordinate to ground to — the adapter then
      # refuses ("…not supported via Windows UIA…") and the cycle dies with
      # flow_state=error (session 56c1564a). Defer instead of executing: keep
      # observing, and the next healthy in_game cycle plays the same move. The
      # prompt branch (Play/Keep) is deliberately NOT gated — a modal exists on
      # screen regardless of the coarse board state, and it is handled before
      # this point.
      if action_type_str in _IN_GAME_ACTIONS and not self._board_is_playable(
        observation, observation.game_state if observation else None,
      ):
        gs_defer = (observation.game_state if observation else None) or {}
        logger.warning(
          "in_game_action_deferred", session_id=detail.session_id, cid=cid,
          action=action_type_str,
          screen_type=gs_defer.get("screen_type"),
          game_state_confidence=getattr(getattr(observation, "confidence", None), "game_state", None) if observation else None,
          reason="board not playable (non-board or zero-confidence frame)",
        )
        defer_msg = await self.clients.send_bot_message(
          detail.session_id,
          f"Table not readable yet (transition frame). Holding '{action_type_str}' — "
          "will play it as soon as the board is visible again.",
          correlation_id=cid,
        )
        session.chat_messages.append(defer_msg)
        detail.phase = SessionPhase.IDLE
        return {
          "correlation_id": cid,
          "deferred": True,
          "planned_action": action_type_str,
        }

      failed_at = FlowStepName.EXECUTE
      session.pre_action_state = self._classify_state_for_verification(observation, detail)
      session.last_action_type = self._extract_action_type(decision)
      session.pre_action_confidence = self._extract_observation_confidence(observation, decision)
      session.pre_action_had_error = bool(detail.error)
      await self._run_step(session, cid, FlowStepName.EXECUTE, SessionPhase.EXECUTE)
      _t0 = time.perf_counter()
      try:
        await self._execute(binding, decision, detail, cid, observation, screenshot)
        session.last_execute_success = True
      except Exception:
        session.last_execute_success = False
        raise
      t_execute_ms = int((time.perf_counter() - _t0) * 1000)
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
        "shadow": _shadow_agree(decision),
      }
    except Exception as exc:
      trace_failed_at = failed_at
      # Not str(exc): httpx transport errors (ReadTimeout, ConnectError) have an EMPTY
      # str(), which is how cycle 5 of session e9f527e3 came out as "failed at observe"
      # with no reason at all.
      trace_error = f"{type(exc).__name__}: {exc}"
      return await self._handle_failure(session, cid, exc, failed_at)
    finally:
      # One record per cycle, success or failure. This is what turns "restart 14
      # services and launch a real game" into `pytest`: the frame and the full
      # perceived board land on disk together, so recognition can be re-run offline
      # against saved frames. See uno_shared.cycle_trace for the rationale.
      write_cycle_trace(
        session_id=detail.session_id,
        cycle_index=cycle_index,
        correlation_id=cid,
        game_type=getattr(detail.config, "game_type", None) or detail.game_id,
        screenshot=screenshot,
        observation=observation,
        legal_actions=legal_actions,
        decision=decision,
        guard=guard,
        failed_at=trace_failed_at,
        error=trace_error,
        timings_ms={
          "cycle": int((time.perf_counter() - started) * 1000),
          "observe": t_observe_ms,
          "perceive": t_perceive_ms,
          "decide": t_decide_ms,
          "execute": t_execute_ms,
        },
        click=click_info,
      )

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

    # Extract screenshot from evidence bundle.
    # GenericEvidenceBundle has NO `screenshot` field — it exposes the raw adapter
    # payload in `.extra` and the file path in `.screenshot_path`. The old code
    # looked for a non-existent `bundle.screenshot`, so the screenshot NEVER
    # reached perception on real windows/web sessions → the screenshot-CV path
    # silently never ran → game_state stayed empty → the agent classified every
    # frame as "not_in_game" and never played. Reconstruct it here.
    from uno_schemas.perception import ScreenshotFrame
    shot_data = bundle.extra.get("screenshot") if getattr(bundle, "extra", None) else None
    if isinstance(shot_data, dict):
      try:
        screenshot = ScreenshotFrame.model_validate(shot_data)
      except Exception:
        screenshot = None
    if screenshot is None and getattr(bundle, "screenshot_path", None):
      w = h = 1
      try:
        from PIL import Image
        with Image.open(bundle.screenshot_path) as _im:
          w, h = _im.size
      except Exception:
        pass
      screenshot = ScreenshotFrame(
        frame_id=cid,
        session_id=bundle.session_id or "unknown",
        width=max(1, w),
        height=max(1, h),
        path=bundle.screenshot_path,
        captured_at_ms=int(time.time() * 1000),
      )

    return dom, ui, conf, screenshot

  async def _legal_actions(self, game_id: str | None, observation: Observation | None = None) -> list[LegalAction]:
    # 9d — PREFER legal actions derived from the PERCEIVED board (real hand + top
    # card from VLM/CV). This is what makes the agent play the RIGHT card instead
    # of the leftmost: the returned action carries the detected card's
    # colour+value, which the windows executor grounds to the correct coordinate.
    # Returns None when the board isn't readable enough → fall through to the
    # simulated engine (unchanged legacy path).
    if observation is not None and getattr(observation, "game_state", None):
      gs = observation.game_state
      perceived = legal_actions_from_perception(
        gs.get("hand_cards"), gs.get("top_card")
      )
      if perceived:
        return perceived

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
      shadow_mode=detail.config.shadow_evaluation,
    ))

  async def _execute(
    self, binding: AdapterBinding, decision: DecisionResult, detail: SessionDetail,
    cid: str, observation: Observation | None = None, screenshot: ScreenshotFrame | None = None,
  ) -> None:
    action = decision.chosen_action
    if detail.game_id:
      # The simulated uno-core game is the source of truth ONLY for the mock
      # adapter. On a REAL adapter (windows/web) we play against the actual game
      # on screen; the simulator runs a parallel, desynced model, so a rejected
      # move (400 — card not in its deck) must NOT crash the real click, which is
      # the ground truth. Keep it fatal for mock; advisory (log + continue) for
      # real screen play.
      is_real_screen = binding.adapter_type in ("windows", "web")
      try:
        await self.clients.apply_action(detail.game_id, action, detail.session_id, cid)
      except Exception as exc:  # noqa: BLE001
        if not is_real_screen:
          raise
        logger.warning(
          "simulator_apply_rejected_ignored", session_id=detail.session_id,
          adapter_type=binding.adapter_type, error=str(exc),
        )

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

    # Detected hand cards (screenshot CV) → lets the adapter GROUND the click to
    # the real card coordinate instead of a static/hardcoded target.
    hand_cards = None
    if observation is not None and getattr(observation, "game_state", None):
      hc = observation.game_state.get("hand_cards")
      if isinstance(hc, list) and hc:
        hand_cards = hc
      # Ground a draw_card action to the perceived deck coordinate so it doesn't
      # stall on canvas/Electron (empty UIA). Thread it through the payload;
      # _map_action_windows reads extra["draw_target"].
      if action_type_str in ("draw_card", "draw"):
        draw_target = find_draw_target(observation.game_state)
        if draw_target is not None:
          payload = {**(payload or {}), "draw_target": list(draw_target)}

      # Ground choose_color to a click point on canvas/Electron (the colour cubes
      # aren't in UIA). Cheap path first: the colour button may already be in the
      # perceived prompts[]. Fall back to the VLM grounding provider only when
      # it isn't. Sets target_x/target_y that _map_action_windows passes on.
      if action_type_str == "choose_color":
        color = payload.get("chosen_color") if payload else None
        xy = await self._ground_choose_color(color, observation, screenshot, detail)
        if xy is not None:
          payload = {**(payload or {}), "target_x": xy[0], "target_y": xy[1]}

    # Re-plan a play_card whose card is NOT in the perceived hand. The simulated
    # engine's hand desyncs from the real table; its phantom cards can never be
    # grounded ("need to draw, instead of an error"). Perceptual contract: every
    # play_card must name a card actually detected on screen. If it doesn't, the
    # honest move is drawing — swap here rather than letting the adapter refuse
    # at delivery time (session de3856d6 cycle 2 and after).
    if action_type_str == "play_card" and isinstance(hand_cards, list) and hand_cards:
      played_color = str((payload or {}).get("card_color") or "").lower()
      played_value = str((payload or {}).get("card_value") or "").lower()
      if any(
        str(c.get("color", "")).lower() == played_color
        and (
          not played_value
          or str(c.get("value", "")).lower() == played_value
          or str(c.get("value", "")).lower() == "unknown"
        )
        for c in hand_cards if isinstance(c, dict)
      ):
        pass  # card exists on screen → grounds normally below
      elif observation is not None and getattr(observation, "game_state", None) \
          and (observation.game_state or {}).get("screen_type") == "in_game":
        logger.warning(
          "replan_ungrounded_play_as_draw", session_id=detail.session_id, cid=cid,
          wanted=f"{played_color} {played_value}",
          reason="chosen card absent from perceived hand (simulator desync)",
        )
        detail.metrics.fallbacks += 1
        draw_target = find_draw_target(observation.game_state)
        decision = DecisionResult(
          chosen_action=LegalAction(action_type=ActionType.DRAW_CARD, player_id=player_id, action_id="draw"),
          confidence=min(decision.confidence, 0.7),
          explanation=decision.explanation.model_copy(update={
            "summary": f"Replanned {action_type_str} ({played_color} {played_value}) as draw_card: "
                       f"card not in the perceived hand",
          }) if decision.explanation else decision.explanation,
          correlation_id=cid,
        )
        action = decision.chosen_action
        action_type_str = "draw_card"
        payload = {"card_color": None, "card_value": None}
        if draw_target is not None:
          payload["draw_target"] = list(draw_target)

    action_req = client.map_action(
      action_type=action_type_str,
      profile_id=binding.profile_id or "local-mock-uno",
      player_id=player_id,
      hand_cards=hand_cards,
      payload=payload,
    )

    result = await client.execute_action(binding.adapter_id, action_req, correlation_id=cid)

    # The adapter answers HTTP 200 even when it REFUSED to act (no UIA target, no
    # click point, confidence below threshold) — success/error live in the BODY. This
    # return value used to be discarded, so a refused click became "Delivery:
    # Delivered" in the operator with the mouse never moving, and the cycle went on to
    # RECORD a step that never happened. An action the agent did not perform must be a
    # failure, loudly: everything downstream (verification, retry, the belief that the
    # board changed) is built on "delivered means clicked".
    if result is not None and not getattr(result, "success", True):
      err = getattr(result, "error", None) or "adapter refused the action"
      logger.warning(
        "execute_refused_by_adapter",
        session_id=detail.session_id, adapter_type=binding.adapter_type,
        action=action_type_str, selector_key=action_req.selector_key,
        grounded_by=(action_req.extra or {}).get("grounded_by"),
        target_x=(action_req.extra or {}).get("target_x"),
        error=err,
      )
      raise RuntimeError(f"adapter did not perform {action_type_str}: {err}")

  async def _ground_choose_color(
    self, color: str | None, observation: Observation | None,
    screenshot: ScreenshotFrame | None, detail: SessionDetail,
  ) -> tuple[int, int] | None:
    """Resolve a screen point for choosing `color`, or None if not groundable.

    Cheapest-first: reuse an already-perceived colour button, else ask the VLM
    grounding provider. Returns integer screenshot coords, or None so the caller
    sends an ungrounded click (the pre-existing behaviour) rather than stalling.
    """
    gs = getattr(observation, "game_state", None) or {}
    # Cheap path: the colour button is already in the perceived prompts[].
    prompt = choose_prompt(gs.get("prompts"), prefer_color=color)
    if prompt and prompt.get("center"):
      c = prompt["center"]
      return int(c["x"]), int(c["y"])
    # Fallback: VLM grounding. Needs a screenshot on disk to look at.
    shot_path = getattr(screenshot, "path", None) if screenshot else None
    if not shot_path:
      return None
    game_type = getattr(observation, "game_type", None) or detail.config.adapter_type or "unknown"
    res = await self.clients.ground(
      "choose_color", shot_path, params={"color": color or ""}, game_type=game_type,
    )
    if res.get("found") and res.get("x") is not None and res.get("y") is not None:
      return int(res["x"]), int(res["y"])
    return None

  async def _capture_frame(self, client, binding: AdapterBinding, session_id: str, cid: str) -> str | None:
    """Path of a FRESH screenshot from the adapter, or None if capture failed.

    Deliberately not the cycle's `screenshot`: that frame belongs to OBSERVE and can
    be seconds old by the time the game reacts to a click. Verification needs two
    captures bracketing the click itself.
    """
    try:
      bundle = await client.capture_evidence(binding.adapter_id, correlation_id=cid)
    except Exception as exc:
      logger.warning(
        "click_verify_capture_failed", session=session_id,
        error=f"{type(exc).__name__}: {exc}",
      )
      return None
    return getattr(bundle, "screenshot_path", None) or None

  async def _click_prompt(
    self, binding: AdapterBinding, prompt: dict, detail: SessionDetail, cid: str, reason: str = "",
  ) -> tuple[str, dict]:
    """Click an on-screen prompt button (Play/Keep, colour picker, Continue) and
    VERIFY the click actually took effect. Returns (announcement, click_info).

    Grounds the click to the button's perceived coordinate — the same mechanism
    as card/draw grounding. Lets the agent get past modal dialogs it would
    otherwise stall on (the recurring "draw → Play/Keep → stuck" case). `reason`
    carries the strategy verdict (WHY this side of the dilemma was chosen) so the
    operator chat and logs show the decision, not just a blind click.

    VERIFICATION (regression, session 8b4cefc1 2026-08-24): `execute_action`
    reported success=True twice while the game ignored the click and kept showing
    the same modal, so every following cycle decided on a board that never moved.
    A dispatched click is therefore NOT a done action: after each attempt we
    re-capture the screen and require a visible change in the zone around the
    clicked point (whole-frame diffs are useless — opponents redraw the board
    constantly). Unreactive → retry with small offsets around the perceived
    centre, then report the outcome as unconfirmed instead of silently claiming
    success. The click info lands in the cycle trace, logs, and the chat line.
    """
    from uno_shared.adapter_protocol import GenericActionRequest

    center = prompt.get("center") or {}
    base_x, base_y = int(center.get("x", 0)), int(center.get("y", 0))
    cfg = zone_config()
    min_ratio = float(cfg["min_ratio"])
    label = prompt.get("label") or "?"

    registry = get_adapter_registry()
    client = registry.get_client(binding.adapter_type)
    # Surface the STRATEGY decision, not just coordinates: the whole point of the
    # Play/Keep fix is that the AI analysed drawn-vs-top-vs-hand and chose a side.
    # The returned text is announced by the caller into the operator chat.
    announcement = f"Prompt: {label}" + (f" — {reason}" if reason else "")

    before_path = await self._capture_frame(client, binding, detail.session_id, cid)

    attempts_plan = click_retry_offsets()
    delivery_ok = False
    delivered_any = False
    change_ratio: float | None = None
    after_path: str | None = None
    final_x, final_y = base_x, base_y
    attempts_made = 0
    status = "unverifiable"
    for index, (dx, dy) in enumerate(attempts_plan):
      final_x, final_y = base_x + dx, base_y + dy
      req = GenericActionRequest(
        action_type="click_input",
        selector_key="prompt",
        domain_action="click_prompt",
        extra={
          "target_x": final_x, "target_y": final_y,
          "grounded_by": "cv_detection",
          "capture_screenshots": True,
          "min_confidence": 0.55,
          "allow_coordinate_fallback": True,
          "prompt_label": prompt.get("label", ""),
          "prompt_strategy": reason,
        },
      )
      logger.info("prompt_click", session=detail.session_id, label=label,
                  x=final_x, y=final_y, strategy=reason or None,
                  attempt=index + 1, max_attempts=len(attempts_plan))
      attempts_made = index + 1
      try:
        res = await client.execute_action(binding.adapter_id, req, correlation_id=cid)
        delivered_any = True
        delivery_ok = bool(getattr(res, "success", False)) and not getattr(res, "error", None)
      except Exception as exc:
        logger.warning(
          "prompt_click_delivery_failed", session=detail.session_id, label=label,
          attempt=index + 1, error=f"{type(exc).__name__}: {exc}",
        )
        status = "delivery_failed"
        break

      after_path = await self._capture_frame(client, binding, detail.session_id, cid)
      if not before_path or not after_path:
        logger.info(
          "prompt_click_unverifiable", session=detail.session_id, label=label,
          attempt=index + 1, note="could not capture before/after frames",
        )
        break
      change_ratio = verify_zone_change(
        before_path, after_path, final_x, final_y,
        half_w=int(cfg["half_w"]), half_h=int(cfg["half_h"]), pixel_diff=int(cfg["pixel_diff"]),
      )
      if change_ratio is not None and change_ratio >= min_ratio:
        status = "confirmed"
        break
      logger.info(
        "prompt_click_unconfirmed", session=detail.session_id, label=label,
        attempt=index + 1,
        change_ratio=None if change_ratio is None else round(change_ratio, 4),
        min_change_ratio=min_ratio,
        note="zone around the button did not visibly react; retrying with offset",
      )
      if index < len(attempts_plan) - 1:
        await asyncio.sleep(float(cfg["settle_s"]))

    if status != "confirmed" and delivered_any and status != "delivery_failed":
      # Click went out at least once but the screen never reacted (or we could not
      # measure it). Not a delivery failure — say exactly that.
      status = "unconfirmed" if change_ratio is not None else "unverifiable"

    if status == "confirmed":
      announcement += " (confirmed)"
    elif status == "unconfirmed":
      announcement += " (UNCONFIRMED — screen did not react)"
    elif status == "unverifiable":
      announcement += " (unverified — no before/after frames)"

    click_info = {
      "type": "prompt_click",
      "label": label,
      "base_point": {"x": base_x, "y": base_y},
      "final_point": {"x": final_x, "y": final_y},
      "attempts": attempts_made,
      "delivery_ok": delivery_ok or status == "confirmed",
      "status": status,
      "change_ratio": None if change_ratio is None else round(change_ratio, 4),
      "min_change_ratio": min_ratio,
      "before_frame": before_path,
      "after_frame": after_path,
    }
    logger.info(
      "prompt_click_result", session=detail.session_id, label=label,
      status=status, attempts=attempts_made,
      change_ratio=click_info["change_ratio"],
    )
    return announcement, click_info

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
      # Name the step in the operator-visible error. "ReadTimeout" alone doesn't
      # say whether observe, perceive or execute stalled, and those have very
      # different fixes (adapter capture vs slow VLM vs a hung click).
      detail.error = f"{failed_at.value}: {exc_msg}" if failed_at else exc_msg
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
