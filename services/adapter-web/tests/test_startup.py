"""Playwright startup stage errors and timeouts."""


from uno_adapter_web.profiles import load_profile
from uno_adapter_web.startup import (
  PLAYWRIGHT_ATTACH_HTTP_TIMEOUT_SEC,
  PlaywrightStartupError,
  StartupStage,
  browser_launch_options,
  format_startup_error,
  format_startup_failure,
)


def test_startup_error_names_failed_stage():
  err = PlaywrightStartupError(
    StartupStage.PAGE_GOTO,
    "Page.goto: Timeout 60000ms exceeded.",
    elapsed_ms=60012,
  )
  text = str(err)
  assert "stage=page_goto" in text
  assert "60012ms" in text
  assert "Timeout 60000ms exceeded" in text


def test_format_startup_error_wraps_unknown():
  assert "Playwright startup failed:" in format_startup_error(ValueError("boom"))


def test_scuffed_profile_soft_readiness_and_long_goto():
  profile = load_profile("scuffed-uno-web")
  assert profile.readiness_required is False
  assert profile.bootstrap_on_attach is False
  assert profile.goto_timeout_ms == 60_000
  assert profile.browser_launch_timeout_ms == 60_000


def test_browser_launch_options_include_safe_args():
  profile = load_profile("scuffed-uno-web")
  opts = browser_launch_options(profile, headless=True)
  assert opts["headless"] is True
  assert opts["timeout"] == 60_000
  assert "--no-sandbox" in opts["args"]


def test_playwright_attach_http_timeout_covers_profile_goto():
  profile = load_profile("scuffed-uno-web")
  assert PLAYWRIGHT_ATTACH_HTTP_TIMEOUT_SEC >= (profile.goto_timeout_ms or 0) / 1000


def test_format_startup_failure():
  msg = format_startup_failure(StartupStage.BOOTSTRAP, "Quick Play click failed", 1200)
  assert "bootstrap" in msg
  assert "1200ms" in msg
