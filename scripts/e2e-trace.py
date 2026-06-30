#!/usr/bin/env python3
"""E2E cycle trace — attach → perceive → decide → execute on real sites.

Usage:
  python scripts/e2e-trace.py --profile real-unoh-web
  python scripts/e2e-trace.py --profile scuffed-uno-web
  python scripts/e2e-trace.py --profile local-mock-uno --url http://127.0.0.1:8765/
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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

STEP_RESULTS = []


def trace_step(name: str, start: float, success: bool, detail: str = "", data: dict | None = None):
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    status = "OK" if success else "FAIL"
    entry = {
        "step": name,
        "status": "ok" if success else "FAIL",
        "elapsed_ms": elapsed_ms,
        "detail": detail,
    }
    if data:
        entry["data"] = data
    STEP_RESULTS.append(entry)
    print(f"\n{'='*60}")
    print(f"  STEP: {name}")
    print(f"  STATUS: {status} ({elapsed_ms}ms)")
    if detail:
        print(f"  DETAIL: {detail}")
    if data:
        print(f"  DATA: {json.dumps(data, indent=2, default=str)[:500]}")
    print(f"{'='*60}")
    return success


async def run_e2e_trace(profile_id: str, target_url: str | None = None, tick_count: int = 1):
    print(f"\n{'#'*60}")
    print(f"  E2E TRACE: profile={profile_id}, url={target_url}")
    print(f"{'#'*60}")

    clients = InProcessClients()
    orch = SessionOrchestrator(clients=clients)

    # --- Step 1: Create session ---
    t0 = time.perf_counter()
    try:
        spec = SessionSpec(
            config=SessionConfig(adapter_type=AdapterType.WEB, adapter_id="pending"),
            web_profile_id=profile_id,
            target_url=target_url,
            automatic=False,
        )
        detail = await orch.create_session_with_game(spec)
        trace_step("1. create_session", t0, True, f"session_id={detail.session_id[:8]}, game_id={detail.game_id}")
    except Exception as exc:
        trace_step("1. create_session", t0, False, str(exc))
        return

    # --- Step 2: Attach adapter ---
    t0 = time.perf_counter()
    try:
        body = AttachAdapterBody(
            adapter_type=AdapterType.WEB,
            target_url=target_url,
            profile_id=profile_id,
        )
        detail = await orch.attach_adapter(detail.session_id, body)
        bindings = [b for b in detail.adapter_bindings if b.attached]
        adapter_id = bindings[0].adapter_id if bindings else None
        trace_step("2. attach_adapter", t0, True, f"adapter_id={adapter_id[:8] if adapter_id else 'NONE'}")
    except Exception as exc:
        diagnostics = getattr(exc, "diagnostics", None)
        detail_str = str(exc)
        if diagnostics:
            detail_str += f"\n  diagnostics.failed_stage={diagnostics.failed_stage}"
            if diagnostics.page_goto:
                detail_str += f"\n  page_goto.final_url={diagnostics.page_goto.final_url}"
                detail_str += f"\n  page_goto.network_reachable={diagnostics.page_goto.network_reachability.reachable if diagnostics.page_goto.network_reachability else 'N/A'}"
        trace_step("2. attach_adapter", t0, False, detail_str)
        return

    # --- Step 3: Start session (warmup) ---
    t0 = time.perf_counter()
    try:
        resp = await orch.start(detail.session_id)
        trace_step("3. start_warmup", t0, resp.flow_state.value in ("active", "attaching"), resp.message)
        # Wait for warmup to complete
        if resp.flow_state.value == "attaching":
            print("  Waiting for observe warmup...")
            for i in range(60):
                await asyncio.sleep(1.0)
                st = orch.status(detail.session_id)
                if st and st.flow_state.value == "active":
                    trace_step("3b. warmup_complete", t0, True, f"completed after {i+1}s")
                    break
                if st and st.flow_state.value == "error":
                    trace_step("3b. warmup_complete", t0, False, f"error after {i+1}s: {st.error}")
                    return
            else:
                trace_step("3b. warmup_complete", t0, False, "warmup timed out after 60s")
                return
    except Exception as exc:
        trace_step("3. start_warmup", t0, False, str(exc))
        return

    # --- Step 4-N: Run ticks ---
    for tick_num in range(1, tick_count + 1):
        print(f"\n{'#'*60}")
        print(f"  TICK {tick_num}/{tick_count}")
        print(f"{'#'*60}")

        t0 = time.perf_counter()
        try:
            result = await orch.run_tick(detail.session_id)
            is_ok = not result.get("error") and not result.get("skipped")
            detail_str = json.dumps(result, indent=2, default=str)[:1000]
            trace_step(f"tick_{tick_num}", t0, is_ok, detail_str)
        except Exception as exc:
            trace_step(f"tick_{tick_num}", t0, False, str(exc))

    # --- Final status ---
    t0 = time.perf_counter()
    status = orch.status(detail.session_id)
    if status:
        trace_step("final_status", t0, True, f"flow_state={status.flow_state.value}, error={status.error}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print("  E2E TRACE SUMMARY")
    print(f"{'='*60}")
    failed = [s for s in STEP_RESULTS if s["status"] == "FAIL"]
    passed = [s for s in STEP_RESULTS if s["status"] == "ok"]
    print(f"  Passed: {len(passed)}/{len(STEP_RESULTS)}")
    print(f"  Failed: {len(failed)}/{len(STEP_RESULTS)}")
    if failed:
        print("\n  FAILED STEPS:")
        for f in failed:
            print(f"    - {f['step']}: {f['detail'][:200]}")
    print(f"\n{'='*60}")

    return {
        "profile": profile_id,
        "passed": len(passed),
        "failed": len(failed),
        "steps": STEP_RESULTS,
    }


async def main():
    p = argparse.ArgumentParser(description="E2E cycle trace")
    p.add_argument("--profile", default="local-mock-uno", help="Profile ID")
    p.add_argument("--url", default=None, help="Target URL (optional)")
    p.add_argument("--ticks", type=int, default=1, help="Number of ticks to run")
    args = p.parse_args()

    result = await run_e2e_trace(args.profile, args.url, args.ticks)
    print("\nFull result saved to stdout as JSON:")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
