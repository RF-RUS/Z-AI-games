"""Playwright session lifecycle management."""

from __future__ import annotations

import base64
import logging
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from uno_adapter_web.canvas_coords import (
  action_requires_canvas_click,
  build_coordinate_click_payload,
  diagnose_page,
)
from uno_adapter_web.extraction import build_extracted_snapshot, dom_snapshot_to_evidence
from uno_adapter_web.navigation_diagnostics import NavigationDiagnosticsCollector
from uno_adapter_web.selector_resolver import resolve_selector_chain
from uno_adapter_web.startup import (
  PlaywrightStartupError,
  StartupRunTracker,
  StartupStage,
  browser_launch_mode,
  browser_launch_options,
  goto_timeout_ms,
  goto_wait_until,
  write_startup_log,
)
from uno_schemas.adapter_web import (
  ActionExecutionRequest,
  ActionExecutionResult,
  DomNodeEvidence,
  WebActionType,
  WebAdapterProfile,
  WebPageDiagnostics,
  WebStartupDiagnostics,
)

ARTIFACTS_DIR = Path(__file__).resolve().parents[3] / "artifacts"
logger = logging.getLogger(__name__)


def playwright_available() -> bool:
  try:
    import playwright  # noqa: F401
    return True
  except ImportError:
    return False


class PlaywrightSession:
  """Manages browser context, extraction, and primitive actions."""

  def __init__(
    self,
    session_id: str,
    profile: WebAdapterProfile,
    url: str | None = None,
    headless: bool = True,
    record_trace: bool = False,
    artifacts_dir: Path | None = None,
    cdp_url: str | None = None,
  ) -> None:
    self.session_id = session_id
    self.profile = profile
    self.url = url or profile.launch_url
    self.headless = headless
    self.record_trace = record_trace
    self.cdp_url = cdp_url
    self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR / session_id
    self.artifacts_dir.mkdir(parents=True, exist_ok=True)
    self.attached = False
    self._pw = None
    self._browser = None
    self._context = None
    self._page = None
    self._trace_path: str | None = None
    self._canvas_bounds: dict[str, float] | None = None
    self._page_diagnostics: WebPageDiagnostics | None = None
    self._last_grounding: Any = None
    self._dpr: float = 1.0
    self._trace_step: int = 0
    self._startup_tracker: StartupRunTracker | None = None
    self._startup_diagnostics: WebStartupDiagnostics | None = None
    self._nav_collector: NavigationDiagnosticsCollector | None = None
    self._browser_launch_mode = "bundled_chromium"
    self._cdp_expected_url: str | None = None

  @property
  def startup_diagnostics(self) -> WebStartupDiagnostics | None:
    return self._startup_diagnostics

  async def _detect_canvas_bounds(self) -> dict[str, float] | None:
    if not self._page or not self.profile.canvas_selector:
      return None
    try:
      loc = self._page.locator(self.profile.canvas_selector)
      if await loc.count() == 0:
        return None
      box = await loc.first.bounding_box()
      if not box or box.get("width", 0) < 10:
        return None
      return box
    except Exception:
      return None

  async def _count_lobby_controls(self) -> int:
    if not self._page:
      return 0
    total = 0
    for sel in self.profile.lobby_selectors.values():
      for locator_str in [sel.primary, *sel.fallbacks]:
        try:
          total += await self._page.locator(locator_str).count()
        except Exception:
          continue
    return total

  async def refresh_page_diagnostics(self) -> WebPageDiagnostics:
    self._canvas_bounds = await self._detect_canvas_bounds()
    if self._page:
      try:
        self._dpr = float(await self._page.evaluate("() => window.devicePixelRatio || 1"))
      except Exception:
        self._dpr = 1.0
    lobby_count = await self._count_lobby_controls()
    self._page_diagnostics = diagnose_page(self._canvas_bounds, lobby_count)
    return self._page_diagnostics

  async def attach(self) -> bool:
    from playwright.async_api import async_playwright

    profile_id = self.profile.profile_id
    session_id = self.session_id
    tracker = StartupRunTracker(profile_id=profile_id, session_id=session_id, url=self.url)
    self._startup_tracker = tracker

    async def _run_stage(stage: StartupStage, fn):
      tracker.start(stage)
      try:
        result = await fn()
        tracker.finish(stage)
        return result
      except PlaywrightStartupError as exc:
        tracker.stage_timings_ms.setdefault(stage.value, exc.elapsed_ms)
        raise
      except Exception as exc:
        elapsed_ms = int((time.perf_counter() - tracker._starts.get(stage, time.perf_counter())) * 1000)
        tracker.stage_timings_ms[stage.value] = elapsed_ms
        raise PlaywrightStartupError(stage, str(exc), elapsed_ms=elapsed_ms, cause=exc) from exc

    try:
      if self.cdp_url:
        async def _connect_cdp():
          self._pw = await async_playwright().start()
          self._browser_launch_mode = "cdp_connect"
          self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)
          contexts = self._browser.contexts
          if not contexts:
            raise RuntimeError(f"No browser contexts found at {self.cdp_url}")
          pages = contexts[0].pages
          if not pages:
            raise RuntimeError(f"No open pages found at {self.cdp_url}")
          target_page = None
          candidates = []
          for p in pages:
            page_url = p.url or ""
            if self.url and self.url in page_url:
              candidates.append(p)
          if len(candidates) == 1:
            target_page = candidates[0]
          elif len(candidates) > 1:
            target_page = candidates[0]
            logger.warning(
              "cdp_multiple_url_matches url=%s count=%d using_first=True",
              self.url, len(candidates),
            )
          else:
            available = [f"  {p.url}" for p in pages if p.url]
            raise RuntimeError(
              f"Target page not found. Expected URL containing '{self.url}'. "
              f"Available pages:\n" + "\n".join(available[:5])
            )
          self._page = target_page
          self._context = target_page.context
          self._cdp_expected_url = self.url
          if self.profile.allowed_domains:
            page_url = target_page.url or ""
            if not self.is_url_compatible_with_profile(page_url):
              raise RuntimeError(
                f"Tab domain mismatch: '{page_url}' is not compatible with profile "
                f"'{self.profile.profile_id}' (allowed: {self.profile.allowed_domains}). "
                f"Select a tab matching the profile, or change the profile to match the tab."
              )

        await _run_stage(StartupStage.BROWSER_LAUNCH, _connect_cdp)
      else:
        async def _launch_browser():
          self._pw = await async_playwright().start()
          self._browser_launch_mode = browser_launch_mode(self.profile)
          launch_opts = browser_launch_options(self.profile, headless=self.headless)
          self._browser = await self._pw.chromium.launch(**launch_opts)

        await _run_stage(StartupStage.BROWSER_LAUNCH, _launch_browser)

        async def _open_context_page():
          self._context = await self._browser.new_context(viewport={"width": 1280, "height": 800})
          if self.record_trace:
            await self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
          self._page = await self._context.new_page()
          self._page.set_default_navigation_timeout(goto_timeout_ms(self.profile))
          self._page.set_default_timeout(min(goto_timeout_ms(self.profile), 30_000))
          if self.profile.block_consent_scripts:
            async def _block_fc(route):
              await route.abort()
            await self._page.route("**/fundingchoicesmessages.google.com/**", _block_fc)
            await self._page.route("**/www.google.com/adsense/**", _block_fc)
            await self._page.route("**/pagead2.googlesyndication.com/**", _block_fc)
            await self._page.route("**/*.doubleclick.net/**", _block_fc)
            await self._page.route("**/www.googletagmanager.com/**", _block_fc)
          wait_until = goto_wait_until(self.profile)
          self._nav_collector = NavigationDiagnosticsCollector(
            requested_url=self.url,
            wait_until=wait_until,
            browser_launch_mode=self._browser_launch_mode,
          )
          self._nav_collector.attach(self._page)

        await _run_stage(StartupStage.CONTEXT_PAGE, _open_context_page)

        async def _goto():
          if self._nav_collector:
            await self._nav_collector.probe_reachability()
          wait_until = goto_wait_until(self.profile)
          await self._page.goto(
            self.url,
            wait_until=wait_until,
            timeout=goto_timeout_ms(self.profile),
          )

        await _run_stage(StartupStage.PAGE_GOTO, _goto)
      await _run_stage(StartupStage.BOOTSTRAP, self._run_bootstrap)
      await _run_stage(StartupStage.READINESS_WAIT, self._wait_for_readiness)
      if self.cdp_url and self._page and self._cdp_expected_url:
        await self._validate_cdp_target_identity()
      await _run_stage(StartupStage.DIAGNOSTICS, self.refresh_page_diagnostics)
      self.attached = True
      self._startup_diagnostics = tracker.build_diagnostics(failed_stage=None, error_message="")
      return True
    except PlaywrightStartupError as exc:
      await self._capture_failure_bundle(exc, tracker)
      await self._cleanup_after_failed_attach()
      exc.diagnostics = self._startup_diagnostics
      raise
    except Exception as exc:
      startup_exc = PlaywrightStartupError(
        StartupStage.BROWSER_LAUNCH,
        str(exc),
        diagnostics=self._startup_diagnostics,
      )
      await self._capture_failure_bundle(startup_exc, tracker)
      await self._cleanup_after_failed_attach()
      raise startup_exc from exc

  async def _capture_failure_bundle(self, exc: PlaywrightStartupError, tracker: StartupRunTracker) -> None:
    screenshot_path: str | None = None
    trace_path: str | None = None
    if self._page:
      try:
        screenshot_path = str(self.artifacts_dir / f"attach-failure-{exc.stage.value}.png")
        await self._page.screenshot(path=screenshot_path, full_page=False)
      except Exception as capture_exc:
        logger.warning("playwright_failure_screenshot_failed error=%s", capture_exc)
    if self.record_trace and self._context:
      try:
        trace_path = str(self.artifacts_dir / f"attach-failure-{exc.stage.value}-trace.zip")
        await self._context.tracing.stop(path=trace_path)
        self._trace_path = trace_path
      except Exception as capture_exc:
        logger.warning("playwright_failure_trace_failed error=%s", capture_exc)
    diagnostics = tracker.build_diagnostics(
      failed_stage=exc.stage,
      error_message=str(exc),
      screenshot_path=screenshot_path,
      trace_path=trace_path,
      page_goto=await self._build_page_goto_diagnostics(exc.stage),
    )
    log_path = write_startup_log(
      self.artifacts_dir / f"startup-failure-{exc.stage.value}.json",
      diagnostics,
    )
    diagnostics.log_path = log_path
    self._startup_diagnostics = diagnostics
    logger.error(
      "playwright_startup_failed stage=%s timings=%s screenshot=%s trace=%s log=%s final_url=%s reachability=%s",
      exc.stage.value,
      tracker.stage_timings_ms,
      screenshot_path,
      trace_path,
      log_path,
      diagnostics.page_goto.final_url if diagnostics.page_goto else None,
      (
        diagnostics.page_goto.network_reachability.reachable
        if diagnostics.page_goto and diagnostics.page_goto.network_reachability
        else None
      ),
    )

  async def _build_page_goto_diagnostics(self, stage: StartupStage):
    if stage != StartupStage.PAGE_GOTO or not self._nav_collector:
      return None
    snapshot = await self._nav_collector.snapshot_page(self._page)
    return self._nav_collector.build(snapshot)

  async def _cleanup_after_failed_attach(self) -> None:
    try:
      if self._context:
        await self._context.close()
      if self._browser:
        await self._browser.close()
      if self._pw:
        await self._pw.stop()
    except Exception:
      pass
    self._context = None
    self._browser = None
    self._page = None
    self._pw = None
    self.attached = False

  async def _wait_for_readiness(self) -> None:
    if not self._page:
      return
    timeout = self.profile.readiness_timeout_ms
    found = False
    if self.profile.readiness_selector:
      try:
        await self._page.wait_for_selector(self.profile.readiness_selector, timeout=timeout)
        found = True
      except Exception:
        try:
          count = await self._page.evaluate(
            f"() => document.querySelectorAll('{self.profile.readiness_selector}').length"
          )
          if count > 0:
            found = True
            logger.info(
              "playwright_readiness_dom_fallback profile=%s selector=%s count=%s",
              self.profile.profile_id, self.profile.readiness_selector, count,
            )
        except Exception:
          pass
      if not found and self.profile.readiness_required:
        raise RuntimeError(
          f"readiness selector not found within {timeout}ms: {self.profile.readiness_selector}"
        )
      if not found:
        logger.warning(
          "playwright_readiness_soft_miss profile=%s selector=%s",
          self.profile.profile_id, self.profile.readiness_selector,
        )
    if not found and self.profile.lobby_selectors:
      for name, sel in self.profile.lobby_selectors.items():
        for locator_str in [sel.primary, *sel.fallbacks]:
          try:
            await self._page.wait_for_selector(locator_str, timeout=min(timeout, 10_000))
            logger.info("playwright_readiness_lobby_found profile=%s selector=%s", self.profile.profile_id, name)
            found = True
            break
          except Exception:
            continue
        if found:
          break
    if not found and self.profile.canvas_selector:
      try:
        await self._page.wait_for_selector(self.profile.canvas_selector, timeout=min(timeout, 10_000))
        logger.info("playwright_readiness_canvas_found profile=%s", self.profile.profile_id)
        found = True
      except Exception as exc:
        if self.profile.readiness_required:
          raise RuntimeError(
            f"canvas selector not found within {timeout}ms: {self.profile.canvas_selector}"
          ) from exc
        logger.warning("playwright_readiness_canvas_soft_miss profile=%s error=%s", self.profile.profile_id, exc)
    if not found and self.profile.readiness_required:
      raise RuntimeError(f"no readiness signal within {timeout}ms for profile {self.profile.profile_id}")

  async def _validate_cdp_target_identity(self) -> None:
    """Post-attach validation: verify the page matches profile domain."""
    if not self._page or not self._cdp_expected_url:
      return
    try:
      current_url = self._page.url or ""
      expected = self._cdp_expected_url
      if expected not in current_url:
        logger.warning(
          "cdp_target_redirect_detected expected_url=%s current_url=%s",
          expected, current_url,
        )
      else:
        logger.info(
          "cdp_target_identity_validated url=%s",
          current_url,
        )
    except Exception:
      pass

  def is_url_compatible_with_profile(self, url: str) -> bool:
    """Check if a URL is compatible with this profile's allowed domains."""
    if not self.profile.allowed_domains:
      return True
    from urllib.parse import urlparse
    try:
      parsed = urlparse(url)
      hostname = (parsed.hostname or "").lower()
      for domain in self.profile.allowed_domains:
        if hostname == domain or hostname.endswith("." + domain):
          return True
      return False
    except Exception:
      return False

  async def _run_bootstrap(self) -> None:
    if not self._page or not self.profile.bootstrap_on_attach:
      return
    try:
      await self._page.evaluate("""() => {
        const style = document.createElement('style');
        style.textContent = `
          .fc-consent-root, .fc-dialog-overlay, .fc-consent-dialog,
          [class*="fc-"], [id*="fc-"] {
            display: none !important;
            visibility: hidden !important;
            pointer-events: none !important;
            z-index: -9999 !important;
          }
        `;
        document.head.appendChild(style);
      }""")
    except Exception:
      pass
    try:
        await self._page.evaluate("""() => {
            const acceptBtn = document.querySelector('a.button:not(.red)');
            if (acceptBtn && acceptBtn.textContent.includes('Accept')) {
                acceptBtn.click();
                return 'clicked_accept';
            }
            const consentBtn = document.querySelector('#consent-buttons button:last-child');
            if (consentBtn) {
                consentBtn.click();
                return 'clicked_consent';
            }
            return null;
        }""")
        await self._page.wait_for_timeout(2000)
    except Exception:
        pass
    consent_selectors = [
        'button:has-text("Accept Cookies")',
        'a:has-text("Accept Cookies")',
        'button:has-text("Accept")',
        'button:has-text("Consent")',
    ]
    for sel in consent_selectors:
        try:
            loc = self._page.locator(sel)
            if await loc.count() > 0:
                await loc.first.click(timeout=5000, force=True)
                await self._page.wait_for_timeout(2000)
                logger.info("playwright_bootstrap_consent_click profile=%s selector=%s", self.profile.profile_id, sel)
                break
        except Exception:
            continue
    for frame in self._page.frames:
        if frame == self._page.main_frame:
            continue
        try:
            consent_btn = frame.locator('button:has-text("Consent")')
            if await consent_btn.count() > 0:
                await consent_btn.first.click(timeout=5000, force=True)
                await self._page.wait_for_timeout(1500)
                logger.info("playwright_bootstrap_consent_frame profile=%s frame=%s", self.profile.profile_id, frame.url)
                break
        except Exception:
            continue
    for key, selector in self.profile.action_mappings.items():
        if not key.startswith("bootstrap_"):
            continue
        try:
            loc = self._page.locator(selector)
            if await loc.count() > 0:
                await loc.first.click(timeout=10_000, force=True)
                await self._page.wait_for_timeout(1500)
                logger.info("playwright_bootstrap_ok profile=%s action=%s", self.profile.profile_id, key)
            else:
                logger.info("playwright_bootstrap_skip profile=%s action=%s reason=not_visible", self.profile.profile_id, key)
        except Exception as exc:
            logger.warning("playwright_bootstrap_failed profile=%s action=%s error=%s", self.profile.profile_id, key, exc)

  async def detach(self) -> None:
    if self.record_trace and self._context:
      trace_file = self.artifacts_dir / "trace.zip"
      await self._context.tracing.stop(path=str(trace_file))
      self._trace_path = str(trace_file)
    if self._context:
      await self._context.close()
    if self._browser:
      await self._browser.close()
    if self._pw:
      await self._pw.stop()
    self.attached = False

  async def extract_dom_nodes(self) -> list[DomNodeEvidence]:
    if not self._page:
      return []
    nodes: list[DomNodeEvidence] = []
    for name, sel in self.profile.selectors.items():
      result = await resolve_selector_chain(self._page, name, sel, tier="required")
      if result.winning_selector:
        locator_strs = [result.winning_selector]
      else:
        locator_strs = [sel.primary, *sel.fallbacks]
      for locator_str in locator_strs:
        try:
          loc = self._page.locator(locator_str)
          count = await loc.count()
          for i in range(min(count, 10)):
            el = loc.nth(i)
            box = await el.bounding_box()
            text = (await el.inner_text()).strip() if await el.is_visible() else ""
            test_id = await el.get_attribute("data-testid")
            attrs: dict[str, str] = {}
            for attr in ("data-color", "data-value", "class"):
              val = await el.get_attribute(attr)
              if val:
                attrs[attr] = val
            if result.winning_level and result.winning_level != "primary":
              attrs["_fallback_level"] = result.winning_level
            nodes.append(
              DomNodeEvidence(
                selector=f"{locator_str}>>nth={i}",
                tag=name,
                text=text,
                test_id=test_id,
                attributes=attrs,
                bbox=box,
              )
            )
          if result.winning_selector and count > 0:
            break
        except Exception:
          continue
    return nodes

  async def capture_evidence(self) -> tuple[Any, Any, str | None]:
    from uno_adapter_web.agent_trace import TraceManager
    from uno_schemas.adapter_web import AdapterEvidenceBundle
    from uno_schemas.perception import ScreenshotFrame

    nodes = await self.extract_dom_nodes()
    diagnostics = await self.refresh_page_diagnostics()
    snapshot = build_extracted_snapshot(self.profile, nodes, self.url)
    snapshot.extracted["page_diagnostics"] = diagnostics.model_dump(mode="json")
    if self._canvas_bounds:
      snapshot.extracted["canvas_bounds"] = self._canvas_bounds

    screenshot_path: str | None = None
    screenshot_frame = None
    raw_screenshot: bytes | None = None
    observe_grounding = None
    if self._page:
      try:
        screenshot_path = str(self.artifacts_dir / f"screenshot-{int(time.time()*1000)}.png")
        await self._page.screenshot(path=screenshot_path, full_page=False)
        raw_screenshot = Path(screenshot_path).read_bytes()
        screenshot_frame = ScreenshotFrame(
          frame_id=str(uuid4()),
          session_id=self.session_id,
          width=1280,
          height=800,
          path=screenshot_path,
          data_base64=base64.b64encode(raw_screenshot).decode("ascii"),
          captured_at_ms=int(time.time() * 1000),
        )

        if self.profile.match_automation == "canvas_coordinate":
          try:
            from PIL import Image as _Image
            from uno_adapter_web.hand_detection import detect_game_elements
            img = _Image.open(screenshot_path)
            hand_region = self.profile.layout_targets.get("hand_area") if hasattr(self.profile, "layout_targets") else None
            draw_region = (self.profile.layout_targets.get("draw_area")
                          or self.profile.layout_targets.get("draw_card")) if hasattr(self.profile, "layout_targets") else None
            grounding = detect_game_elements(
              img,
              hand_region=hand_region,
              draw_region=draw_region,
            )
            self._last_grounding = grounding
            observe_grounding = grounding
            snapshot.extracted["action_grounding"] = {
              "hand": [
                {"color": c.color, "number": c.number, "slot_index": c.slot_index, "bbox": c.bbox,
                 "click_x": c.click_x, "click_y": c.click_y, "confidence": c.confidence,
                 "number_confidence": c.number_confidence}
                for c in grounding.hand
              ],
              "draw_pile": grounding.draw_pile,
              "draw_pile_click": list(grounding.draw_pile_click) if grounding.draw_pile_click else None,
              "detection_confidence": grounding.detection_confidence,
              "method": grounding.method,
            }
            if grounding.hand:
              snapshot.extracted["hand_cards"] = [
                {"color": c.color, "number": c.number, "slot_index": c.slot_index} for c in grounding.hand
              ]
              if not snapshot.extracted.get("top_card") and grounding.hand:
                snapshot.extracted["top_card"] = {"color": grounding.hand[0].color, "value": grounding.hand[0].number or "unknown"}
              logger.info(
                "cv_detection_ok hand_cards=%d confidence=%.2f draw=%s",
                len(grounding.hand), grounding.detection_confidence,
                "yes" if grounding.draw_pile else "no",
              )
            else:
              logger.info(
                "cv_detection_empty hand_region=%s draw_region=%s canvas=%dx%d",
                hand_region, draw_region, img.size[0], img.size[1],
              )
          except Exception as cv_exc:
            logger.warning("cv_detection_failed error=%s", str(cv_exc))

        # TRACE: observe — save exact screenshot used for CV
        if raw_screenshot and self._page:
          self._trace_step += 1
          logger.info(
            "trace_observe_calling session=%s step=%d raw_bytes=%d page_url=%s",
            self.session_id, self._trace_step, len(raw_screenshot), self._page.url,
          )
          try:
            await TraceManager.capture_observe(
              self.session_id, self._trace_step, self._page,
              raw_screenshot, snapshot.extracted, observe_grounding,
            )
          except Exception as trace_exc:
            logger.warning("trace_observe_failed session=%s error=%s", self.session_id, trace_exc)

      except Exception as capture_exc:
        logger.warning("capture_evidence_screenshot_failed session=%s error=%s", self.session_id, capture_exc)
        screenshot_path = None
        screenshot_frame = None

    # Build dom_evidence AFTER CV pipeline writes to snapshot.extracted
    # so that top_card, hand_cards, action_grounding are included
    dom_evidence = dom_snapshot_to_evidence(snapshot)

    bundle = AdapterEvidenceBundle(
      adapter_id="pending",
      session_id=self.session_id,
      dom_snapshot=snapshot,
      dom_evidence=dom_evidence,
      screenshot=screenshot_frame,
      chat_messages=snapshot.extracted.get("chat_messages", []),
    )
    return snapshot, bundle, screenshot_path

  async def execute(self, req: ActionExecutionRequest, correlation_id: str | None = None) -> ActionExecutionResult:
    start = time.perf_counter()
    if not self._page or not self.attached:
      return ActionExecutionResult(success=False, action_type=req.action_type, error="not attached", correlation_id=correlation_id)
    try:
      diagnostics = await self.refresh_page_diagnostics()
      from uno_adapter_web.agent_trace import TraceManager
      from uno_adapter_web.coordinate_reliability import (
        convert_cv_to_css,
        validate_click_target,
      )
      from uno_adapter_web.gesture_planner import GestureType, plan_gesture

      action_str = req.action_type.value if hasattr(req.action_type, 'value') else str(req.action_type)
      selector_key = req.selector_key or req.domain_action or "play_card"
      slot_index = req.extra.get("slot_index")
      target_source = "none"
      raw_x = raw_y = None
      target_bbox = None

      # --- Resolve target coordinates ---
      if req.action_type == WebActionType.CLICK_COORDINATE or action_requires_canvas_click(req, self.profile):
        if self._last_grounding and self._last_grounding.hand and slot_index is not None:
          for card in self._last_grounding.hand:
            if card.slot_index == slot_index:
              raw_x, raw_y = float(card.click_x), float(card.click_y)
              target_source = "cv_card"
              target_bbox = card.bbox
              break

        if target_source == "none" and selector_key == "draw" and self._last_grounding and self._last_grounding.draw_pile_click:
          raw_x = float(self._last_grounding.draw_pile_click[0])
          raw_y = float(self._last_grounding.draw_pile_click[1])
          target_source = "cv_draw"

        if target_source == "none" and self._canvas_bounds:
          static_point, _label = build_coordinate_click_payload(selector_key, self.profile, self._canvas_bounds)
          raw_x, raw_y = static_point["x"], static_point["y"]
          target_source = "static_profile"

        if target_source == "none":
          if not self._canvas_bounds:
            return ActionExecutionResult(success=False, action_type=req.action_type, selector_key=req.selector_key, diagnostics=diagnostics, error=f"{diagnostics.message} Canvas bounds unavailable", duration_ms=int((time.perf_counter() - start) * 1000), correlation_id=correlation_id)

      # --- Plan gesture ---
      gesture_plan = plan_gesture(
        action_str, self.profile.profile_id,
        target_x=raw_x, target_y=raw_y, raw_x=raw_x, raw_y=raw_y,
        bbox=target_bbox, target_source=target_source,
        hand_cards=[{"color": c.color, "number": c.number, "slot_index": c.slot_index} for c in (self._last_grounding.hand if self._last_grounding else [])],
        card_color=req.extra.get("card_color"), card_value=req.extra.get("card_value"),
        available_grounding=self._last_grounding is not None and bool(self._last_grounding.hand),
      )
      logger.info("gesture_plan type=%s target_source=%s confidence=%s rationale=%s", gesture_plan.gesture_type, target_source, gesture_plan.confidence, gesture_plan.rationale[:80])

      # --- Convert coordinates ---
      coord_conv = None
      click_point = None
      if gesture_plan.target and raw_x is not None and raw_y is not None:
        coord_conv = convert_cv_to_css(raw_x, raw_y, self._dpr, self._canvas_bounds)
        if not coord_conv.valid:
          return ActionExecutionResult(success=False, action_type=req.action_type, selector_key=req.selector_key, error=f"invalid coordinates: {coord_conv.reason}", duration_ms=int((time.perf_counter() - start) * 1000), correlation_id=correlation_id)
        click_point = {"x": coord_conv.css_x, "y": coord_conv.css_y}
        validate_click_target(coord_conv.css_x, coord_conv.css_y, self._canvas_bounds)

      # --- Trace before ---
      grounding_before = self._last_grounding
      self._trace_step += 1
      try:
        await TraceManager.capture_execute_before(self.session_id, self._trace_step, self._page, action_str, selector_key, click_point, self._dpr, target_source, grounding_before)
      except Exception as trace_exc:
        logger.warning("trace_execute_before_failed session=%s error=%s", self.session_id, trace_exc)

      # --- Execute gesture ---
      if click_point and gesture_plan.gesture_type == GestureType.CLICK:
        await self._page.mouse.click(click_point["x"], click_point["y"])
      elif click_point and gesture_plan.gesture_type == GestureType.DOUBLE_CLICK:
        await self._page.mouse.dblclick(click_point["x"], click_point["y"])
      elif click_point and gesture_plan.gesture_type == GestureType.HOVER:
        await self._page.mouse.move(click_point["x"], click_point["y"])
      elif gesture_plan.gesture_type == GestureType.DRAG and gesture_plan.drag_from and gesture_plan.drag_to:
        fx, fy = gesture_plan.drag_from.x, gesture_plan.drag_from.y
        tx, ty = gesture_plan.drag_to.x, gesture_plan.drag_to.y
        await self._page.mouse.move(fx, fy)
        await self._page.mouse.down()
        steps = 5
        for i in range(1, steps + 1):
          t = i / steps
          mx = fx + (tx - fx) * t
          my = fy + (ty - fy) * t
          await self._page.mouse.move(mx, my)
        await self._page.mouse.up()
      elif click_point and gesture_plan.gesture_type == GestureType.CLICK_THEN_DROP and gesture_plan.drag_to:
        await self._page.mouse.click(click_point["x"], click_point["y"])
        import asyncio as _aio2
        await _aio2.sleep(0.1)
        await self._page.mouse.move(gesture_plan.drag_to.x, gesture_plan.drag_to.y)
      elif req.action_type == WebActionType.CLICK and req.selector:
        await self._page.locator(req.selector).click(timeout=req.timeout_ms)
      elif req.action_type == WebActionType.TYPE and req.selector and req.text is not None:
        await self._page.locator(req.selector).fill(req.text, timeout=req.timeout_ms)
      elif req.action_type == WebActionType.PRESS and req.key:
        await self._page.keyboard.press(req.key)
      elif req.action_type == WebActionType.SELECT and req.selector:
        await self._page.locator(req.selector).click(timeout=req.timeout_ms)
      elif click_point:
        await self._page.mouse.click(click_point["x"], click_point["y"])

      # --- Post-action grounding + verification ---
      grounding_after = None
      verification_result = None
      if self.profile.match_automation == "canvas_coordinate" and self._page:
        try:
          import asyncio as _aio

          from uno_adapter_web.hand_detection import detect_game_elements
          await _aio.sleep(0.2)
          after_bytes = await self._page.screenshot(full_page=False)
          from PIL import Image as _Image2
          after_img = _Image2.open(BytesIO(after_bytes))
          hr = self.profile.layout_targets.get("hand_area") if hasattr(self.profile, "layout_targets") else None
          dr = (self.profile.layout_targets.get("draw_area") or self.profile.layout_targets.get("draw_card")) if hasattr(self.profile, "layout_targets") else None
          grounding_after = detect_game_elements(after_img, hand_region=hr, draw_region=dr)
        except Exception as post_exc:
          logger.warning("post_action_grounding_failed error=%s", str(post_exc))

      from uno_adapter_web.action_verification import compare_grounding, verify_action
      evidence = compare_grounding(grounding_before, grounding_after)
      verification_result = verify_action(
        action_str, gesture_plan.gesture_type.value,
        delivery_success=True,
        evidence=evidence,
      )
      logger.info("verification outcome=%s rationale=%s", verification_result.outcome, verification_result.rationale[:100])

      # --- Trace after ---
      try:
        await TraceManager.capture_execute_after(self.session_id, self._trace_step, self._page, action_str, True, grounding_before=grounding_before, grounding_after=grounding_after)
      except Exception as trace_exc:
        logger.warning("trace_execute_after_failed session=%s error=%s", self.session_id, trace_exc)

      screenshot_path = str(self.artifacts_dir / f"action-{int(time.perf_counter()*1000)}.png")
      try:
        await self._page.screenshot(path=screenshot_path)
      except Exception:
        screenshot_path = None

      return ActionExecutionResult(success=True, action_type=req.action_type, selector=req.selector, selector_key=req.selector_key, click_point=click_point, canvas_bounds=self._canvas_bounds, diagnostics=diagnostics, duration_ms=int((time.perf_counter() - start) * 1000), screenshot_path=screenshot_path, correlation_id=correlation_id)
    except Exception as exc:
      fail_path = str(self.artifacts_dir / f"failure-{int(time.time()*1000)}.png")
      try:
        await self._page.screenshot(path=fail_path)
      except Exception:
        fail_path = None
      diagnostics = self._page_diagnostics or await self.refresh_page_diagnostics()
      return ActionExecutionResult(success=False, action_type=req.action_type, selector=req.selector, selector_key=req.selector_key, canvas_bounds=self._canvas_bounds, diagnostics=diagnostics, error=str(exc), duration_ms=int((time.perf_counter() - start) * 1000), screenshot_path=fail_path, correlation_id=correlation_id)

  async def read_dom_dict(self) -> dict:
    nodes = await self.extract_dom_nodes()
    snapshot = build_extracted_snapshot(self.profile, nodes, self.url)
    return snapshot.extracted
