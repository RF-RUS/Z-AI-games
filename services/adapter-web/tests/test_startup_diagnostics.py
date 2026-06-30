"""Startup diagnostics tracker and failure bundle."""

from pathlib import Path

from uno_adapter_web.startup import StartupRunTracker, StartupStage, write_startup_log
from uno_schemas.adapter_web import WebStartupDiagnostics


def test_startup_tracker_records_stage_timings():
  tracker = StartupRunTracker(profile_id="scuffed-uno-web", session_id="sess-1", url="https://example.com")
  tracker.start(StartupStage.BROWSER_LAUNCH)
  tracker.finish(StartupStage.BROWSER_LAUNCH)
  tracker.start(StartupStage.PAGE_GOTO)
  tracker.stage_timings_ms[StartupStage.PAGE_GOTO.value] = 60000
  diag = tracker.build_diagnostics(
    failed_stage=StartupStage.PAGE_GOTO,
    error_message="Playwright startup failed at stage=page_goto (60000ms): timeout",
  )
  assert diag.failed_stage == "page_goto"
  assert diag.stage_timings_ms["browser_launch"] >= 0
  assert diag.stage_timings_ms["page_goto"] == 60000


def test_write_startup_log_persists_json(tmp_path: Path):
  diag = WebStartupDiagnostics(
    failed_stage="page_goto",
    error_message="timeout",
    stage_timings_ms={"browser_launch": 10},
    profile_id="scuffed-uno-web",
  )
  path = write_startup_log(tmp_path / "startup-failure-page_goto.json", diag)
  assert Path(path).exists()
  assert "page_goto" in Path(path).read_text(encoding="utf-8")
