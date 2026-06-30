"""Read profile health artifacts and build history views."""

from __future__ import annotations

import json
from pathlib import Path

from uno_schemas.adapter_web import ProfileHealthHistoryEntry, ProfileHealthReport

REPORT_DIR = Path(__file__).resolve().parents[4] / "artifacts" / "profile-health"
ALERT_DIR = REPORT_DIR / "alerts"


def load_reports(
  profile_id: str,
  *,
  limit: int = 50,
  artifacts_dir: Path | None = None,
) -> list[ProfileHealthReport]:
  root = artifacts_dir or REPORT_DIR
  if not root.exists():
    return []
  files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
  out: list[ProfileHealthReport] = []
  for path in files:
    try:
      report = ProfileHealthReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
      continue
    if report.profile_id != profile_id:
      continue
    if not report.report_path:
      report.report_path = str(path)
    out.append(report)
    if len(out) >= limit:
      break
  return sorted(out, key=lambda r: r.timestamp_ms)


def to_history_entry(report: ProfileHealthReport) -> ProfileHealthHistoryEntry:
  return ProfileHealthHistoryEntry(
    run_id=report.run_id,
    correlation_id=report.correlation_id,
    timestamp_ms=report.timestamp_ms,
    status=report.status,
    required_failure_count=report.required_failure_count,
    fallback_usage_count=report.fallback_usage_count,
    report_path=report.report_path,
    screenshot_path=report.screenshot_path,
    dom_signature=report.dom_signature,
    source=report.source,
  )
