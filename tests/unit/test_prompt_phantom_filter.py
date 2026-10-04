"""Anti-hallucination prompt filtering (turn gate + coordinate stability).

Session 3bfacb8a (2026-08-29): the VLM (7b) kept reporting a Play/Keep dialog
on the OPPONENT's turn. Play/Keep modals only exist on the player's own turn,
so any prompt reported while `whose_turn == "opponent"` is by definition a
phantom. The old confirmation-based guard (3x unconfirmed -> suppress) was
defeated because opponent-turn board animations pushed change_ratio above the
0.05 "confirmed" threshold, resetting the stall counter.

`_filter_phantom_prompts` adds two reliable signals that do not depend on
click confirmation:

* TURN GATE: whose_turn == "opponent" -> drop every reported prompt.
* COORDINATE STABILITY: a label re-reported > _PROMPT_COORD_STABILITY_PX px
  from its last known position is a phantom for this cycle (real dialog
  buttons stay put; VLM phantoms wander 100+ px between frames).
"""

from types import SimpleNamespace

from uno_orchestrator.flow_controller import (
  _PROMPT_COORD_STABILITY_PX,
  _filter_phantom_prompts,
  RuntimeSession,
)


def _session():
  detail = SimpleNamespace(session_id="s1", config=SimpleNamespace(dry_run=False))
  spec = SimpleNamespace()
  s = RuntimeSession(detail=detail, spec=spec)
  return s


PLAY = {"label": "Play", "center": {"x": 500, "y": 600}}
KEEP = {"label": "Keep", "center": {"x": 600, "y": 600}}


def test_turn_gate_drops_prompts_on_opponent_turn():
  s = _session()
  kept = _filter_phantom_prompts(s, [PLAY, KEEP], "opponent", "s1")
  assert kept == []
  # Coordinate memory must NOT be refreshed with phantom positions.
  assert s.last_prompt_coord == {}


def test_turn_gate_allows_prompts_on_own_turn():
  s = _session()
  kept = _filter_phantom_prompts(s, [PLAY, KEEP], "self", "s1")
  assert [p["label"] for p in kept] == ["Play", "Keep"]
  # Own-turn positions become the stability baseline.
  assert s.last_prompt_coord == {"play": (500.0, 600.0), "keep": (600.0, 600.0)}


def test_unknown_turn_passes_prompts():
  """whose_turn unknown/absent -> no turn-gate; coordinates still track."""
  s = _session()
  kept = _filter_phantom_prompts(s, [PLAY], None, "s1")
  assert [p["label"] for p in kept] == ["Play"]
  kept = _filter_phantom_prompts(s, [PLAY], "unknown", "s1")
  assert [p["label"] for p in kept] == ["Play"]


def test_stable_coords_pass():
  s = _session()
  _filter_phantom_prompts(s, [PLAY], "self", "s1")
  # Same position next cycle -> kept.
  kept = _filter_phantom_prompts(s, [{"label": "Play", "center": {"x": 501, "y": 600}}], "self", "s1")
  assert [p["label"] for p in kept] == ["Play"]


def test_wandering_coords_filtered():
  """A label jumping > stability px between cycles is a phantom for this cycle."""
  s = _session()
  _filter_phantom_prompts(s, [PLAY], "self", "s1")
  # Jump to (700, 500) — 223 px away -> filtered.
  kept = _filter_phantom_prompts(s, [{"label": "Play", "center": {"x": 700, "y": 500}}], "self", "s1")
  assert kept == []
  # The phantom position must NOT become the new baseline, so the next cycle's
  # return to the real position is still within range of the ORIGINAL baseline.
  assert s.last_prompt_coord == {"play": (500.0, 600.0)}


def test_fresh_label_no_baseline_is_kept():
  """A label never seen before has no baseline -> always kept (a real new dialog)."""
  s = _session()
  kept = _filter_phantom_prompts(s, [PLAY, KEEP], "self", "s1")
  assert {p["label"] for p in kept} == {"Play", "Keep"}


def test_empty_prompts_clear_memory():
  s = _session()
  _filter_phantom_prompts(s, [PLAY, KEEP], "self", "s1")
  _filter_phantom_prompts(s, [], "self", "s1")
  assert s.last_prompt_coord == {}
  # After the dialog is gone and reappears, it is compared against nothing -> kept.
  kept = _filter_phantom_prompts(s, [{"label": "Play", "center": {"x": 999, "y": 999}}], "self", "s1")
  assert [p["label"] for p in kept] == ["Play"]


def test_malformed_center_passes_through():
  s = _session()
  kept = _filter_phantom_prompts(s, [{"label": "Play", "center": {"x": "bad"}}], "self", "s1")
  assert len(kept) == 1


def test_constant_sane():
  assert _PROMPT_COORD_STABILITY_PX > 0
