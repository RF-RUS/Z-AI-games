"""Benchmark dataset loader and runner."""

from __future__ import annotations

import statistics
import time
from pathlib import Path
from uuid import uuid4

from uno_model_runtime.prompts_registry import resolve_prompt
from uno_model_runtime.providers import get_provider
from uno_schemas.model import (
  BenchmarkCase,
  BenchmarkCaseResult,
  BenchmarkResult,
  ModelInvocationContext,
  ModelInvocationRequest,
  ModelProfile,
  ModelUseCase,
)

DATASETS_DIR = Path(__file__).resolve().parents[4] / "models" / "benchmarks" / "datasets"
RESULTS_DIR = Path(__file__).resolve().parents[4] / "models" / "benchmarks" / "results"


def load_dataset(name: str) -> list[BenchmarkCase]:
  path = DATASETS_DIR / f"{name}.jsonl"
  if not path.exists():
    raise FileNotFoundError(f"dataset not found: {name}")
  cases = []
  for line in path.read_text(encoding="utf-8").strip().splitlines():
    if line.strip():
      cases.append(BenchmarkCase.model_validate_json(line))
  return cases


def _score_case(case: BenchmarkCase, parsed: dict | None) -> tuple[float, bool]:
  if not parsed:
    return 0.0, False
  expected = case.expected
  if case.use_case == ModelUseCase.CHAT_INTENT:
    exact = (
      parsed.get("directed_at_bot") == expected.get("directed_at_bot")
      and parsed.get("reply_required") == expected.get("reply_required")
    )
    return (1.0 if exact else 0.0), exact
  if case.use_case == ModelUseCase.EXPLANATION:
    contains = expected.get("summary_contains", "")
    summary = str(parsed.get("summary", "")).lower()
    ok = contains.lower() in summary if contains else bool(summary)
    return (1.0 if ok else 0.0), ok
  if case.use_case == ModelUseCase.PERCEPTION_DISPUTE:
    exact = parsed.get("resolution_class") == expected.get("resolution_class")
    return (1.0 if exact else 0.0), exact
  if case.use_case == ModelUseCase.CHAT_REPLY:
    exact = parsed.get("best_index") == expected.get("best_index")
    return (1.0 if exact else 0.0), exact
  return 0.5, False


async def run_benchmark(
  dataset_name: str,
  profile: ModelProfile,
  prompt_id: str | None = None,
) -> BenchmarkResult:
  cases = load_dataset(dataset_name)
  if not cases:
    raise ValueError("empty dataset")

  run_id = str(uuid4())
  use_case = cases[0].use_case
  provider = get_provider(profile.provider)
  case_results: list[BenchmarkCaseResult] = []
  latencies: list[int] = []
  prompt_version: str | None = None
  resolved_prompt_id: str | None = prompt_id

  for case in cases:
    try:
      resolution = resolve_prompt(use_case, {k: str(v) for k, v in case.input.items()}, prompt_id)
      prompt_version = resolution.version
      resolved_prompt_id = resolution.prompt_id
      req = ModelInvocationRequest(
        context=ModelInvocationContext(use_case=use_case, correlation_id=run_id, benchmark_run_id=run_id),
        profile_id=profile.profile_id,
        prompt_id=resolution.prompt_id,
        prompt_version=resolution.version,
        variables={k: str(v) for k, v in case.input.items()},
        expect_json=True,
      )
      resp = await provider.invoke(profile, resolution.rendered_prompt, req)
      parsed = resp.structured.parsed if resp.structured else None
      score, exact = _score_case(case, parsed)
      case_results.append(BenchmarkCaseResult(
        case_id=case.case_id,
        success=score > 0,
        score=score,
        latency_ms=resp.latency_ms,
        parse_success=bool(resp.structured and resp.structured.parse_success),
        exact_match=exact,
      ))
      latencies.append(resp.latency_ms)
    except Exception as exc:
      case_results.append(BenchmarkCaseResult(case_id=case.case_id, success=False, score=0.0, latency_ms=0, error=str(exc)))

  scores = [c.score for c in case_results]
  lat_sorted = sorted(latencies) or [0]
  p50 = lat_sorted[len(lat_sorted) // 2]
  p95 = lat_sorted[int(len(lat_sorted) * 0.95)] if len(lat_sorted) > 1 else lat_sorted[0]

  result = BenchmarkResult(
    run_id=run_id,
    model_id=profile.profile_id,
    dataset=dataset_name,
    prompt_id=resolved_prompt_id,
    prompt_version=prompt_version,
    provider=profile.provider,
    score=statistics.mean(scores) if scores else 0.0,
    latency_p50_ms=p50,
    latency_p95_ms=p95,
    samples=len(cases),
    success_rate=sum(1 for c in case_results if c.success) / len(case_results),
    parse_success_rate=sum(1 for c in case_results if c.parse_success) / len(case_results),
    case_results=case_results,
    metadata={"timestamp": str(int(time.time()))},
  )

  RESULTS_DIR.mkdir(parents=True, exist_ok=True)
  (RESULTS_DIR / f"{run_id}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
  return result
