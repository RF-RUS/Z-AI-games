#!/usr/bin/env python3
"""Profile health summary for operators."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "adapter-web" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _profile_health_ops import parse_args  # noqa: E402
from uno_adapter_web.profile_alerts import build_summary  # noqa: E402
from uno_adapter_web.profiles import load_profile  # noqa: E402


def main() -> None:
  args = parse_args("Profile health summary").parse_args()
  summary = build_summary(load_profile(args.profile), limit=args.limit)
  if args.json:
    print(summary.model_dump_json(indent=2))
    return
  print(f"Profile: {summary.profile_id}")
  print(f"Latest: {summary.latest_status} @ {summary.latest_timestamp_ms}")
  print(f"Consecutive degraded: {summary.consecutive_degraded} | broken: {summary.consecutive_broken}")
  print(f"Fallback ratio: {summary.fallback_usage_ratio}")
  if summary.selector_drift_counts:
    print("Drifting selectors:", summary.selector_drift_counts)
  print(f"Runbook: {summary.runbook_path}")
  if summary.latest_report_path:
    print(f"Report: {summary.latest_report_path}")
  if summary.active_alerts:
    print("Alerts:")
    for a in summary.active_alerts:
      print(f"  [{a.severity.value}] {a.alert_type}: {a.message}")


if __name__ == "__main__":
  main()
