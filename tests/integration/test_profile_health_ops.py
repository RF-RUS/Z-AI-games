"""Profile health operability integration tests."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uno_adapter_web.api import app
from uno_adapter_web.profile_alerts import evaluate_alerts, persist_alerts
from uno_adapter_web.profile_health import run_profile_health_check
from uno_adapter_web.profiles import load_profile
from uno_schemas.adapter_web import ProfileHealthStatus, SelectorCheckResult, SelectorMatchStatus

from tests.helpers.fake_playwright import FakePage


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_report_includes_correlation(tmp_path):
  profile = load_profile("local-mock-uno")
  page = FakePage({
    "[data-testid='player-hand']": 1,
    "[data-testid='discard-top-card']": 1,
    "[data-testid='btn-draw']": 1,
  })
  report = await run_profile_health_check(
    profile, page, artifacts_dir=tmp_path, correlation_id="corr-test-1", source="test",
  )
  assert report.correlation_id == "corr-test-1"
  assert report.metadata.get("correlation_id") == "corr-test-1"
  data = json.loads(Path(report.report_path).read_text(encoding="utf-8"))
  assert data["correlation_id"] == "corr-test-1"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_broken_report_has_remediation(tmp_path):
  profile = load_profile("local-mock-uno")
  report = await run_profile_health_check(profile, FakePage({}), artifacts_dir=tmp_path, save_report=True)
  assert report.status == ProfileHealthStatus.BROKEN
  assert report.remediation is not None
  assert "runbook" in report.remediation.runbook_path


@pytest.mark.integration
def test_api_summary_and_metrics(tmp_path, monkeypatch):
  client = TestClient(app)
  r = client.get("/profiles/real-unoh-web/health/summary")
  assert r.status_code == 200
  body = r.json()
  assert body["profile_id"] == "real-unoh-web"
  assert "metrics" in body
  m = client.get("/metrics/profile-health")
  assert m.status_code == 200
  assert "profile_health_runs_total" in m.json()


@pytest.mark.integration
def test_alert_pipeline_from_artifacts(tmp_path):
  profile = load_profile("real-unoh-web")
  import time
  from uuid import uuid4

  from uno_schemas.adapter_web import ProfileHealthReport
  broken = ProfileHealthReport(
    run_id=str(uuid4()), profile_id="real-unoh-web", target_url="https://x",
    status=ProfileHealthStatus.BROKEN, timestamp_ms=int(time.time() * 1000),
    required_failure_count=1,
    selector_results=[
      SelectorCheckResult(selector_name="hand_area", tier="required", primary="#h", status=SelectorMatchStatus.FAIL),
    ],
  )
  path = tmp_path / f"{broken.run_id}.json"
  path.write_text(broken.model_dump_json(), encoding="utf-8")
  from uno_adapter_web.health_store import load_reports
  reports = load_reports("real-unoh-web", artifacts_dir=tmp_path)
  alerts = evaluate_alerts(reports, profile)
  paths = persist_alerts(alerts, artifacts_dir=tmp_path / "alerts")
  assert any(a.alert_type == "broken_immediate" for a in alerts)
  assert paths
