"""Profile health alert evaluation tests."""

import time
from uuid import uuid4

from uno_adapter_web.profile_alerts import AlertThresholds, evaluate_alerts, selector_drift_counts
from uno_adapter_web.profile_metrics import compute_fallback_ratio
from uno_adapter_web.profiles import load_profile
from uno_schemas.adapter_web import (
  ProfileHealthAlertSeverity,
  ProfileHealthReport,
  ProfileHealthStatus,
  SelectorCheckResult,
  SelectorMatchStatus,
)


def _report(
  status: ProfileHealthStatus,
  *,
  selector_results: list[SelectorCheckResult] | None = None,
  ts: int | None = None,
) -> ProfileHealthReport:
  return ProfileHealthReport(
    run_id=str(uuid4()),
    profile_id="real-unoh-web",
    target_url="https://pizz.uno/singleplayer",
    status=status,
    timestamp_ms=ts or int(time.time() * 1000),
    selector_results=selector_results or [],
    source="test",
  )


def test_broken_produces_critical_alert():
  profile = load_profile("real-unoh-web")
  r = _report(ProfileHealthStatus.BROKEN, selector_results=[
    SelectorCheckResult(selector_name="hand_area", tier="required", primary="#h", status=SelectorMatchStatus.FAIL),
  ])
  alerts = evaluate_alerts([r], profile)
  assert any(a.alert_type == "broken_immediate" and a.severity == ProfileHealthAlertSeverity.CRITICAL for a in alerts)


def test_sustained_degraded_warning():
  profile = load_profile("real-unoh-web")
  sel = SelectorCheckResult(
    selector_name="hand_area", tier="required", primary="#h",
    status=SelectorMatchStatus.PASS_FALLBACK, primary_matched=False,
  )
  reports = [_report(ProfileHealthStatus.DEGRADED, selector_results=[sel], ts=1000 + i) for i in range(3)]
  alerts = evaluate_alerts(reports, profile, AlertThresholds(degraded_consecutive=3))
  assert any(a.alert_type == "sustained_degraded" for a in alerts)


def test_optional_only_degraded_no_sustained_alert():
  profile = load_profile("real-unoh-web")
  required_ok = SelectorCheckResult(
    selector_name="hand_area", tier="required", primary="#h", status=SelectorMatchStatus.PASS_PRIMARY, primary_matched=True,
  )
  optional_fail = SelectorCheckResult(
    selector_name="chat_messages", tier="optional", primary="#c", status=SelectorMatchStatus.FAIL,
  )
  reports = [_report(ProfileHealthStatus.DEGRADED, selector_results=[required_ok, optional_fail], ts=1000 + i) for i in range(5)]
  alerts = evaluate_alerts(reports, profile, AlertThresholds(degraded_consecutive=3))
  assert not any(a.alert_type == "sustained_degraded" for a in alerts)


def test_fallback_ratio_spike():
  profile = load_profile("real-unoh-web")
  results = [
    SelectorCheckResult(selector_name="hand_area", tier="required", primary="#h", status=SelectorMatchStatus.PASS_FALLBACK),
    SelectorCheckResult(selector_name="draw_button", tier="required", primary="#d", status=SelectorMatchStatus.PASS_PRIMARY, primary_matched=True),
  ]
  reports = [_report(ProfileHealthStatus.DEGRADED, selector_results=results, ts=1000 + i) for i in range(2)]
  alerts = evaluate_alerts(reports, profile, AlertThresholds(fallback_ratio_threshold=0.4, fallback_ratio_min_runs=2))
  assert any(a.alert_type == "fallback_spike" for a in alerts)


def test_recovery_info_alert():
  profile = load_profile("real-unoh-web")
  broken = _report(ProfileHealthStatus.BROKEN, ts=1000)
  healthy = _report(ProfileHealthStatus.HEALTHY, ts=2000)
  alerts = evaluate_alerts([broken, healthy], profile)
  assert any(a.alert_type == "recovery" and a.severity == ProfileHealthAlertSeverity.INFO for a in alerts)


def test_compute_fallback_ratio():
  profile = load_profile("local-mock-uno")
  from uno_adapter_web.profile_health import health_config_for
  cfg = health_config_for(profile)
  r = ProfileHealthReport(
    run_id=str(uuid4()),
    profile_id="local-mock-uno",
    target_url="http://127.0.0.1:8765/",
    status=ProfileHealthStatus.DEGRADED,
    timestamp_ms=int(time.time() * 1000),
    selector_results=[
    SelectorCheckResult(selector_name="hand_area", tier="required", primary="#h", status=SelectorMatchStatus.PASS_FALLBACK),
    SelectorCheckResult(selector_name="draw_button", tier="required", primary="#d", status=SelectorMatchStatus.PASS_PRIMARY, primary_matched=True),
    ],
  )
  assert compute_fallback_ratio(r, cfg.required) == 0.5


def test_selector_drift_counts():
  profile = load_profile("real-unoh-web")
  r = _report(ProfileHealthStatus.DEGRADED, selector_results=[
    SelectorCheckResult(selector_name="hand_area", tier="required", primary="#h", status=SelectorMatchStatus.PASS_FALLBACK),
  ])
  counts = selector_drift_counts([r, r], profile)
  assert counts.get("hand_area") == 2
