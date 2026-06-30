"""Profile selector health checks and drift report persistence."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from uno_adapter_web.profile_metrics import METRICS, compute_fallback_ratio, record_health_run
from uno_adapter_web.profiles import load_profile
from uno_adapter_web.selector_resolver import resolve_selector_chain
from uno_schemas.adapter_web import (
  ProfileHealthConfig,
  ProfileHealthRemediation,
  ProfileHealthReport,
  ProfileHealthStatus,
  SelectorCheckResult,
  SelectorMatchStatus,
  WebAdapterProfile,
)
from uno_shared.logging import bind_correlation_id, get_logger

logger = get_logger("adapter-web.profile-health")

REPORT_DIR = Path(__file__).resolve().parents[4] / "artifacts" / "profile-health"
RUNBOOK_PATHS = {
  "real-unoh-web": "docs/runbooks/real-unoh-web-profile.md",
  "local-mock-uno": "docs/runbooks/real-unoh-web-profile.md",
}
DEFAULT_HEALTH: dict[str, ProfileHealthConfig] = {
  "real-unoh-web": ProfileHealthConfig(
    required=["game_root", "hand_area", "discard_top_card", "draw_button"],
    optional=["play_button", "current_player", "uno_indicator", "chat_messages", "bootstrap_start_game"],
  ),
  "local-mock-uno": ProfileHealthConfig(
    required=["hand_area", "discard_top_card", "draw_button"],
    optional=["chat_messages", "play_button"],
  ),
}


def health_config_for(profile: WebAdapterProfile) -> ProfileHealthConfig:
  if profile.health:
    return profile.health
  return DEFAULT_HEALTH.get(profile.profile_id, ProfileHealthConfig(
    required=list(profile.selectors.keys())[:4],
    optional=list(profile.selectors.keys())[4:],
  ))


def degraded_drivers(results: list[SelectorCheckResult], config: ProfileHealthConfig) -> dict[str, bool]:
  required = {r.selector_name: r for r in results if r.selector_name in config.required}
  optional = [r for r in results if r.selector_name in config.optional]
  return {
    "required_fallback": any(r.status == SelectorMatchStatus.PASS_FALLBACK for r in required.values()),
    "required_fail": any(r.status == SelectorMatchStatus.FAIL for r in required.values()),
    "optional_fail": any(r.status == SelectorMatchStatus.FAIL for r in optional),
  }


def classify_health(results: list[SelectorCheckResult], config: ProfileHealthConfig) -> ProfileHealthStatus:
  required = {r.selector_name: r for r in results if r.selector_name in config.required}
  for name in config.required:
    r = required.get(name)
    if not r or r.status == SelectorMatchStatus.FAIL:
      return ProfileHealthStatus.BROKEN
  if any(r.status == SelectorMatchStatus.PASS_FALLBACK for r in required.values()):
    METRICS["profile_health_degraded_total"] = int(METRICS["profile_health_degraded_total"]) + 1
    return ProfileHealthStatus.DEGRADED
  optional = [r for r in results if r.selector_name in config.optional]
  if any(r.status == SelectorMatchStatus.FAIL for r in optional):
    return ProfileHealthStatus.DEGRADED
  return ProfileHealthStatus.HEALTHY


def build_remediation(
  report: ProfileHealthReport,
  config: ProfileHealthConfig,
  runbook_path: str,
) -> ProfileHealthRemediation | None:
  if report.status == ProfileHealthStatus.HEALTHY:
    return None
  failed = [r.selector_name for r in report.selector_results if r.tier == "required" and r.status == SelectorMatchStatus.FAIL]
  fallbacks = [r.selector_name for r in report.selector_results if r.tier == "required" and r.status == SelectorMatchStatus.PASS_FALLBACK]
  suspected = failed + fallbacks
  if report.status == ProfileHealthStatus.BROKEN:
    return ProfileHealthRemediation(
      runbook_path=runbook_path,
      summary="Required selectors failed — profile unusable until fixed",
      suspected_selectors=suspected,
      next_actions=[
        "Open latest artifact JSON and screenshot",
        "Run scripts/inspect-pizzuno-game.py if site changed",
        "Update primary selectors in profile JSON",
        f"See runbook: {runbook_path}",
      ],
    )
  return ProfileHealthRemediation(
    runbook_path=runbook_path,
    summary="Profile degraded — fallback or optional selector drift",
    suspected_selectors=suspected,
    next_actions=[
      "Inspect fallback_usage in report — fix primary selectors if sustained",
      "Compare dom_signature with prior healthy runs",
      f"See runbook: {runbook_path}",
    ],
  )


async def compute_dom_signature(page) -> str:
  try:
    raw = await page.evaluate("""() => {
      const keys = ['app', 'player-hand', 'deck', 'playedCards'];
      return keys.map(k => {
        const el = document.getElementById(k) || document.querySelector('#' + k);
        return k + ':' + (el ? el.childElementCount + ':' + el.className.toString().slice(0,40) : 'missing');
      }).join('|');
    }""")
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
  except Exception:
    return "unknown"


async def check_action_mapping(page, name: str, selector: str, tier: str) -> SelectorCheckResult:
  from uno_adapter_web.selector_resolver import probe_selector
  count, ms = await probe_selector(page, selector)
  status = SelectorMatchStatus.PASS_PRIMARY if count > 0 else SelectorMatchStatus.FAIL
  return SelectorCheckResult(
    selector_name=name,
    tier=tier,
    primary=selector,
    primary_matched=count > 0,
    winning_selector=selector if count > 0 else None,
    winning_level="primary" if count > 0 else None,
    match_count=count,
    status=status,
    latency_ms=ms,
  )


async def run_profile_health_check(
  profile: WebAdapterProfile,
  page,
  *,
  artifacts_dir: Path | None = None,
  save_report: bool = True,
  correlation_id: str | None = None,
  trace_id: str | None = None,
  source: str = "manual",
) -> ProfileHealthReport:
  run_id = str(uuid4())
  cid = correlation_id or run_id
  bind_correlation_id(cid)
  config = health_config_for(profile)
  results: list[SelectorCheckResult] = []

  for name in config.required + config.optional:
    tier = "required" if name in config.required else "optional"
    if name.startswith("bootstrap_"):
      sel_str = profile.action_mappings.get(name)
      if sel_str:
        results.append(await check_action_mapping(page, name, sel_str, tier))
      continue
    sel = profile.selectors.get(name)
    if not sel:
      results.append(SelectorCheckResult(
        selector_name=name, tier=tier, primary="",
        status=SelectorMatchStatus.FAIL, notes="selector key not in profile",
      ))
      continue
    results.append(await resolve_selector_chain(page, name, sel, tier))

  status = classify_health(results, config)
  fallback_count = sum(1 for r in results if r.status == SelectorMatchStatus.PASS_FALLBACK)
  req_fail = sum(1 for r in results if r.tier == "required" and r.status == SelectorMatchStatus.FAIL)
  runbook = RUNBOOK_PATHS.get(profile.profile_id, "docs/runbooks/real-unoh-web-profile.md")

  title = ""
  try:
    title = await page.title()
  except Exception:
    pass

  dom_sig = await compute_dom_signature(page)
  screenshot_path: str | None = None
  out_dir = artifacts_dir or REPORT_DIR
  out_dir.mkdir(parents=True, exist_ok=True)
  try:
    screenshot_path = str(out_dir / f"{run_id}.png")
    await page.screenshot(path=screenshot_path, full_page=False)
  except Exception:
    screenshot_path = None

  report = ProfileHealthReport(
    run_id=run_id,
    profile_id=profile.profile_id,
    target_url=profile.launch_url,
    page_title=title,
    status=status,
    timestamp_ms=int(time.time() * 1000),
    correlation_id=cid,
    trace_id=trace_id or cid,
    source=source,
    selector_results=results,
    fallback_usage_count=fallback_count,
    required_failure_count=req_fail,
    dom_signature=dom_sig,
    screenshot_path=screenshot_path,
  )
  report.remediation = build_remediation(report, config, runbook)
  report.metadata = {
    "metrics": json.dumps({k: v for k, v in METRICS.items() if isinstance(v, (int, float, str))}),
    "fallback_usage_ratio": str(compute_fallback_ratio(report, config.required)),
    "correlation_id": cid,
    "trace_id": trace_id or cid,
    "source": source,
  }

  record_health_run(report, required_keys=config.required)

  if save_report:
    path = out_dir / f"{run_id}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    report.report_path = str(path)
    recent = [report]
    try:
      from uno_adapter_web.health_store import load_reports
      recent = load_reports(profile.profile_id, limit=10, artifacts_dir=out_dir)
      if not any(r.run_id == report.run_id for r in recent):
        recent.append(report)
      recent.sort(key=lambda r: r.timestamp_ms)
    except Exception:
      pass
    from uno_adapter_web.profile_alerts import evaluate_alerts, persist_alerts

    alerts = evaluate_alerts(recent, profile)
    alert_paths = persist_alerts([a for a in alerts if a.alert_type != "recovery" or status == ProfileHealthStatus.HEALTHY])
    if alerts:
      report.metadata["alerts"] = json.dumps([a.alert_type for a in alerts])
      report.metadata["alert_paths"] = json.dumps(alert_paths)
    logger.info(
      "profile_health_check",
      profile_id=profile.profile_id,
      status=status.value,
      fallback_count=fallback_count,
      required_failures=req_fail,
      run_id=run_id,
      correlation_id=cid,
      trace_id=trace_id or cid,
      source=source,
      report_path=str(path),
      screenshot_path=screenshot_path,
      runbook_path=runbook,
    )
    if report.remediation and status != ProfileHealthStatus.HEALTHY:
      logger.warning(
        "profile_health_remediation",
        profile_id=profile.profile_id,
        summary=report.remediation.summary,
        suspected_selectors=report.remediation.suspected_selectors,
        runbook_path=report.remediation.runbook_path,
      )

  return report


async def run_playwright_health_check(
  profile_id: str,
  headless: bool = True,
  *,
  correlation_id: str | None = None,
  trace_id: str | None = None,
  source: str = "api",
) -> ProfileHealthReport:
  from uno_adapter_web.runtime import PlaywrightSession, playwright_available

  if not playwright_available():
    return ProfileHealthReport(
      run_id=str(uuid4()),
      profile_id=profile_id,
      target_url="",
      status=ProfileHealthStatus.BROKEN,
      timestamp_ms=int(time.time() * 1000),
      skipped=True,
      skip_reason="playwright not installed",
      source=source,
      correlation_id=correlation_id,
    )

  profile = load_profile(profile_id)
  session = PlaywrightSession(f"health-{profile_id}", profile, headless=headless, artifacts_dir=REPORT_DIR)
  try:
    await session.attach()
    assert session._page
    return await run_profile_health_check(
      profile,
      session._page,
      artifacts_dir=REPORT_DIR,
      correlation_id=correlation_id,
      trace_id=trace_id,
      source=source,
    )
  finally:
    await session.detach()
