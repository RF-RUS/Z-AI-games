#!/usr/bin/env python3
"""Nightly / scheduled profile health smoke for drift detection."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "adapter-web" / "src"))

from uno_adapter_web.profile_alerts import build_summary, evaluate_alerts, persist_alerts
from uno_adapter_web.profile_health import run_playwright_health_check
from uno_adapter_web.profiles import load_profile
from uno_adapter_web.runtime import playwright_available
from uno_schemas.adapter_web import ProfileHealthStatus


async def main() -> None:
  p = argparse.ArgumentParser(description="Profile selector health / drift smoke")
  p.add_argument("--profile", default="real-unoh-web")
  p.add_argument("--allow-network", action="store_true", help="Allow real site fetch")
  p.add_argument("--tolerate-degraded", action=argparse.BooleanOptionalAction, default=True)
  p.add_argument("--capture-fixture", action="store_true")
  p.add_argument("--correlation-id", default=None)
  args = p.parse_args()

  run_corr = args.correlation_id or f"nightly-{args.profile}-{uuid4()}"

  if not playwright_available():
    print(json.dumps({"status": "skipped", "reason": "playwright not installed", "correlation_id": run_corr}))
    sys.exit(0)

  if args.profile == "real-unoh-web" and os.getenv("CI") == "true" and not args.allow_network:
    print(json.dumps({"status": "skipped", "reason": "CI without --allow-network", "correlation_id": run_corr}))
    sys.exit(0)

  report = await run_playwright_health_check(
    args.profile, headless=True, correlation_id=run_corr, trace_id=run_corr, source="nightly",
  )

  if report.skipped:
    print(json.dumps({"status": "skipped", "reason": report.skip_reason, "correlation_id": run_corr}))
    sys.exit(0)

  profile = load_profile(args.profile)
  from uno_adapter_web.health_store import load_reports
  reports = load_reports(args.profile, limit=10)
  alerts = evaluate_alerts(reports, profile)
  alert_paths = persist_alerts(alerts)

  out = {
    "status": report.status.value,
    "profile_id": report.profile_id,
    "run_id": report.run_id,
    "correlation_id": report.correlation_id,
    "trace_id": report.trace_id,
    "fallback_usage": report.fallback_usage_count,
    "required_failures": report.required_failure_count,
    "dom_signature": report.dom_signature,
    "report_path": report.report_path,
    "screenshot_path": report.screenshot_path,
    "remediation": report.remediation.model_dump(mode="json") if report.remediation else None,
    "alerts": [a.model_dump(mode="json") for a in alerts],
    "alert_paths": alert_paths,
    "summary": build_summary(profile, limit=10).model_dump(mode="json"),
  }
  print(json.dumps(out, indent=2))

  if args.capture_fixture:
    print("Use scripts/capture-web-fixture.py for fixture capture", file=sys.stderr)

  if report.status == ProfileHealthStatus.BROKEN:
    sys.exit(1)
  if report.status == ProfileHealthStatus.DEGRADED and not args.tolerate_degraded:
    sys.exit(2)
  sys.exit(0)


if __name__ == "__main__":
  asyncio.run(main())
