"""Unit-test isolation: no live services, no real artifacts.

Why this file exists (2026-08-27)
---------------------------------
Two leaks were observed while the real UNO game was running:

1. TEST CYCLES IN THE REAL TRACE CORPUS. ``create_session_with_game`` +
   ``run_tick`` / ``run_cycle`` write a ``write_cycle_trace`` record in a
   ``finally``. ``AGENT_CYCLE_TRACE`` defaults to enabled and
   ``AGENT_CYCLE_TRACE_DIR`` to ``artifacts/cycle_trace`` — so unit tests that
   ran a cycle without pointing the trace dir at ``tmp_path`` dropped
   ``frame=None`` / ``summary='test'`` records straight into the real corpus,
   interleaved with the live agent's cycles. A replay corpus polluted by mock
   boards is exactly the "confidently wrong" trap this repo keeps fixing.

2. TEST GAMES IN THE LIVE ``uno-core``. ``SessionOrchestrator`` is constructed
   with a REAL ``ServiceClients``; ``create_session_with_game`` calls
   ``clients.create_game`` (HTTP POST to the running uno-core) and only catches
   the exception afterwards. With the backend up, every such test created a real
   in-memory game in the operator's running core (visible as ``POST /games 200``
   bursts in ``logs/uno-core.log``).

Fix: for unit tests only, redirect the trace dir to a per-test tmp dir and point
every service URL at the discard port (127.0.0.1:9) so any unmocked client call
fails fast with ConnectionRefused instead of reaching a live service. Contract /
smoke / e2e suites intentionally talk to real servers and are NOT affected —
they do not live under tests/unit.
"""

from __future__ import annotations

import pytest

from uno_schemas.api import SERVICE_PORTS

_DEAD = "http://127.0.0.1:9"  # port 9 (discard): connection refused, no service can bind it


@pytest.fixture(autouse=True)
def isolate_unit_test_env(monkeypatch, tmp_path):
  # 1) cycle traces land in a per-test scratch dir, never in artifacts/cycle_trace.
  monkeypatch.setenv("AGENT_CYCLE_TRACE_DIR", str(tmp_path / "cycle_trace"))

  # 2) every service URL points at a dead port: unmocked ServiceClients calls
  #    fail immediately instead of creating games / sessions in the live backend.
  for service in SERVICE_PORTS:
    monkeypatch.setenv(f"UNO_SERVICE_URL_{service.upper().replace('-', '_')}", _DEAD)

  yield
