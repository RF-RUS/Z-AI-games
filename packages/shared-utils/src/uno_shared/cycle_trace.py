"""One record per agent cycle: the frame, what was perceived, what was decided.

WHY THIS EXISTS (and why it is not `adapter-web/agent_trace.py`)
---------------------------------------------------------------
Debugging this agent used to mean: restart 14 services, launch a real game, watch
the operator, grep four log files — a 30-minute loop per hypothesis, and every run
irreproducible because the game state differed. The existing web trace does not
help with that, for two reasons:

  1. It is Playwright-specific (it needs a `page`), so it never fires for the
     Windows adapter — which is the adapter that actually plays Ubisoft UNO.
  2. It records COUNTS, not CONTENT: `"top_card": extracted.get("top_card") is not
     None`, `"hand_cards": len(grounding.hand)`. You can see that nine cards were
     found, never WHICH nine. A corpus of booleans cannot be used to check whether
     perception got better or worse.

So this module writes the one artifact that makes perception testable offline: the
exact frame plus the FULL perceived board, side by side, per cycle. Once that
exists, `scripts/replay_perception.py` can re-run recognition over saved frames in
seconds, with no game, no services and no GPU — and a regression becomes a diff
instead of an argument.

DESIGN NOTES
------------
* Game-agnostic on purpose. Nothing here knows what a card is; it serializes
  whatever the perception payload contains. Adding Svintus must not require
  touching this file.
* Provenance is recorded, not inferred. `recognition_method` / `vlm_status` /
  `cv_build` travel with the record, because "9 cards at confidence 0.8" means
  something completely different coming from the VLM, the heuristic, or a mock.
  (A fabricated mock board once reached the agent at confidence 0.8 and it played a
  hand that did not exist on screen — see AGENT_LOG.md 2026-08-04.)
* Best-effort, always. Tracing must never break a cycle: every public function
  swallows its own exceptions and returns None.
* Bounded on disk. Frames are ~1–3 MB; a long session would otherwise fill the
  drive. Oldest cycle directories are pruned past AGENT_CYCLE_TRACE_KEEP.

Env:
  AGENT_CYCLE_TRACE=0        — disable (default: enabled; the whole point is that
                               the data exists BEFORE you know you need it)
  AGENT_CYCLE_TRACE_DIR=...  — root dir (default: artifacts/cycle_trace)
  AGENT_CYCLE_TRACE_KEEP=200 — cycle dirs to retain per session
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uno_shared.logging import get_logger

logger = get_logger("cycle_trace")

# Bump when the on-disk shape changes so the replay harness can refuse to compare
# records it does not understand instead of silently mis-reading old fixtures.
SCHEMA_VERSION = 2

_DEFAULT_DIR = Path("artifacts") / "cycle_trace"


def trace_enabled() -> bool:
  """Whether cycle tracing is on. Read per call, NOT cached at import time.

  Module-level env caching is a trap this repo has already hit: `vlm_provider`
  reads its flags at import, so "set the var and reload" silently does nothing.
  A per-call read costs nothing here and makes the flag behave as expected.
  """
  return os.getenv("AGENT_CYCLE_TRACE", "1") not in ("0", "", "false", "False")


def trace_root() -> Path:
  raw = os.getenv("AGENT_CYCLE_TRACE_DIR", "")
  return Path(raw) if raw else _DEFAULT_DIR


def _keep() -> int:
  try:
    return max(1, int(os.getenv("AGENT_CYCLE_TRACE_KEEP", "200")))
  except ValueError:
    return 200


def _now_iso() -> str:
  return datetime.now(UTC).isoformat(timespec="milliseconds")


def _jsonable(value: Any) -> Any:
  """Best-effort conversion of pydantic models / dataclasses / enums to plain JSON.

  Deliberately tolerant: a trace that loses one field is useful, a trace that
  raises while serializing is not.
  """
  if value is None or isinstance(value, (str, int, float, bool)):
    return value
  if isinstance(value, dict):
    return {str(k): _jsonable(v) for k, v in value.items()}
  if isinstance(value, (list, tuple, set)):
    return [_jsonable(v) for v in value]
  dump = getattr(value, "model_dump", None)  # pydantic v2
  if callable(dump):
    try:
      return _jsonable(dump(mode="json"))
    except Exception:  # noqa: BLE001
      pass
  if hasattr(value, "value") and type(value).__mro__[1].__name__ == "Enum":
    return value.value
  if hasattr(value, "__dict__"):
    return {k: _jsonable(v) for k, v in vars(value).items() if not k.startswith("_")}
  return str(value)


def _dump(value: Any) -> Any:
  """`_jsonable` that cannot fail. Same rule as `_safe_attr`: losing one field is
  acceptable, losing the cycle record is not."""
  try:
    return _jsonable(value)
  except Exception as exc:  # noqa: BLE001
    return f"<unserializable: {type(exc).__name__}>"


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
  """`getattr` that also survives an attribute which RAISES.

  Not paranoia: `getattr(o, "x", None)` only swallows AttributeError, and the objects
  passed in here are pydantic models and adapter payloads whose fields can be computed
  properties. One raising field must cost that ONE field, not the whole record — the
  frame is still worth keeping even when the observation is broken.
  (`recovery.format_exception_message` had the identical bug and it took down the
  failure handler itself while formatting a timeout.)
  """
  try:
    return getattr(obj, name, default)
  except Exception:  # noqa: BLE001
    return default


def _prune(session_dir: Path, keep: int) -> None:
  try:
    dirs = sorted((d for d in session_dir.iterdir() if d.is_dir()), key=lambda p: p.name)
    for old in dirs[:-keep]:
      shutil.rmtree(old, ignore_errors=True)
  except Exception:  # noqa: BLE001 — pruning is housekeeping, never fatal
    pass


def write_cycle_trace(
    *,
    session_id: str,
    cycle_index: int,
    correlation_id: str,
    game_type: str | None = None,
    screenshot: Any = None,
    observation: Any = None,
    legal_actions: Any = None,
    decision: Any = None,
    guard: Any = None,
    failed_at: Any = None,
    error: str | None = None,
    timings_ms: dict[str, int] | None = None,
    click: dict[str, Any] | None = None,
) -> Path | None:
  """Write one cycle directory: `frame.png` + `cycle.json`. Returns its path.

  Keyword-only by design — this is called from the middle of the agent loop where
  a positional-argument mix-up would silently mislabel a whole corpus.

  Must be called for FAILED cycles too. The frames worth having are exactly the
  ones where perception went wrong, and the previous trace only ever fired on the
  happy path.
  """
  if not trace_enabled():
    return None
  try:
    safe_session = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(session_id))[:64]
    session_dir = trace_root() / (safe_session or "unknown")
    dest = session_dir / f"{cycle_index:04d}"
    dest.mkdir(parents=True, exist_ok=True)

    frame: dict[str, Any] = {"file": None, "width": None, "height": None, "source_path": None}
    shot_path = _safe_attr(screenshot, "path") if screenshot is not None else None
    if shot_path:
      frame["source_path"] = str(shot_path)
      frame["width"] = _safe_attr(screenshot, "width")
      frame["height"] = _safe_attr(screenshot, "height")
      try:
        src = Path(shot_path)
        target = dest / f"frame{src.suffix or '.png'}"
        # Copy, not reference: the adapter's screenshot directory is recycled, so a
        # path recorded today points at a different frame tomorrow. A corpus of
        # dangling paths is worse than no corpus.
        shutil.copyfile(src, target)
        frame["file"] = target.name
      except Exception as exc:  # noqa: BLE001
        frame["copy_error"] = f"{type(exc).__name__}: {exc}"

    gs = _dump(_safe_attr(observation, "game_state")) or {}
    if not isinstance(gs, dict):
      # A non-dict board is not something the replay harness can compare, but it is
      # still evidence — keep it under a key instead of dropping the whole cycle.
      gs = {"_raw": gs}
    conf = _safe_attr(observation, "confidence")

    record: dict[str, Any] = {
      "schema_version": SCHEMA_VERSION,
      "timestamp": _now_iso(),
      "session_id": str(session_id),
      "cycle_index": cycle_index,
      "correlation_id": str(correlation_id),
      "game_type": game_type or _safe_attr(observation, "game_type"),
      "frame": frame,
      # The whole perceived board, verbatim — this is the field the replay harness
      # compares against, so it must NOT be reduced to counts.
      "perception": gs,
      "provenance": {
        "recognition_method": gs.get("recognition_method"),
        "vlm_status": gs.get("vlm_status"),
        "cv_build": gs.get("cv_build"),
        "source": gs.get("source"),
      },
      "confidence": {
        "overall": _safe_attr(conf, "overall"),
        "game_state": _safe_attr(conf, "game_state"),
        "game_elements": _safe_attr(conf, "game_elements"),
      },
      "legal_actions": _dump(legal_actions),
      "decision": _dump(decision),
      "guard": _dump(guard),
      # Whether the executed click actually took effect (zone diff before/after),
      # and what was retried where — None for cycles that clicked nothing.
      "click": _dump(click) if click is not None else None,
      "outcome": {
        "failed_at": _dump(failed_at),
        "error": error,
        "ok": error is None and failed_at is None,
      },
      "timings_ms": timings_ms or {},
    }

    (dest / "cycle.json").write_text(
      json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    _prune(session_dir, _keep())
    return dest
  except Exception as exc:  # noqa: BLE001 — tracing must never break the agent loop
    logger.warning("cycle_trace_failed", error=f"{type(exc).__name__}: {exc}", session_id=str(session_id))
    return None
