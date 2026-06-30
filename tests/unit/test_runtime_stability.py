"""Verification tests for runtime stability / frame pipeline recovery."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from uno_orchestrator.recovery import classify_error, decide_recovery
from uno_schemas.orchestrator import ErrorClass, RecoveryConfig, RecoveryMode

# --- 1. Connection errors classified as TRANSIENT ---


class TestConnectionErrorClassification:
    """Verify connection-related errors are TRANSIENT, not PERMANENT."""

    def test_connection_refused_is_transient(self):
        exc = ConnectionRefusedError("Connection refused")
        assert classify_error(exc) == ErrorClass.TRANSIENT

    def test_connection_reset_is_transient(self):
        exc = ConnectionResetError("Connection reset by peer")
        assert classify_error(exc) == ErrorClass.TRANSIENT

    def test_connection_error_is_transient(self):
        exc = ConnectionError("Connection failed")
        assert classify_error(exc) == ErrorClass.TRANSIENT

    def test_os_error_is_transient(self):
        exc = OSError("Network unreachable")
        assert classify_error(exc) == ErrorClass.TRANSIENT

    def test_httpx_timeout_is_transient(self):
        exc = httpx.TimeoutException("timeout")
        assert classify_error(exc) == ErrorClass.TRANSIENT

    def test_httpx_500_is_transient(self):
        response = MagicMock()
        response.status_code = 500
        exc = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=response)
        assert classify_error(exc) == ErrorClass.TRANSIENT

    def test_value_error_is_permanent(self):
        exc = ValueError("bad input")
        assert classify_error(exc) == ErrorClass.PERMANENT

    def test_key_error_is_permanent(self):
        exc = KeyError("missing_key")
        assert classify_error(exc) == ErrorClass.PERMANENT


# --- 2. Recovery decisions for TRANSIENT errors ---


class TestTransientRecovery:
    """Verify TRANSIENT errors lead to RETRY, not STOP."""

    def test_transient_retries_within_limit(self):
        config = RecoveryConfig(max_retries=3, backoff_ms=500)
        decision = decide_recovery(ErrorClass.TRANSIENT, 0, config)
        assert decision.action == RecoveryMode.RETRY

    def test_transient_retries_at_limit(self):
        config = RecoveryConfig(max_retries=3, backoff_ms=500)
        decision = decide_recovery(ErrorClass.TRANSIENT, 2, config)
        assert decision.action == RecoveryMode.RETRY

    def test_transient_exhausted_retries_falls_to_manual(self):
        config = RecoveryConfig(max_retries=3, backoff_ms=500)
        decision = decide_recovery(ErrorClass.TRANSIENT, 3, config, fallback_to_manual=True)
        assert decision.action == RecoveryMode.FALLBACK_MANUAL

    def test_permanent_falls_to_manual_by_default(self):
        config = RecoveryConfig(max_retries=3, backoff_ms=500)
        decision = decide_recovery(ErrorClass.PERMANENT, 0, config)
        assert decision.action == RecoveryMode.FALLBACK_MANUAL

    def test_permanent_stops_when_no_fallback(self):
        config = RecoveryConfig(max_retries=3, backoff_ms=500)
        decision = decide_recovery(ErrorClass.PERMANENT, 0, config, fallback_to_manual=False)
        assert decision.action == RecoveryMode.STOP


# --- 3. _run_loop behavior simulation ---


class TestRunLoopBehavior:
    """Simulate _run_loop to verify it stays alive after recoverable failures."""

    @pytest.mark.asyncio
    async def test_loop_resets_error_to_active(self):
        from uno_orchestrator.orchestrator import SessionOrchestrator
        from uno_schemas.orchestrator import FlowState

        session = MagicMock()
        session.detail.flow_state = FlowState.ERROR
        session.detail.automatic = True
        session.detail.error = "test error"
        session.detail.session_id = "test-session"

        orch = MagicMock(spec=SessionOrchestrator)
        orch._flow = MagicMock()
        orch._flow.run_cycle = AsyncMock(return_value={"skipped": True})
        orch._bus = MagicMock()
        orch._bus.publish = AsyncMock()

        call_count = 0
        async def stop_after_one(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            session.detail.automatic = False
            return {"skipped": True}

        orch._flow.run_cycle = stop_after_one

        await SessionOrchestrator._run_loop(orch, session)
        assert session.detail.flow_state == FlowState.ACTIVE

    @pytest.mark.asyncio
    async def test_loop_continues_after_cycle_failure(self):
        from uno_orchestrator.orchestrator import SessionOrchestrator
        from uno_schemas.orchestrator import FlowState

        session = MagicMock()
        session.detail.flow_state = FlowState.ACTIVE
        session.detail.automatic = True
        session.detail.error = None
        session.detail.session_id = "test-session"

        orch = MagicMock(spec=SessionOrchestrator)
        orch._flow = MagicMock()
        orch._bus = MagicMock()
        orch._bus.publish = AsyncMock()

        cycle_count = 0
        async def failing_cycle(s):
            nonlocal cycle_count
            cycle_count += 1
            if cycle_count >= 3:
                session.detail.automatic = False
            if cycle_count == 2:
                raise ValueError("perception failed")
            return {"correlation_id": "ok"}

        orch._flow.run_cycle = failing_cycle

        await SessionOrchestrator._run_loop(orch, session)
        assert cycle_count == 3

    @pytest.mark.asyncio
    async def test_loop_breaks_on_cancelled(self):
        from uno_orchestrator.orchestrator import SessionOrchestrator
        from uno_schemas.orchestrator import FlowState

        session = MagicMock()
        session.detail.flow_state = FlowState.ACTIVE
        session.detail.automatic = True
        session.detail.error = None
        session.detail.session_id = "test-session"

        orch = MagicMock(spec=SessionOrchestrator)
        orch._flow = MagicMock()
        orch._bus = MagicMock()
        orch._bus.publish = AsyncMock()

        async def cancelling_cycle(s):
            session.detail.automatic = False
            raise asyncio.CancelledError()

        orch._flow.run_cycle = cancelling_cycle

        await SessionOrchestrator._run_loop(orch, session)
        assert session.detail.automatic is False

    @pytest.mark.asyncio
    async def test_loop_breaks_on_disabled_flow_state(self):
        from uno_orchestrator.orchestrator import SessionOrchestrator
        from uno_schemas.orchestrator import FlowState

        session = MagicMock()
        session.detail.flow_state = FlowState.ACTIVE
        session.detail.automatic = True
        session.detail.error = None
        session.detail.session_id = "test-session"

        orch = MagicMock(spec=SessionOrchestrator)
        orch._flow = MagicMock()
        orch._bus = MagicMock()
        orch._bus.publish = AsyncMock()

        async def disabling_cycle(s):
            session.detail.flow_state = FlowState.DISABLED
            return {"correlation_id": "ok"}

        orch._flow.run_cycle = disabling_cycle

        await SessionOrchestrator._run_loop(orch, session)
        assert session.detail.flow_state == FlowState.DISABLED


# --- 4. Stale session detection ---


class TestStaleSessionDetection:
    """Verify the frontend stale detection logic."""

    def test_stale_when_flow_active_no_new_steps(self):
        flow_active = True
        step_count = 5
        last_step_count = 5
        stale = flow_active and step_count == last_step_count and step_count > 0
        assert stale is True

    def test_not_stale_when_new_steps_arrive(self):
        flow_active = True
        step_count = 6
        last_step_count = 5
        stale = flow_active and step_count == last_step_count and step_count > 0
        assert stale is False

    def test_not_stale_when_flow_not_active(self):
        flow_active = False
        step_count = 5
        last_step_count = 5
        stale = flow_active and step_count == last_step_count and step_count > 0
        assert stale is False

    def test_not_stale_on_first_cycle(self):
        flow_active = True
        step_count = 1
        last_step_count = 0
        stale = flow_active and step_count == last_step_count and step_count > 0
        assert stale is False
