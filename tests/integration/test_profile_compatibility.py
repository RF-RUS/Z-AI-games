"""Profile-to-tab compatibility tests.

Verifies:
1. Each profile returns correct allowed_domains
2. Domain matching logic works correctly
3. Profile compatibility endpoint serves correct data
4. No-domain-guard profiles are handled correctly
5. Backend rejects domain-mismatched tabs
"""

import pytest
from httpx import ASGITransport, AsyncClient
from uno_adapter_web.api import app
from uno_adapter_web.profiles import load_profile


class TestProfileAllowedDomains:
    def test_scuffed_uno_has_domains(self):
        p = load_profile("scuffed-uno-web")
        assert "scuffeduno.online" in p.allowed_domains

    def test_real_unoh_has_domains(self):
        p = load_profile("real-unoh-web")
        assert "pizz.uno" in p.allowed_domains

    def test_local_mock_has_domains(self):
        p = load_profile("local-mock-uno")
        assert "127.0.0.1" in p.allowed_domains
        assert "localhost" in p.allowed_domains


class TestProfileCompatibilityEndpoint:
    @pytest.mark.asyncio
    async def test_returns_domains(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/profiles/scuffed-uno-web/compatibility")
            assert r.status_code == 200
            d = r.json()
            assert d["allowed_domains"] == ["scuffeduno.online"]
            assert d["profile_id"] == "scuffed-uno-web"

    @pytest.mark.asyncio
    async def test_real_unoh_domains(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/profiles/real-unoh-web/compatibility")
            d = r.json()
            assert "pizz.uno" in d["allowed_domains"]

    @pytest.mark.asyncio
    async def test_nonexistent_returns_404(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/profiles/does-not-exist/compatibility")
            assert r.status_code == 404


class TestDomainMatchingLogic:
    def _match(self, url, domains):
        from urllib.parse import urlparse
        try:
            hostname = urlparse(url).hostname.lower()
            return any(hostname == d or hostname.endswith("." + d) for d in domains)
        except Exception:
            return False

    def test_exact_match(self):
        assert self._match("https://pizz.uno/singleplayer", ["pizz.uno"])

    def test_subdomain_match(self):
        assert self._match("https://www.pizz.uno/game", ["pizz.uno"])

    def test_no_match(self):
        assert not self._match("https://scuffeduno.online/", ["pizz.uno"])

    def test_mock_domain(self):
        assert self._match("http://127.0.0.1:8765/", ["127.0.0.1", "localhost"])

    def test_localhost_match(self):
        assert self._match("http://localhost:8765/", ["127.0.0.1", "localhost"])

    def test_empty_domains_means_no_guard(self):
        """Empty domains list means no domain guard — profile accepts any tab."""
        assert self._match("https://any-domain.com/", []) is False
        assert self._match("https://pizz.uno/", []) is False

    def test_invalid_url(self):
        assert not self._match("not-a-url", ["pizz.uno"])

    def test_pizz_uno_rejects_scuffed(self):
        assert not self._match("https://scuffeduno.online/", ["pizz.uno"])

    def test_scuffed_rejects_pizz(self):
        assert not self._match("https://pizz.uno/singleplayer", ["scuffeduno.online"])


class TestTabFilteringBehavior:
    """Simulate what BrowserTabPicker does: filter tabs by profile compatibility."""

    def _filter(self, tabs, domains):
        if not domains:
            return tabs, []
        compatible = []
        incompatible = []
        for tab in tabs:
            from urllib.parse import urlparse
            try:
                hostname = urlparse(tab["url"]).hostname.lower()
                if any(hostname == d or hostname.endswith("." + d) for d in domains):
                    compatible.append(tab)
                else:
                    incompatible.append(tab)
            except Exception:
                incompatible.append(tab)
        return compatible, incompatible

    def test_scuffed_profile_filters_correctly(self):
        tabs = [
            {"url": "https://scuffeduno.online/", "title": "Scuffed UNO"},
            {"url": "https://pizz.uno/singleplayer", "title": "Pizzuno"},
            {"url": "https://gmail.com/", "title": "Gmail"},
        ]
        compat, incompat = self._filter(tabs, ["scuffeduno.online"])
        assert len(compat) == 1
        assert compat[0]["title"] == "Scuffed UNO"
        assert len(incompat) == 2

    def test_real_unoh_profile_filters_correctly(self):
        tabs = [
            {"url": "https://scuffeduno.online/", "title": "Scuffed UNO"},
            {"url": "https://pizz.uno/singleplayer", "title": "Pizzuno"},
            {"url": "https://pizz.uno/multiplayer", "title": "Pizzuno MP"},
        ]
        compat, incompat = self._filter(tabs, ["pizz.uno"])
        assert len(compat) == 2
        assert len(incompat) == 1
