"""Profile health integration tests."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uno_adapter_web.api import app
from uno_adapter_web.profile_health import run_profile_health_check
from uno_adapter_web.profiles import load_profile
from uno_schemas.adapter_web import ProfileHealthStatus

from tests.helpers.fake_playwright import FakePage

FIXTURES = Path(__file__).parent.parent / "fixtures" / "web_adapter" / "real-unoh"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_fake_page_healthy(tmp_path):
  profile = load_profile("local-mock-uno")
  page = FakePage({
    "[data-testid='player-hand']": 1,
    "[data-testid='discard-top-card']": 1,
    "[data-testid='btn-draw']": 1,
    "[data-testid='chat-messages']": 1,
    "[data-testid='btn-play-red5']": 1,
  })
  report = await run_profile_health_check(profile, page, artifacts_dir=tmp_path, save_report=True)
  assert report.status == ProfileHealthStatus.HEALTHY
  assert report.report_path
  assert Path(report.report_path).exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_broken_missing_required():
  profile = load_profile("local-mock-uno")
  page = FakePage({})
  report = await run_profile_health_check(profile, page, save_report=False)
  assert report.status == ProfileHealthStatus.BROKEN
  assert report.required_failure_count >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_fallback_degraded():
  profile = load_profile("local-mock-uno")
  hand_sel = profile.selectors["hand_area"]
  page = FakePage({
    hand_sel.fallbacks[0]: 1,
    "[data-testid='discard-top-card']": 1,
    "[data-testid='btn-draw']": 1,
  })
  report = await run_profile_health_check(profile, page, save_report=False)
  assert report.status == ProfileHealthStatus.DEGRADED
  assert report.fallback_usage_count >= 1


@pytest.mark.contract
def test_profile_json_includes_health():
  client = TestClient(app)
  resp = client.get("/profiles/real-unoh-web")
  assert resp.status_code == 200
  body = resp.json()
  assert body["health"]["required"]


def test_health_expected_fixture_exists():
  path = FIXTURES / "health_expected.json"
  assert path.exists()
  data = json.loads(path.read_text(encoding="utf-8"))
  assert "required_selectors" in data
