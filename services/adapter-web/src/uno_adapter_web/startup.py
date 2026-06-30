"""Playwright attach startup stages, timing, and errors."""

from __future__ import annotations

import logging
import os
import time
from enum import StrEnum
from pathlib import Path
from typing import Any

from uno_schemas.adapter_web import PageGotoDiagnostics, WebAdapterProfile, WebStartupDiagnostics

logger = logging.getLogger(__name__)

DEFAULT_GOTO_TIMEOUT_MS = 60_000
DEFAULT_LAUNCH_TIMEOUT_MS = 60_000
PLAYWRIGHT_ATTACH_HTTP_TIMEOUT_SEC = 120.0


class StartupStage(StrEnum):
  BROWSER_LAUNCH = "browser_launch"
  CONTEXT_PAGE = "context_page"
  PAGE_GOTO = "page_goto"
  READINESS_WAIT = "readiness_wait"
  BOOTSTRAP = "bootstrap"
  DIAGNOSTICS = "diagnostics"


class PlaywrightStartupError(RuntimeError):
  def __init__(
    self,
    stage: StartupStage,
    message: str,
    *,
    elapsed_ms: int = 0,
    cause: Exception | None = None,
    diagnostics: WebStartupDiagnostics | None = None,
  ) -> None:
    self.stage = stage
    self.elapsed_ms = elapsed_ms
    self.cause = cause
    self.detail = message
    self.diagnostics = diagnostics
    super().__init__(format_startup_failure(stage, message, elapsed_ms))

  @property
  def message(self) -> str:
    return self.detail


class StartupRunTracker:
  def __init__(self, *, profile_id: str, session_id: str, url: str) -> None:
    self.profile_id = profile_id
    self.session_id = session_id
    self.url = url
    self.stage_timings_ms: dict[str, int] = {}
    self._starts: dict[StartupStage, float] = {}

  def start(self, stage: StartupStage) -> None:
    logger.info(
      "playwright_startup_stage_start stage=%s profile=%s session=%s",
      stage.value,
      self.profile_id,
      self.session_id,
    )
    self._starts[stage] = time.perf_counter()

  def finish(self, stage: StartupStage) -> int:
    started = self._starts.pop(stage, time.perf_counter())
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    self.stage_timings_ms[stage.value] = elapsed_ms
    logger.info(
      "playwright_startup_stage_ok stage=%s elapsed_ms=%s profile=%s session=%s",
      stage.value,
      elapsed_ms,
      self.profile_id,
      self.session_id,
    )
    return elapsed_ms

  def build_diagnostics(
    self,
    *,
    failed_stage: StartupStage | None,
    error_message: str,
    screenshot_path: str | None = None,
    trace_path: str | None = None,
    log_path: str | None = None,
    page_goto: PageGotoDiagnostics | None = None,
  ) -> WebStartupDiagnostics:
    return WebStartupDiagnostics(
      failed_stage=failed_stage.value if failed_stage else None,
      error_message=error_message,
      stage_timings_ms=dict(self.stage_timings_ms),
      screenshot_path=screenshot_path,
      trace_path=trace_path,
      log_path=log_path,
      url=self.url,
      profile_id=self.profile_id,
      page_goto=page_goto,
    )


def format_startup_failure(stage: StartupStage, message: str, elapsed_ms: int = 0) -> str:
  return f"Playwright startup failed at stage={stage.value} ({elapsed_ms}ms): {message}"


def format_startup_error(exc: Exception) -> str:
  if isinstance(exc, PlaywrightStartupError):
    return str(exc)
  return f"Playwright startup failed: {exc}"


def write_startup_log(path: Path, diagnostics: WebStartupDiagnostics) -> str:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(diagnostics.model_dump_json(indent=2), encoding="utf-8")
  return str(path)


def browser_launch_options(profile: WebAdapterProfile, *, headless: bool) -> dict[str, Any]:
  launch_timeout = profile.browser_launch_timeout_ms or DEFAULT_LAUNCH_TIMEOUT_MS
  opts: dict[str, Any] = {
    "headless": headless,
    "timeout": launch_timeout,
    "args": ["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"],
  }
  channel = os.getenv("UNO_PLAYWRIGHT_CHANNEL") or profile.browser_channel
  executable = os.getenv("UNO_PLAYWRIGHT_EXECUTABLE") or profile.browser_executable_path
  if channel:
    opts["channel"] = channel
  elif executable:
    opts["executable_path"] = executable
  return opts


def browser_launch_mode(profile: WebAdapterProfile) -> str:
  channel = os.getenv("UNO_PLAYWRIGHT_CHANNEL") or profile.browser_channel
  executable = os.getenv("UNO_PLAYWRIGHT_EXECUTABLE") or profile.browser_executable_path
  if channel:
    return f"channel:{channel}"
  if executable:
    return f"executable:{executable}"
  return "bundled_chromium"


def goto_wait_until(profile: WebAdapterProfile) -> str:
  return profile.goto_wait_until or "domcontentloaded"


def goto_timeout_ms(profile: WebAdapterProfile) -> int:
  return profile.goto_timeout_ms or DEFAULT_GOTO_TIMEOUT_MS
