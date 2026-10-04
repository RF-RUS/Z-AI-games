#!/usr/bin/env python3
"""Evaluation harness — the platform's quality gate (see docs/EVALUATION.md).

Runs scenario datasets through the full operator pipeline IN-PROCESS (ASGI, no
live services needed) and emits a single report containing every metric an
operator cares about:

  - success_rate / avg_score        scenario pass rate
  - policy_accept_rate              guard blocks (safety health)
  - shadow_agree_rate               strategy disagreement (when shadow on)
  - avg_ticks                       loop efficiency

Results are appended to models/benchmarks/history.jsonl so every commit/nightly
run extends one long time series — the "quality curve". A regression shows up as
a dip you can bisect against git history.

Usage:
  python scripts/run-eval.py                      # smoke dataset (fast, ~10 s)
  python scripts/run-eval.py --dataset full_operator
  python scripts/run-eval.py --dataset full_operator --min-success 0.8   # CI gate
  python scripts/run-eval.py --dry-run-session    # dry-run mode: actions not executed
  python scripts/run-eval.py --shadow             # enable shadow evaluation in scenarios

Exit code: 0 when success_rate >= --min-success (default: no gate), else 1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (
    ROOT / "packages" / "schemas" / "src",
    ROOT / "packages" / "shared-utils" / "src",
    ROOT / "services" / "session-orchestrator" / "src",
):
    sys.path.insert(0, str(p))

HISTORY_FILE = ROOT / "models" / "benchmarks" / "history.jsonl"


async def run(args: argparse.Namespace) -> dict:
    from uno_orchestrator.in_process_clients import InProcessClients, setup_in_process_adapter_registry
    from uno_orchestrator.orchestrator import SessionOrchestrator
    from uno_schemas.operator_evaluation import OperatorScenario
    from uno_schemas.orchestrator import AttachAdapterBody, SessionSpec
    from uno_schemas.session import SessionConfig

    setup_in_process_adapter_registry()
    clients = InProcessClients()
    orch = SessionOrchestrator(clients=clients)

    dataset_dir = ROOT / "orchestrator" / "evaluation" / "datasets"
    rows = [
        OperatorScenario.model_validate_json(line)
        for line in (dataset_dir / f"{args.dataset}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    tick_results_by_case: list[list[dict]] = []
    errors: list[str | None] = []
    steps_by_case: list[int] = []
    t0 = time.perf_counter()

    for scenario in rows:
        ticks: list[dict] = []
        err: str | None = None
        try:
            spec = SessionSpec(config=SessionConfig(
                adapter_type=scenario.adapter_type,
                adapter_id="pending",
                min_confidence=scenario.min_confidence,
                model_assist_enabled=scenario.model_assist or args.shadow,
                dry_run=args.dry_run_session,
                shadow_evaluation=args.shadow,
            ))
            detail = await orch.create_session_with_game(spec)
            await orch.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=scenario.adapter_type))
            await orch.start(detail.session_id)
            # Warmup (observe ready + VLM warm) runs async after start(); wait for it
            # like the operator loop does, otherwise the first ticks are all skips.
            for _ in range(100):
                if orch._sessions[detail.session_id].observe_ready:
                    break
                await asyncio.sleep(0.15)
            for _ in range(scenario.max_ticks):
                ticks.append(await orch.run_tick(detail.session_id))
            steps_by_case.append(len(orch.get_steps(detail.session_id)))
            await orch.stop(detail.session_id)
        except Exception as exc:  # noqa: BLE001 — record, keep going
            err = f"{type(exc).__name__}: {exc}"
            steps_by_case.append(0)
        tick_results_by_case.append(ticks)
        errors.append(err)

    duration_s = round(time.perf_counter() - t0, 2)

    legal_ok = sum(
        1 for t in tick_results_by_case
        if any(not x.get("skipped") and (x.get("action") or x.get("planned_action") or x.get("prompt_clicked")) for x in t)
    )
    policy_blocked = sum(1 for t in tick_results_by_case if any(x.get("guard_blocked") for x in t))
    total_ticks = sum(len(t) for t in tick_results_by_case)
    failures = [sc.scenario_id for sc, e in zip(rows, errors) if e]

    shadow_rates = []
    for ticks in tick_results_by_case:
        agree = [x["shadow"] for x in ticks if isinstance(x.get("shadow"), bool)]
        if agree:
            shadow_rates.append(sum(agree) / len(agree))
    shadow_agree_rate = round(sum(shadow_rates) / len(shadow_rates), 4) if shadow_rates else None

    # Simple per-scenario scoring mirroring evaluation_runner semantics
    ok_cases = 0
    for scenario, ticks, err, case_steps in zip(rows, tick_results_by_case, errors, steps_by_case):
        expected = scenario.expected
        has_action = any(x.get("action") or x.get("planned_action") or x.get("prompt_clicked") for x in ticks)
        no_fatal = err is None and not any(x.get("error") for x in ticks)
        success = True
        if expected.get("has_action"):
            success = has_action and no_fatal
        if expected.get("min_ticks"):
            success = success and len(ticks) >= int(expected["min_ticks"])
        if expected.get("min_steps"):
            success = success and case_steps >= int(expected["min_steps"])
        if expected.get("policy_allowed"):
            success = success and not any(x.get("guard_blocked") for x in ticks)
        ok_cases += int(success)
    success_rate = ok_cases / len(rows) if rows else 0.0

    report = {
        "ts": datetime.now(UTC).isoformat(),
        "dataset": args.dataset,
        "git_sha": args.git_sha,
        "duration_s": duration_s,
        "scenarios": len(rows),
        "total_ticks": total_ticks,
        "success_rate": round(success_rate, 4),
        "cases_ok": ok_cases,
        "policy_accept_rate": round(1 - policy_blocked / len(rows), 4) if rows else 1.0,
        "legal_action_rate": round(legal_ok / len(rows), 4) if rows else 0.0,
        "avg_ticks_per_scenario": round(total_ticks / len(rows), 2) if rows else 0.0,
        "shadow_agree_rate": shadow_agree_rate,
        "dry_run_sessions": args.dry_run_session,
        "failed_scenarios": failures,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="full_operator_smoke", help="Dataset name in orchestrator/evaluation/datasets/")
    parser.add_argument("--min-success", type=float, default=None, help="Gate: exit 1 if success_rate below this")
    parser.add_argument("--dry-run-session", action="store_true", help="Run sessions in dry-run mode (no actions executed)")
    parser.add_argument("--shadow", action="store_true", help="Enable shadow evaluation (heuristic vs model agreement)")
    parser.add_argument("--print-json", action="store_true", help="Print the JSON report to stdout")
    args = parser.parse_args()

    try:
      import subprocess
      args.git_sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
      args.git_sha = "unknown"

    report = asyncio.run(run(args))
    print(json.dumps(report, indent=2))

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a", encoding="utf-8") as fh:
      fh.write(json.dumps(report) + "\n")

    if args.print_json:
      return
    if args.min_success is not None and report["success_rate"] < args.min_success:
      print(f"\nGATE FAILED: success_rate {report['success_rate']} < {args.min_success}")
      raise SystemExit(1)
    if report["success_rate"] == 1.0:
      print("\nAll scenarios passed.")


if __name__ == "__main__":
    main()
