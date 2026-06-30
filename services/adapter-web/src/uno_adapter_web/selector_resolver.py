"""Explicit selector chain resolution with observability."""

from __future__ import annotations

import time
from typing import Any, Protocol

from uno_schemas.adapter_web import ProfileSelector, SelectorCheckResult, SelectorMatchStatus
from uno_shared.logging import get_logger

logger = get_logger("adapter-web.selector")

from uno_adapter_web.profile_metrics import METRICS


class PageLike(Protocol):
  async def locator(self, selector: str) -> Any: ...


async def probe_selector(page: PageLike, selector: str) -> tuple[int, int]:
  """Return (match_count, latency_ms)."""
  start = time.perf_counter()
  try:
    loc = page.locator(selector)
    count = await loc.count()
    visible = 0
    for i in range(min(count, 5)):
      if await loc.nth(i).is_visible():
        visible += 1
    ms = int((time.perf_counter() - start) * 1000)
    return (visible if visible else count, ms)
  except Exception:
    return (0, int((time.perf_counter() - start) * 1000))


async def resolve_selector_chain(
  page: PageLike,
  selector_name: str,
  sel: ProfileSelector,
  tier: str = "required",
) -> SelectorCheckResult:
  chain = [("primary", sel.primary), *[(f"fallback_{i}", fb) for i, fb in enumerate(sel.fallbacks)]]
  fallback_results: list[dict[str, bool | int | str]] = []
  total_ms = 0
  primary_count = 0

  primary_count, ms = await probe_selector(page, sel.primary)
  total_ms += ms
  primary_matched = primary_count > 0

  if primary_matched:
    METRICS["selector_primary_success_total"] = int(METRICS["selector_primary_success_total"]) + 1
    logger.debug("selector_primary_ok", selector=selector_name, count=primary_count)
    return SelectorCheckResult(
      selector_name=selector_name,
      tier=tier,
      primary=sel.primary,
      primary_matched=True,
      winning_selector=sel.primary,
      winning_level="primary",
      match_count=primary_count,
      status=SelectorMatchStatus.PASS_PRIMARY,
      latency_ms=total_ms,
    )

  for level, fb_sel in chain[1:]:
    count, ms = await probe_selector(page, fb_sel)
    total_ms += ms
    matched = count > 0
    fallback_results.append({"selector": fb_sel, "level": level, "matched": matched, "count": count})
    if matched:
      METRICS["selector_fallback_success_total"] = int(METRICS["selector_fallback_success_total"]) + 1
      logger.warning("selector_fallback_used", selector=selector_name, level=level, fallback=fb_sel)
      return SelectorCheckResult(
        selector_name=selector_name,
        tier=tier,
        primary=sel.primary,
        primary_matched=False,
        fallback_results=fallback_results,
        winning_selector=fb_sel,
        winning_level=level,
        match_count=count,
        status=SelectorMatchStatus.PASS_FALLBACK,
        latency_ms=total_ms,
        notes=f"primary missed; used {level}",
      )

  if tier == "required":
    METRICS["selector_required_failure_total"] = int(METRICS["selector_required_failure_total"]) + 1
  logger.error("selector_failed", selector=selector_name, primary=sel.primary, tier=tier)
  return SelectorCheckResult(
    selector_name=selector_name,
    tier=tier,
    primary=sel.primary,
    primary_matched=False,
    fallback_results=fallback_results,
    match_count=0,
    status=SelectorMatchStatus.FAIL,
    latency_ms=total_ms,
    notes="all chain selectors missed",
  )


def resolve_from_nodes(nodes: list, sel: ProfileSelector) -> tuple[str | None, str | None]:
  """Sync resolution for extracted DomNodeEvidence list (extraction path)."""
  for level, s in [("primary", sel.primary), *[(f"fallback_{i}", fb) for i, fb in enumerate(sel.fallbacks)]]:
    for n in nodes:
      if s in n.selector or (n.test_id and s.replace("[data-testid='", "").replace("']", "") == n.test_id):
        return s, level
  return None, None
