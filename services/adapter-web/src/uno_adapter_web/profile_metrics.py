"""Profile health metrics registry (Prometheus-style friendly)."""

from __future__ import annotations

from uno_schemas.adapter_web import ProfileHealthReport, ProfileHealthStatus

METRICS: dict[str, int | float | str] = {
  "selector_primary_success_total": 0,
  "selector_fallback_success_total": 0,
  "selector_required_failure_total": 0,
  "profile_health_degraded_total": 0,
  "profile_health_broken_total": 0,
  "profile_health_runs_total": 0,
  "profile_health_last_status": 0,
  "profile_health_last_success_timestamp": 0,
  "fallback_usage_ratio": 0.0,
}

_STATUS_GAUGE = {
  ProfileHealthStatus.HEALTHY: 0,
  ProfileHealthStatus.DEGRADED: 1,
  ProfileHealthStatus.BROKEN: 2,
}


def compute_fallback_ratio(report: ProfileHealthReport, required_keys: list[str]) -> float:
  if not required_keys:
    return 0.0
  required = [r for r in report.selector_results if r.selector_name in required_keys]
  if not required:
    return 0.0
  from uno_schemas.adapter_web import SelectorMatchStatus
  fallbacks = sum(1 for r in required if r.status == SelectorMatchStatus.PASS_FALLBACK)
  return round(fallbacks / len(required), 4)


def record_health_run(report: ProfileHealthReport, *, required_keys: list[str] | None = None) -> None:
  if report.skipped:
    return
  METRICS["profile_health_runs_total"] = int(METRICS["profile_health_runs_total"]) + 1
  METRICS["profile_health_last_status"] = _STATUS_GAUGE.get(report.status, 2)
  METRICS["fallback_usage_ratio"] = compute_fallback_ratio(report, required_keys or [])
  if report.status == ProfileHealthStatus.BROKEN:
    METRICS["profile_health_broken_total"] = int(METRICS["profile_health_broken_total"]) + 1
  if report.status == ProfileHealthStatus.HEALTHY:
    METRICS["profile_health_last_success_timestamp"] = report.timestamp_ms


def metrics_export() -> dict[str, int | float | str]:
  return dict(METRICS)
