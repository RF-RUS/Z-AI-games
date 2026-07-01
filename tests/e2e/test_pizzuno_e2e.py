"""Pizzuno E2E test — regression guard for confirmed flow.

Runs full cycle: attach → observe → perceive → decide → guard → execute
against real Pizzuno site. Requires network + Playwright.

Run with: pytest tests/e2e/test_pizzuno_e2e.py -m e2e
"""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "session-orchestrator" / "src"))
sys.path.insert(0, str(ROOT / "services" / "adapter-web" / "src"))
sys.path.insert(0, str(ROOT / "services" / "uno-core" / "src"))
sys.path.insert(0, str(ROOT / "services" / "perception-service" / "src"))
sys.path.insert(0, str(ROOT / "services" / "decision-service" / "src"))
sys.path.insert(0, str(ROOT / "services" / "policy-guard" / "src"))

from uno_orchestrator.in_process_clients import InProcessClients
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.orchestrator import AttachAdapterBody, SessionSpec
from uno_schemas.session import AdapterType, SessionConfig


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pizzuno_e2e_full_cycle():
    """Full E2E cycle on real Pizzuno: attach → observe → decide → execute."""
    clients = InProcessClients()
    orch = SessionOrchestrator(clients=clients)

    spec = SessionSpec(
        config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
        web_profile_id="real-unoh-web",
        automatic=False,
    )
    detail = await orch.create_session_with_game(spec)
    assert detail.session_id is not None
    assert detail.game_id is not None

    body = AttachAdapterBody(
        adapter_type=AdapterType.WEB,
        profile_id="real-unoh-web",
    )
    detail = await orch.attach_adapter(detail.session_id, body)
    bindings = [b for b in detail.adapter_bindings if b.attached]
    assert len(bindings) == 1, f"Expected 1 attached binding, got {len(bindings)}"
    assert bindings[0].adapter_id is not None

    resp = await orch.start(detail.session_id)
    assert resp.flow_state.value in ("active", "attaching")

    for _ in range(30):
        await asyncio.sleep(1.0)
        st = orch.status(detail.session_id)
        if st and st.flow_state.value == "active":
            break
        if st and st.flow_state.value == "error":
            pytest.fail(f"Warmup failed: {st.error}")
    else:
        pytest.fail("Warmup timed out after 30s")

    result = await orch.run_tick(detail.session_id)
    assert "error" not in result, f"Tick failed: {result}"
    assert result.get("action") is not None, f"No action in result: {result}"
    assert result.get("guard", {}).get("allowed") is True, f"Guard blocked: {result}"

    action = result["action"]
    assert action["action_type"] in ("play_card", "draw_card"), f"Unexpected action: {action}"

    status = orch.status(detail.session_id)
    assert status.flow_state.value == "active"
    assert status.error is None


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_pizzuno_observe_selectors():
    """Verify key Pizzuno selectors resolve after game starts."""
    from uno_adapter_web.registry import attach_adapter, get_adapter
    from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterRequest

    req = AttachWebAdapterRequest(
        session_id="smoke-selectors",
        mode=AdapterMode.PLAYWRIGHT,
        profile_id="real-unoh-web",
        headless=True,
    )
    resp = await attach_adapter(req)
    assert resp.attached, f"Attach failed: {resp.message}"

    adapter = get_adapter(resp.adapter_id)
    assert adapter is not None

    evidence = await adapter.capture_evidence(resp.adapter_id)
    snapshot = evidence.dom_snapshot
    assert snapshot is not None
    assert len(snapshot.nodes) > 0, "No DOM nodes extracted"

    node_tags = [n.tag for n in snapshot.nodes]
    assert "game_root" in node_tags, f"game_root not found in {node_tags}"
    assert "hand_area" in node_tags, f"hand_area not found in {node_tags}"

    await adapter.detach()
