"""Alert evaluation for profile health drift."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from uno_adapter_web.health_store import ALERT_DIR, load_reports, to_history_entry
from uno_adapter_web.profile_health import (
  RUNBOOK_PATHS,
  build_remediation,
  degraded_drivers,
  health_config_for,
)
from uno_adapter_web.profile_metrics import compute_fallback_ratio, metrics_export
from uno_schemas.adapter_web import (
  ProfileHealthAlert,
  ProfileHealthAlertSeverity,
  ProfileHealthRemediation,
  ProfileHealthReport,
  ProfileHealthStatus,
  ProfileHealthSummary,
  SelectorMatchStatus,
  WebAdapterProfile,
)

RUNBOOK_DEFAULT = "docs/runbooks/real-unoh-web-profile.md"


@dataclass(frozen=True)
class AlertThresholds:
  degraded_consecutive: int = 3
  fallback_ratio_threshold: float = 0.5
  fallback_ratio_min_runs: int = 2


def _required_fallback_degraded(report: ProfileHealthReport, profile: WebAdapterProfile) -> bool:
  if report.status != ProfileHealthStatus.DEGRADED:
    return False
  cfg = health_config_for(profile)
  drivers = degraded_drivers(report.selector_results, cfg)
  return drivers["required_fallback"] or drivers["required_fail"]


def evaluate_alerts(
  reports: list[ProfileHealthReport],
  profile: WebAdapterProfile,
  thresholds: AlertThresholds | None = None,
) -> list[ProfileHealthAlert]:
  th = thresholds or AlertThresholds()
  if not reports:
    return []
  alerts: list[ProfileHealthAlert] = []
  latest = reports[-1]
  runbook = RUNBOOK_PATHS.get(profile.profile_id, RUNBOOK_DEFAULT)
  remediation = build_remediation(latest, health_config_for(profile), runbook)

  if latest.status == ProfileHealthStatus.BROKEN:
    alerts.append(ProfileHealthAlert(
      alert_id=str(uuid4()),
      profile_id=profile.profile_id,
      severity=ProfileHealthAlertSeverity.CRITICAL,
      alert_type="broken_immediate",
      message=f"Profile {profile.profile_id} is BROKEN — required selectors failed",
      timestamp_ms=latest.timestamp_ms,
      run_id=latest.run_id,
      correlation_id=latest.correlation_id,
      details={"required_failures": latest.required_failure_count},
      remediation=remediation,
    ))

  consec_degraded = 0
  for r in reversed(reports):
    if r.status == ProfileHealthStatus.DEGRADED and _required_fallback_degraded(r, profile):
      consec_degraded += 1
    else:
      break
  if consec_degraded >= th.degraded_consecutive and latest.status != ProfileHealthStatus.BROKEN:
    alerts.append(ProfileHealthAlert(
      alert_id=str(uuid4()),
      profile_id=profile.profile_id,
      severity=ProfileHealthAlertSeverity.WARNING,
      alert_type="sustained_degraded",
      message=f"Profile degraded {consec_degraded} consecutive runs (required selectors)",
      timestamp_ms=latest.timestamp_ms,
      run_id=latest.run_id,
      correlation_id=latest.correlation_id,
      details={"consecutive_degraded": consec_degraded},
      remediation=remediation,
    ))

  recent = reports[-th.fallback_ratio_min_runs:]
  if len(recent) >= th.fallback_ratio_min_runs:
    cfg = health_config_for(profile)
    ratios = [compute_fallback_ratio(r, cfg.required) for r in recent]
    avg_ratio = sum(ratios) / len(ratios)
    if avg_ratio >= th.fallback_ratio_threshold:
      alerts.append(ProfileHealthAlert(
        alert_id=str(uuid4()),
        profile_id=profile.profile_id,
        severity=ProfileHealthAlertSeverity.WARNING,
        alert_type="fallback_spike",
        message=f"Required fallback ratio {avg_ratio:.0%} over last {len(recent)} runs",
        timestamp_ms=latest.timestamp_ms,
        run_id=latest.run_id,
        correlation_id=latest.correlation_id,
        details={"fallback_ratio_avg": round(avg_ratio, 4), "runs": len(recent)},
        remediation=remediation,
      ))

  if len(reports) >= 2:
    prev, cur = reports[-2], reports[-1]
    if cur.status == ProfileHealthStatus.HEALTHY and prev.status in (
      ProfileHealthStatus.BROKEN,
      ProfileHealthStatus.DEGRADED,
    ):
      alerts.append(ProfileHealthAlert(
        alert_id=str(uuid4()),
        profile_id=profile.profile_id,
        severity=ProfileHealthAlertSeverity.INFO,
        alert_type="recovery",
        message=f"Profile recovered to HEALTHY from {prev.status.value}",
        timestamp_ms=cur.timestamp_ms,
        run_id=cur.run_id,
        correlation_id=cur.correlation_id,
        details={"previous_status": prev.status.value},
        remediation=ProfileHealthRemediation(
          runbook_path=runbook,
          summary="Recovery detected — confirm selectors and refresh fixtures if DOM changed",
          next_actions=["Re-run nightly smoke", "Compare dom_signature with pre-incident runs", "Update fixtures if needed"],
        ),
      ))

  return alerts


def selector_drift_counts(reports: list[ProfileHealthReport], profile: WebAdapterProfile) -> dict[str, int]:
  cfg = health_config_for(profile)
  counts: dict[str, int] = {}
  for report in reports:
    for r in report.selector_results:
      if r.selector_name not in cfg.required:
        continue
      if r.status in (SelectorMatchStatus.PASS_FALLBACK, SelectorMatchStatus.FAIL):
        counts[r.selector_name] = counts.get(r.selector_name, 0) + 1
  return counts


def build_summary(
  profile: WebAdapterProfile,
  *,
  limit: int = 20,
  artifacts_dir: Path | None = None,
  thresholds: AlertThresholds | None = None,
) -> ProfileHealthSummary:
  reports = load_reports(profile.profile_id, limit=limit, artifacts_dir=artifacts_dir)
  runbook = RUNBOOK_PATHS.get(profile.profile_id, RUNBOOK_DEFAULT)
  summary = ProfileHealthSummary(profile_id=profile.profile_id, runbook_path=runbook)
  if not reports:
    summary.metrics = metrics_export()
    return summary

  latest = reports[-1]
  summary.latest_status = latest.status
  summary.latest_run_id = latest.run_id
  summary.latest_correlation_id = latest.correlation_id
  summary.latest_timestamp_ms = latest.timestamp_ms
  summary.latest_report_path = latest.report_path
  summary.latest_screenshot_path = latest.screenshot_path
  summary.recent_runs = [to_history_entry(r) for r in reports[-limit:]]
  summary.selector_drift_counts = selector_drift_counts(reports, profile)
  summary.fallback_usage_ratio = compute_fallback_ratio(latest, health_config_for(profile).required)

  consec_d = 0
  for r in reversed(reports):
    if r.status == ProfileHealthStatus.DEGRADED and _required_fallback_degraded(r, profile):
      consec_d += 1
    else:
      break
  consec_b = 0
  for r in reversed(reports):
    if r.status == ProfileHealthStatus.BROKEN:
      consec_b += 1
    else:
      break
  summary.consecutive_degraded = consec_d
  summary.consecutive_broken = consec_b
  summary.active_alerts = evaluate_alerts(reports, profile, thresholds)
  summary.metrics = metrics_export()
  return summary


def persist_alerts(alerts: list[ProfileHealthAlert], artifacts_dir: Path | None = None) -> list[str]:
  if not alerts:
    return []
  out_dir = (artifacts_dir or ALERT_DIR)
  out_dir.mkdir(parents=True, exist_ok=True)
  paths: list[str] = []
  for alert in alerts:
    path = out_dir / f"{alert.alert_id}.json"
    path.write_text(alert.model_dump_json(indent=2), encoding="utf-8")
    paths.append(str(path))
  return paths
