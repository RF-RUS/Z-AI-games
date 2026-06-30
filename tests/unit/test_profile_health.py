"""Selector resolver and profile health unit tests."""

import pytest
from uno_adapter_web.profile_health import classify_health, compute_dom_signature, health_config_for
from uno_adapter_web.profiles import load_profile
from uno_adapter_web.selector_resolver import METRICS, resolve_selector_chain
from uno_schemas.adapter_web import (
  ProfileHealthConfig,
  ProfileHealthReport,
  ProfileHealthStatus,
  ProfileSelector,
  SelectorCheckResult,
  SelectorMatchStatus,
)

from tests.helpers.fake_playwright import FakePage


@pytest.mark.asyncio
async def test_resolve_primary_success():
  METRICS.update({k: 0 for k in METRICS})
  sel = ProfileSelector(primary="#hand", fallbacks=[".hand-fallback"])
  page = FakePage({"#hand": 2})
  r = await resolve_selector_chain(page, "hand_area", sel)
  assert r.status == SelectorMatchStatus.PASS_PRIMARY
  assert r.winning_selector == "#hand"
  assert METRICS["selector_primary_success_total"] == 1


@pytest.mark.asyncio
async def test_resolve_fallback_success():
  sel = ProfileSelector(primary="#missing", fallbacks=[".hand-fallback"])
  page = FakePage({".hand-fallback": 1})
  r = await resolve_selector_chain(page, "hand_area", sel)
  assert r.status == SelectorMatchStatus.PASS_FALLBACK
  assert r.winning_level == "fallback_0"


@pytest.mark.asyncio
async def test_resolve_broken():
  sel = ProfileSelector(primary="#a", fallbacks=["#b"])
  page = FakePage({})
  r = await resolve_selector_chain(page, "hand_area", sel, tier="required")
  assert r.status == SelectorMatchStatus.FAIL


def test_classify_healthy():
  cfg = ProfileHealthConfig(required=["a"], optional=["b"])
  results = [
    SelectorCheckResult(selector_name="a", primary="#a", status=SelectorMatchStatus.PASS_PRIMARY, primary_matched=True),
    SelectorCheckResult(selector_name="b", primary="#b", status=SelectorMatchStatus.PASS_PRIMARY, primary_matched=True),
  ]
  assert classify_health(results, cfg) == ProfileHealthStatus.HEALTHY


def test_classify_degraded_fallback():
  cfg = ProfileHealthConfig(required=["a"], optional=[])
  results = [
    SelectorCheckResult(selector_name="a", primary="#a", status=SelectorMatchStatus.PASS_FALLBACK, primary_matched=False),
  ]
  assert classify_health(results, cfg) == ProfileHealthStatus.DEGRADED


def test_classify_broken():
  cfg = ProfileHealthConfig(required=["a"], optional=[])
  results = [
    SelectorCheckResult(selector_name="a", primary="#a", status=SelectorMatchStatus.FAIL),
  ]
  assert classify_health(results, cfg) == ProfileHealthStatus.BROKEN


def test_real_unoh_health_config():
  p = load_profile("real-unoh-web")
  cfg = health_config_for(p)
  assert "game_root" in cfg.required
  assert "draw_button" in cfg.required


@pytest.mark.asyncio
async def test_dom_signature():
  sig = await compute_dom_signature(FakePage({}))
  assert len(sig) == 16
  assert sig != "unknown"


@pytest.mark.contract
def test_profile_health_report_schema():
  report = ProfileHealthReport(
    run_id="r1",
    profile_id="real-unoh-web",
    target_url="https://pizz.uno/singleplayer",
    status=ProfileHealthStatus.HEALTHY,
    timestamp_ms=1,
  )
  data = report.model_dump()
  assert data["status"] == "healthy"
