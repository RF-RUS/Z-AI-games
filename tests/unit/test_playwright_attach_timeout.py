"""Client timeouts for Playwright attach."""

from uno_adapter_web.startup import PLAYWRIGHT_ATTACH_HTTP_TIMEOUT_SEC


def test_playwright_attach_timeout_is_at_least_two_minutes():
  assert PLAYWRIGHT_ATTACH_HTTP_TIMEOUT_SEC >= 120.0
