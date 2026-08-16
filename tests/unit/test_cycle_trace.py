"""Tests for the cycle-trace writer.

Runnable with no game, no services and no screenshots — which is the point: the
trace writer is the foundation the offline perception corpus is built on, so if it
silently drops the board or dies inside the agent loop, everything above it is
worthless.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from uno_shared.cycle_trace import trace_enabled, write_cycle_trace


def _frame(tmp_path: Path) -> SimpleNamespace:
  src = tmp_path / "shot.png"
  src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
  return SimpleNamespace(path=str(src), width=1296, height=759)


def _observation(game_state: dict) -> SimpleNamespace:
  return SimpleNamespace(
    game_state=game_state,
    game_type="uno",
    confidence=SimpleNamespace(overall=0.71, game_state=0.5, game_elements=0.4),
  )


def test_writes_frame_and_full_board(tmp_path, monkeypatch) -> None:
  monkeypatch.setenv("AGENT_CYCLE_TRACE", "1")
  monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))

  hand = [{"color": "red", "value": "6"}, {"color": "blue", "value": "9"}]
  dest = write_cycle_trace(
    session_id="sess-1",
    cycle_index=7,
    correlation_id="cid-1",
    screenshot=_frame(tmp_path),
    observation=_observation({
      "screen_type": "in_game",
      "top_card": {"color": "red", "value": "6"},
      "hand_cards": hand,
      "recognition_method": "vlm",
      "vlm_status": "ok",
    }),
  )
  assert dest is not None
  record = json.loads((dest / "cycle.json").read_text(encoding="utf-8"))

  # The frame must be COPIED, not referenced: the adapter recycles its screenshot
  # directory, so a recorded path points at a different frame tomorrow.
  assert (dest / "cycle.json").is_file()
  assert (dest / record["frame"]["file"]).is_file()
  assert record["frame"]["source_path"].endswith("shot.png")

  # The whole hand, not a count. A corpus of counts cannot detect a board that is
  # the right SIZE and the wrong CONTENT — which is exactly how the agent came to
  # play a blue card onto a red one.
  assert record["perception"]["hand_cards"] == hand
  assert record["perception"]["top_card"] == {"color": "red", "value": "6"}

  # Provenance travels with the record: 2 cards from the VLM, the heuristic or a
  # mock are three different facts.
  assert record["provenance"]["recognition_method"] == "vlm"
  assert record["provenance"]["vlm_status"] == "ok"
  assert record["outcome"]["ok"] is True


def test_records_failed_cycles(tmp_path, monkeypatch) -> None:
  """The frames worth keeping are the ones where perception went wrong."""
  monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
  dest = write_cycle_trace(
    session_id="sess-1",
    cycle_index=1,
    correlation_id="cid-2",
    screenshot=_frame(tmp_path),
    observation=_observation({"screen_type": "unknown", "hand_cards": []}),
    failed_at="perceive",
    error="confidence 0.1 < 0.4",
  )
  assert dest is not None
  record = json.loads((dest / "cycle.json").read_text(encoding="utf-8"))
  assert record["outcome"] == {"failed_at": "perceive", "error": "confidence 0.1 < 0.4", "ok": False}
  assert (dest / record["frame"]["file"]).is_file()


def test_survives_garbage_input(tmp_path, monkeypatch) -> None:
  """Tracing must never break a cycle — it runs in a `finally` inside run_cycle."""
  monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))

  class Exploding:
    @property
    def game_state(self):
      raise RuntimeError("boom")

  # A missing screenshot, an object that raises on attribute access, and a
  # non-serializable decision must all still produce a record.
  dest = write_cycle_trace(
    session_id="sess/../../weird id",
    cycle_index=2,
    correlation_id="cid-3",
    screenshot=SimpleNamespace(path="/nonexistent/frame.png", width=1, height=1),
    observation=None,
    decision=object(),
    guard={"allowed": True},
  )
  assert dest is not None
  record = json.loads((dest / "cycle.json").read_text(encoding="utf-8"))
  assert record["perception"] == {}
  # Path traversal in a session id must not escape the trace root.
  assert (tmp_path / "trace") in dest.parents

  # An attribute that RAISES must cost that one field, not the whole record. Note
  # `getattr(o, "x", None)` does NOT cover this — its default only catches
  # AttributeError — and the identical bug in recovery.format_exception_message took
  # down the failure handler itself while formatting a timeout.
  exploded = write_cycle_trace(
    session_id="s", cycle_index=3, correlation_id="c", observation=Exploding()
  )
  assert exploded is not None
  assert json.loads((exploded / "cycle.json").read_text(encoding="utf-8"))["perception"] == {}


def test_disabled_writes_nothing(tmp_path, monkeypatch) -> None:
  monkeypatch.setenv("AGENT_CYCLE_TRACE", "0")
  monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
  assert trace_enabled() is False
  assert write_cycle_trace(session_id="s", cycle_index=1, correlation_id="c") is None
  assert not (tmp_path / "trace").exists()


def test_prunes_old_cycles(tmp_path, monkeypatch) -> None:
  """A session is hours long and frames are megabytes — the corpus must stay bounded."""
  monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "trace"))
  monkeypatch.setenv("AGENT_CYCLE_TRACE_KEEP", "3")
  for i in range(1, 8):
    write_cycle_trace(
      session_id="s", cycle_index=i, correlation_id="c", screenshot=_frame(tmp_path)
    )
  kept = sorted(p.name for p in (tmp_path / "trace" / "s").iterdir())
  assert kept == ["0005", "0006", "0007"]
