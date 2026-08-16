"""E2E prerequisite guards.

E2E tests must SKIP (not FAIL) when the environment lacks prerequisites.
Checking only `import playwright` is not enough: the Python package can be
installed while the browser binaries were never downloaded
(`playwright install chromium`), which made these tests fail with
"Executable doesn't exist" on hosts that simply hadn't run the installer.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest


@lru_cache(maxsize=1)
def chromium_installed() -> bool:
  """True if the Playwright Chromium browser binary exists on this host."""
  try:
    from playwright.sync_api import sync_playwright
  except ImportError:
    return False
  try:
    with sync_playwright() as p:
      return Path(p.chromium.executable_path).exists()
  except Exception:
    return False


@lru_cache(maxsize=1)
def pizzuno_reachable() -> bool:
  """True if the real Pizzuno target answers (network required)."""
  import httpx

  try:
    r = httpx.head("https://pizz.uno/singleplayer", timeout=3.0, follow_redirects=True)
    return r.status_code < 500
  except Exception:
    return False


requires_chromium = pytest.mark.skipif(
  not chromium_installed(),
  reason="Playwright Chromium browser not installed (run: python -m playwright install chromium)",
)

requires_pizzuno = pytest.mark.skipif(
  not (chromium_installed() and pizzuno_reachable()),
  reason="pizz.uno unreachable or Playwright Chromium not installed",
)
