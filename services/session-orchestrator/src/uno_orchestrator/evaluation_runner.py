"""Full-operator evaluation runner."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from uuid import uuid4

from uno_orchestrator.in_process_clients import InProcessClients
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.operator_evaluation import (
  OperatorEvaluationRun,
  OperatorScenario,
  OperatorScenarioResult,
)
from uno_schemas.orchestrator import AttachAdapterBody, SessionSpec
from uno_schemas.session import SessionConfig

DATASETS_DIR = Path(__file__).resolve().parents[4] / "orchestrator" / "evaluation" / "datasets"
RESULTS_DIR = Path(__file__).resolve().parents[4] / "models" / "benchmarks" / "results"


def load_operator_dataset(name: str) -> list[OperatorScenario]:
  path = DATASETS_DIR / f"{name}.jsonl"
  if not path.exists():
    raise FileNotFoundError(f"dataset not found: {name}")
  rows = []
  for line in path.read_text(encoding="utf-8").strip().splitlines():
    if line.strip():
      rows.append(OperatorScenario.model_validate_json(line))
  return rows


def _score_scenario(scenario: OperatorScenario, tick_results: list[dict], steps: int, error: str | None) -> OperatorScenarioResult:
  expected = scenario.expected
  weights = scenario.scoring_weights
  last = tick_results[-1] if tick_results else {}
  legal_ok = bool(last.get("action") or last.get("correlation_id"))
  policy_ok = not last.get("guard_blocked") if expected.get("policy_allowed") else True
  if expected.get("allow_guard_block"):
    policy_ok = True
  flow_ok = steps >= int(expected.get("min_steps", 5)) if "min_steps" in expected else steps > 0
  no_error = error is None and not last.get("error")
  if expected.get("no_fatal_error"):
    no_error = error is None or "replay" in str(error).lower()

  parts = {
    "legal_action": 1.0 if legal_ok else 0.0,
    "policy_pass": 1.0 if policy_ok else 0.0,
    "flow_complete": 1.0 if flow_ok else 0.0,
    "no_error": 1.0 if no_error else 0.0,
  }
  wsum = sum(weights.values()) or 1.0
  score = sum(parts.get(k, 0) * weights.get(k, 0) for k in parts) / wsum
  success = score >= 0.6
  if expected.get("has_action"):
    success = legal_ok and no_error
  if expected.get("min_ticks"):
    success = len(tick_results) >= expected["min_ticks"] and no_error

  return OperatorScenarioResult(
    scenario_id=scenario.scenario_id,
    success=success,
    score=score,
    ticks_run=len(tick_results),
    legal_action_ok=legal_ok,
    policy_pass_ok=policy_ok,
    flow_complete_ok=flow_ok,
    error=error,
    failure_reason=None if success else json.dumps({k: parts[k] for k in parts if parts[k] < 1}),
    flow_steps=steps,
    metadata={"description": scenario.description},
  )


async def run_operator_evaluation(
  dataset_name: str,
  orchestrator: SessionOrchestrator | None = None,
  clients=None,
) -> OperatorEvaluationRun:
  orch = orchestrator if orchestrator is not None else SessionOrchestrator(clients=clients or InProcessClients())
  scenarios = load_operator_dataset(dataset_name)
  run_id = str(uuid4())
  results: list[OperatorScenarioResult] = []

  for scenario in scenarios:
    tick_results: list[dict] = []
    err: str | None = None
    steps = 0
    try:
      spec = SessionSpec(
        config=SessionConfig(
          adapter_type=scenario.adapter_type,
          adapter_id="pending",
          min_confidence=scenario.min_confidence,
          model_assist_enabled=scenario.model_assist,
        ),
      )
      detail = await orch.create_session_with_game(spec)
      await orch.attach_adapter(detail.session_id, AttachAdapterBody(adapter_type=scenario.adapter_type))
      await orch.start(detail.session_id)
      for _ in range(scenario.max_ticks):
        tick_results.append(await orch.run_tick(detail.session_id))
      steps = len(orch.get_steps(detail.session_id))
      await orch.stop(detail.session_id)
    except Exception as exc:
      err = str(exc)
    results.append(_score_scenario(scenario, tick_results, steps, err))

  scores = [r.score for r in results]
  policy_pass = [r.policy_pass_ok for r in results]
  ticks = [r.ticks_run for r in results]

  run = OperatorEvaluationRun(
    run_id=run_id,
    dataset=dataset_name,
    scenarios=len(scenarios),
    success_rate=sum(1 for r in results if r.success) / len(results) if results else 0,
    avg_score=statistics.mean(scores) if scores else 0,
    avg_ticks=statistics.mean(ticks) if ticks else 0,
    policy_accept_rate=sum(1 for p in policy_pass if p) / len(policy_pass) if policy_pass else 0,
    case_results=results,
    metadata={"timestamp": str(int(time.time())), "mode": "full_operator"},
  )

  RESULTS_DIR.mkdir(parents=True, exist_ok=True)
  out = RESULTS_DIR / f"{run_id}_full_operator.json"
  out.write_text(run.model_dump_json(indent=2), encoding="utf-8")
  return run
