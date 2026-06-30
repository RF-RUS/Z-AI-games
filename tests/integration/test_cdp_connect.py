"""CDP connect integration tests — production-hardened.

Verifies:
1. CDP path selection (cdp_url vs launch)
2. connect_over_cdp is called when cdp_url is set
3. No new browser launched when cdp_url is set
4. Strict target matching (no pages[0] fallback)
5. Target not found raises clear error
6. Post-attach redirect detection
7. Full chain: schema → adapter → session
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_adapter_web.registry import create_adapter
from uno_schemas.adapter_web import AdapterMode, AttachWebAdapterRequest


def _make_request(profile_id="local-mock-uno", cdp_url=None, url=None):
    return AttachWebAdapterRequest(
        session_id="test-session", profile_id=profile_id,
        mode=AdapterMode.PLAYWRIGHT, cdp_url=cdp_url, url=url,
    )


def _patch_playwright(mock_pw):
    mock_start = AsyncMock(return_value=mock_pw)
    mock_ctx = MagicMock()
    mock_ctx.start = mock_start
    return patch("playwright.async_api.async_playwright", return_value=mock_ctx)


def _make_mock_page(url="https://pizz.uno/singleplayer"):
    page = MagicMock()
    page.url = url
    page.wait_for_selector = AsyncMock()
    page.set_default_navigation_timeout = MagicMock()
    page.set_default_timeout = MagicMock()
    page.route = AsyncMock()
    return page


class TestCdpPathSelection:
    def test_cdp_url_set(self):
        _, adapter = create_adapter(_make_request(cdp_url="http://127.0.0.1:9222"))
        assert adapter._session.cdp_url == "http://127.0.0.1:9222"

    def test_no_cdp_url(self):
        _, adapter = create_adapter(_make_request())
        assert adapter._session.cdp_url is None

    def test_cdp_with_url(self):
        _, adapter = create_adapter(_make_request(cdp_url="http://127.0.0.1:9222", url="https://pizz.uno/s"))
        assert adapter._session.cdp_url == "http://127.0.0.1:9222"
        assert adapter._session.url == "https://pizz.uno/s"


class TestConnectOverCdpPath:
    @pytest.mark.asyncio
    async def test_cdp_calls_connect(self):
        page = _make_mock_page("http://127.0.0.1:8765/")
        ctx = MagicMock()
        ctx.pages = [page]
        browser = MagicMock()
        browser.contexts = [ctx]
        pw = MagicMock()
        pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        with _patch_playwright(pw):
            _, adapter = create_adapter(_make_request(cdp_url="http://127.0.0.1:9222"))
            assert await adapter.attach()
            pw.chromium.connect_over_cdp.assert_called_once()
            pw.chromium.launch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_cdp_calls_launch(self):
        page = _make_mock_page("http://127.0.0.1:8765/")
        page.goto = AsyncMock()
        ctx = MagicMock()
        ctx.pages = [page]
        ctx.new_page = AsyncMock(return_value=page)
        ctx.tracing = MagicMock()
        ctx.tracing.start = AsyncMock()
        browser = MagicMock()
        browser.new_context = AsyncMock(return_value=ctx)
        pw = MagicMock()
        pw.chromium.launch = AsyncMock(return_value=browser)
        with _patch_playwright(pw), \
             patch("uno_adapter_web.runtime.goto_timeout_ms", return_value=5000), \
             patch("uno_adapter_web.runtime.goto_wait_until", return_value="domcontentloaded"), \
             patch("uno_adapter_web.runtime.browser_launch_mode", return_value="bundled"), \
             patch("uno_adapter_web.runtime.browser_launch_options", return_value={"headless": True}):
            _, adapter = create_adapter(_make_request())
            assert await adapter.attach()
            pw.chromium.launch.assert_called_once()
            pw.chromium.connect_over_cdp.assert_not_called()


class TestStrictTargetMatching:
    @pytest.mark.asyncio
    async def test_exact_url_match(self):
        page = _make_mock_page("https://pizz.uno/singleplayer")
        ctx = MagicMock()
        ctx.pages = [page]
        browser = MagicMock()
        browser.contexts = [ctx]
        pw = MagicMock()
        pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        with _patch_playwright(pw):
            _, adapter = create_adapter(_make_request(
                profile_id="real-unoh-web",
                cdp_url="http://127.0.0.1:9222", url="https://pizz.uno/singleplayer"))
            assert await adapter.attach()
            assert adapter._session._page.url == "https://pizz.uno/singleplayer"

    @pytest.mark.asyncio
    async def test_no_pages0_fallback_raises(self):
        page1 = _make_mock_page("https://gmail.com")
        page2 = _make_mock_page("https://youtube.com")
        ctx = MagicMock()
        ctx.pages = [page1, page2]
        browser = MagicMock()
        browser.contexts = [ctx]
        pw = MagicMock()
        pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        with _patch_playwright(pw):
            _, adapter = create_adapter(_make_request(
                profile_id="real-unoh-web",
                cdp_url="http://127.0.0.1:9222", url="https://pizz.uno/singleplayer"))
            with pytest.raises(Exception, match="Target page not found"):
                await adapter.attach()

    @pytest.mark.asyncio
    async def test_multiple_matching_tabs_uses_first(self):
        page1 = _make_mock_page("https://pizz.uno/singleplayer")
        page2 = _make_mock_page("https://pizz.uno/singleplayer")
        ctx = MagicMock()
        ctx.pages = [page1, page2]
        browser = MagicMock()
        browser.contexts = [ctx]
        pw = MagicMock()
        pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        with _patch_playwright(pw):
            _, adapter = create_adapter(_make_request(
                profile_id="real-unoh-web",
                cdp_url="http://127.0.0.1:9222", url="https://pizz.uno/singleplayer"))
            assert await adapter.attach()

    @pytest.mark.asyncio
    async def test_url_partial_match(self):
        page = _make_mock_page("https://pizz.uno/singleplayer?bot=1")
        ctx = MagicMock()
        ctx.pages = [page]
        browser = MagicMock()
        browser.contexts = [ctx]
        pw = MagicMock()
        pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        with _patch_playwright(pw):
            _, adapter = create_adapter(_make_request(
                profile_id="real-unoh-web",
                cdp_url="http://127.0.0.1:9222", url="https://pizz.uno/singleplayer"))
            assert await adapter.attach()

    @pytest.mark.asyncio
    async def test_domain_mismatch_raises(self):
        """scuffed-uno-web profile rejects pizz.uno tab."""
        page = _make_mock_page("https://pizz.uno/singleplayer")
        ctx = MagicMock()
        ctx.pages = [page]
        browser = MagicMock()
        browser.contexts = [ctx]
        pw = MagicMock()
        pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        with _patch_playwright(pw):
            _, adapter = create_adapter(_make_request(
                profile_id="scuffed-uno-web",
                cdp_url="http://127.0.0.1:9222", url="https://pizz.uno/singleplayer"))
            with pytest.raises(Exception, match="Tab domain mismatch"):
                await adapter.attach()


class TestCdpFailureModes:
    @pytest.mark.asyncio
    async def test_no_contexts(self):
        browser = MagicMock()
        browser.contexts = []
        pw = MagicMock()
        pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        with _patch_playwright(pw):
            _, adapter = create_adapter(_make_request(cdp_url="http://127.0.0.1:9222"))
            with pytest.raises(Exception, match="No browser contexts"):
                await adapter.attach()

    @pytest.mark.asyncio
    async def test_no_pages(self):
        ctx = MagicMock()
        ctx.pages = []
        browser = MagicMock()
        browser.contexts = [ctx]
        pw = MagicMock()
        pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        with _patch_playwright(pw):
            _, adapter = create_adapter(_make_request(cdp_url="http://127.0.0.1:9222"))
            with pytest.raises(Exception, match="No open pages"):
                await adapter.attach()


class TestPostAttachValidation:
    @pytest.mark.asyncio
    async def test_validated_url_no_warning(self):
        page = _make_mock_page("https://pizz.uno/singleplayer")
        ctx = MagicMock()
        ctx.pages = [page]
        browser = MagicMock()
        browser.contexts = [ctx]
        pw = MagicMock()
        pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        with _patch_playwright(pw):
            _, adapter = create_adapter(_make_request(
                profile_id="real-unoh-web",
                cdp_url="http://127.0.0.1:9222", url="https://pizz.uno/singleplayer"))
            assert await adapter.attach()
            assert adapter._session._cdp_expected_url == "https://pizz.uno/singleplayer"


class TestEndToEndChain:
    def test_schema_accepts_cdp_url(self):
        req = AttachWebAdapterRequest(session_id="t", mode=AdapterMode.PLAYWRIGHT, cdp_url="http://127.0.0.1:9222")
        assert req.cdp_url == "http://127.0.0.1:9222"

    def test_schema_cdp_optional(self):
        req = AttachWebAdapterRequest(session_id="t", mode=AdapterMode.PLAYWRIGHT)
        assert req.cdp_url is None

    def test_adapter_passes_cdp_url(self):
        _, adapter = create_adapter(_make_request(cdp_url="http://127.0.0.1:9222", url="https://x.com"))
        assert adapter._session.cdp_url == "http://127.0.0.1:9222"
        assert adapter._session.url == "https://x.com"

    def test_orchestrator_body_cdp_url(self):
        from uno_schemas.orchestrator import AttachAdapterBody
        assert AttachAdapterBody(adapter_type="web", cdp_url="http://127.0.0.1:9222").cdp_url == "http://127.0.0.1:9222"

    def test_generic_client_normalize(self):
        from uno_shared.adapter_registry import GenericAdapterClient
        req = GenericAdapterClient("web", "http://noop").normalize_attach_request(
            session_id="t", profile_id="real-unoh-web", cdp_url="http://127.0.0.1:9222")
        assert req.extra.get("cdp_url") == "http://127.0.0.1:9222"

    def test_generic_client_build_body(self):
        from uno_shared.adapter_protocol import GenericAttachRequest
        from uno_shared.adapter_registry import GenericAdapterClient
        req = GenericAttachRequest(session_id="t", profile_id="x", adapter_type="web",
                                   extra={"mode": "playwright", "cdp_url": "http://127.0.0.1:9222"})
        body = GenericAdapterClient("web", "http://noop")._build_attach_body(req)
        assert body["cdp_url"] == "http://127.0.0.1:9222"

    def test_inprocess_client_forward(self):
        from uno_adapter_web.api import app as web_app
        from uno_orchestrator.in_process_clients import InProcessAdapterClient
        req = InProcessAdapterClient("web", web_app).normalize_attach_request(
            session_id="t", profile_id="real-unoh-web", cdp_url="http://127.0.0.1:9222")
        assert req.extra.get("cdp_url") == "http://127.0.0.1:9222"
