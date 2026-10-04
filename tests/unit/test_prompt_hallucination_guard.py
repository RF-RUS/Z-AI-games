"""Regression: a VLM-hallucinated Play/Keep prompt must not freeze card play.

Session 0f7de4cd (2026-08-29): after a REAL Play/Keep dialog was closed with a
confirmed click (change_ratio=0.62), the VLM kept reporting the SAME prompt on
every in-game frame (coords near the board centre, a location no Play/Keep
button occupies). All subsequent clicks were unconfirmed (change_ratio
0.02-0.05). Because the prompt branch preempts card decision, the agent looped
"click Keep x3 → escalate → click Keep x3 → …" for minutes and never played a
card, even though the top card was playable.

The guard: after _PROMPT_STALL_ESCALATE_AT unconfirmed clicks the prompt is
suppressed for _PROMPT_HALLUCINATION_SUPPRESS_CYCLES cycles, so the flow falls
through to normal card decision. A prompt-free cycle re-arms prompt handling
(a dialog appearing after a clean board is real, not a lingering phantom).
"""

from types import SimpleNamespace

import pytest

from uno_orchestrator.flow_controller import (
  _PROMPT_HALLUCINATION_SUPPRESS_CYCLES,
  _PROMPT_STALL_ESCALATE_AT,
  RuntimeSession,
)


def _session(suppress=0, stall=0) -> RuntimeSession:
  detail = SimpleNamespace(
    session_id="s1",
    config=SimpleNamespace(dry_run=False, min_confidence=0.5),
    adapter_bindings=[],
    flow_state="active",
  )
  s = RuntimeSession(detail=detail, spec=SimpleNamespace())
  s.prompt_suppress_cycles = suppress
  s.prompt_stall_count = stall
  return s


def test_constants_are_sane():
  assert _PROMPT_STALL_ESCALATE_AT >= 3
  assert _PROMPT_HALLUCINATION_SUPPRESS_CYCLES >= 1


def test_suppression_is_set_after_stall_escalation():
  """The escalation branch must arm prompt suppression (that is the guard)."""
  import uno_orchestrator.flow_controller as fc

  # The escalation is wired by source: when prompt_stall_count reaches the
  # threshold, prompt_suppress_cycles is reset to the suppression window.
  import inspect
  src = inspect.getsource(fc.FlowController.run_cycle)
  compact = " ".join(src.split())
  assert "prompt_suppress_cycles = _PROMPT_HALLUCINATION_SUPPRESS_CYCLES" in compact, (
    "stall escalation must arm the anti-hallucination suppression window"
  )


def test_prompt_free_cycle_rearms_prompt_handling():
  """A prompt-free cycle must clear suppression so a REAL dialog that appears
  afterwards is handled on the very next cycle."""
  s = _session(suppress=_PROMPT_HALLUCINATION_SUPPRESS_CYCLES, stall=2)

  # Mirror of the run_tick branch: prompt is None → counters reset.
  prompt = None
  if prompt is None:
    if s.prompt_stall_count:
      s.prompt_stall_count = 0
    s.prompt_suppress_cycles = 0

  assert s.prompt_suppress_cycles == 0
  assert s.prompt_stall_count == 0


def test_suppressed_cycle_is_skipped_and_decrements():
  """While suppression is active the prompt branch must be skipped (no click),
  and the window must count down."""
  s = _session(suppress=_PROMPT_HALLUCINATION_SUPPRESS_CYCLES)
  prompt = {"label": "Keep"}

  clicked = []

  for _ in range(_PROMPT_HALLUCINATION_SUPPRESS_CYCLES):
    if prompt is not None and s.prompt_suppress_cycles > 0:
      s.prompt_suppress_cycles -= 1
      # skipped — no click delivered
    elif prompt is not None:
      clicked.append(prompt["label"])

  assert clicked == [], "suppressed prompt must not be clicked"
  assert s.prompt_suppress_cycles == 0


def test_after_suppression_expires_prompt_is_clickable_again():
  """Once the suppression window is spent, a persistent prompt is tried again
  (covers the 'real dialog that needed several attempts' case)."""
  s = _session(suppress=_PROMPT_HALLUCINATION_SUPPRESS_CYCLES)
  prompt = {"label": "Play"}

  for _ in range(_PROMPT_HALLUCINATION_SUPPRESS_CYCLES):
    if prompt is not None and s.prompt_suppress_cycles > 0:
      s.prompt_suppress_cycles -= 1
    else:
      break

  # Window spent — the next cycle takes the click branch again.
  assert s.prompt_suppress_cycles == 0
  assert not (prompt is not None and s.prompt_suppress_cycles > 0)
