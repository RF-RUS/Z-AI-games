"""Attach startup failure reporting in PlaywrightSession."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_adapter_web.profiles import load_profile
from uno_adapter_web.runtime import PlaywrightSession
from uno_adapter_web.startup import PlaywrightStartupError, StartupStage


@pytest.mark.asyncio
async def test_attach_reports_page_goto_stage_failure():
  profile = load_profile("scuffed-uno-web")
  session = PlaywrightSession("sess-1", profile, headless=True)

  mock_pw = MagicMock()
  mock_browser = AsyncMock()
  mock_context = AsyncMock()
  mock_page = AsyncMock()
  mock_browser.new_context.return_value = mock_context
  mock_context.new_page.return_value = mock_page
  mock_page.goto.side_effect = TimeoutError("navigation timed out")

  with patch("playwright.async_api.async_playwright") as mock_async_pw:
    mock_async_pw.return_value.start = AsyncMock(return_value=mock_pw)
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    with pytest.raises(PlaywrightStartupError) as exc_info:
      await session.attach()

  assert exc_info.value.stage == StartupStage.PAGE_GOTO
  assert "navigation timed out" in str(exc_info.value)
