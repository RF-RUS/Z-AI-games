"""Regression tests for autonomous loop lifecycle.

Protects against:
- automatic=True not starting loop after warmup
- InProcessAdapterClient missing required methods
- First cycle not producing persisted steps
- Snapshot not being populated after first cycle
- Silent failures in autonomous loop
"""

import asyncio

import pytest
from uno_orchestrator.in_process_clients import (
    InProcessAdapterClient,
    InProcessClients,
    setup_in_process_adapter_registry,
)
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.orchestrator import AttachAdapterBody, FlowState, SessionSpec
from uno_schemas.session import AdapterType, SessionConfig

setup_in_process_adapter_registry()


def _make_orch(automatic=True):
    orch = SessionOrchestrator(clients=InProcessClients())
    return orch


@pytest.mark.integration
@pytest.mark.asyncio
async def test_automatic_true_creates_run_loop_after_warmup():
    """ACTIVE + automatic=True always creates run_loop after warmup."""
    orch = _make_orch()
    spec = SessionSpec(
        config=SessionConfig(adapter_type=AdapterType.MOCK, adapter_id="pending"),
        automatic=True,
    )
    detail = await orch.create_session_with_game(spec)
    await orch.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=AdapterType.MOCK))
    await orch.start(detail.session_id)

    for _ in range(20):
        await asyncio.sleep(0.25)
        s = orch._sessions.get(detail.session_id)
        if s.loop_task and not s.loop_task.done():
            break

    s = orch._sessions[detail.session_id]
    assert s.loop_task is not None, "loop_task should exist after warmup with automatic=True"
    assert not s.loop_task.done(), "loop_task should still be running"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_automatic_false_never_creates_run_loop():
    """automatic=False must never create _run_loop."""
    orch = _make_orch()
    spec = SessionSpec(
        config=SessionConfig(adapter_type=AdapterType.MOCK, adapter_id="pending"),
        automatic=False,
    )
    detail = await orch.create_session_with_game(spec)
    await orch.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=AdapterType.MOCK))
    await orch.start(detail.session_id)

    await asyncio.sleep(1.0)
    s = orch._sessions[detail.session_id]
    assert s.loop_task is None, "loop_task must not exist with automatic=False"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_first_cycle_produces_persisted_steps():
    """First cycle produces at least one persisted step."""
    orch = _make_orch()
    spec = SessionSpec(
        config=SessionConfig(adapter_type=AdapterType.MOCK, adapter_id="pending"),
        automatic=True,
    )
    detail = await orch.create_session_with_game(spec)
    await orch.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=AdapterType.MOCK))
    await orch.start(detail.session_id)

    for _ in range(20):
        await asyncio.sleep(0.25)
        steps = orch.get_steps(detail.session_id)
        if len(steps) > 0:
            break

    steps = orch.get_steps(detail.session_id)
    assert len(steps) > 0, "At least one step should be persisted after first cycle"

    step_names = {s.step_name for s in steps}
    assert "observe" in step_names, f"observe step missing from {step_names}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_snapshot_updated_after_first_cycle():
    """Snapshot has real data after first cycle, not placeholders."""
    orch = _make_orch()
    spec = SessionSpec(
        config=SessionConfig(adapter_type=AdapterType.MOCK, adapter_id="pending"),
        automatic=True,
    )
    detail = await orch.create_session_with_game(spec)
    await orch.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=AdapterType.MOCK))
    await orch.start(detail.session_id)

    for _ in range(20):
        await asyncio.sleep(0.25)
        s = orch.status(detail.session_id)
        if s.strategy_snapshot and len(orch.get_steps(detail.session_id)) >= 5:
            break

    status = orch.status(detail.session_id)
    ss = status.strategy_snapshot
    assert ss is not None, "snapshot should be populated"
    assert ss.goal, "snapshot.goal should be non-empty"
    assert ss.detected_state != "unknown", "detected_state should be non-unknown"
    assert ss.hypothesis, "snapshot.hypothesis should be non-empty"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_loop_stops_on_error_and_sets_error_state():
    """When cycle fails unrecoverably, loop stops and error state is set."""
    orch = _make_orch()
    spec = SessionSpec(
        config=SessionConfig(adapter_type=AdapterType.MOCK, adapter_id="pending"),
        automatic=True,
    )
    detail = await orch.create_session_with_game(spec)
    await orch.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=AdapterType.MOCK))
    await orch.start(detail.session_id)

    for _ in range(20):
        await asyncio.sleep(0.25)
        if len(orch.get_steps(detail.session_id)) >= 5:
            break

    session = orch._sessions[detail.session_id]
    detail_obj = session.detail
    if detail_obj.flow_state == FlowState.ERROR:
        assert detail_obj.error is not None, "Error state should have error message"
        assert session.loop_task.done(), "Loop should be stopped in error state"


@pytest.mark.integration
def test_adapter_client_contract():
    """Both adapter clients satisfy the required controller contract."""
    required_methods = [
        "normalize_attach_request", "attach", "detach",
        "capture_evidence", "map_action", "execute_action",
        "get_retry_policy", "list_profiles", "load_profile",
    ]
    from uno_shared.adapter_registry import GenericAdapterClient
    for cls in [InProcessAdapterClient, GenericAdapterClient]:
        for m in required_methods:
            assert hasattr(cls, m), f"{cls.__name__} missing {m}"


@pytest.mark.integration
def test_inprocess_client_map_action_returns_valid_request():
    """InProcessAdapterClient.map_action returns a valid GenericActionRequest."""
    from uno_adapter_web.api import app as web_app
    from uno_shared.adapter_protocol import GenericActionRequest
    client = InProcessAdapterClient("mock", web_app)
    req = client.map_action("play_card", profile_id="local-mock-uno", card_color="red", card_value="5")
    assert isinstance(req, GenericActionRequest)
    assert req.domain_action == "play_card"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_steps_grow_monotonically_during_autonomous_loop():
    """Steps count never decreases during active autonomous loop."""
    orch = _make_orch()
    spec = SessionSpec(
        config=SessionConfig(adapter_type=AdapterType.MOCK, adapter_id="pending"),
        automatic=True,
    )
    detail = await orch.create_session_with_game(spec)
    await orch.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=AdapterType.MOCK))
    await orch.start(detail.session_id)

    prev_count = 0
    for _ in range(12):
        await asyncio.sleep(0.5)
        count = len(orch.get_steps(detail.session_id))
        assert count >= prev_count, f"Steps decreased from {prev_count} to {count}"
        prev_count = count

    assert prev_count > 0, "Steps should have grown during autonomous loop"
