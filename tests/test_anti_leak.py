"""Anti-leak hardening: WebRTC block, toString camouflage, geo helpers."""

from __future__ import annotations

import httpx
import pytest

import funbrowser
from funbrowser._launcher import find_chrome
from funbrowser.geo import GeoInfo, lookup_proxy_geo, make_accept_language, resolve_locale

# ── pure-Python unit tests ───────────────────────────────────────────────


def test_resolve_locale_known_country_codes() -> None:
    assert resolve_locale("US") == "en-US"
    assert resolve_locale("GB") == "en-GB"
    assert resolve_locale("DE") == "de-DE"
    assert resolve_locale("JP") == "ja-JP"
    assert resolve_locale("BR") == "pt-BR"
    assert resolve_locale("us") == "en-US"  # case-insensitive


def test_resolve_locale_unknown_country_code() -> None:
    # No mapping entry — falls back to lowercased + uppercased pattern.
    assert resolve_locale("ZZ") == "zz-ZZ"


def test_make_accept_language_for_english() -> None:
    assert make_accept_language("en-US") == "en-US,en;q=0.9"


def test_make_accept_language_for_non_english() -> None:
    out = make_accept_language("de-DE")
    assert out.startswith("de-DE,de;q=0.9")
    assert "en;q=0.8" in out


def test_make_accept_language_base_only() -> None:
    assert make_accept_language("en") == "en"


# ── integration with real Chrome ─────────────────────────────────────────

pytestmark_chrome = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


@pytestmark_chrome
async def test_webdriver_getter_tostring_looks_native() -> None:
    """The fingerprint test that classic stealth libs fail."""
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        s = await tab.evaluate(
            "Object.getOwnPropertyDescriptor(  Navigator.prototype, 'webdriver').get.toString()"
        )
        assert "[native code]" in s, f"toString leaked: {s!r}"


@pytestmark_chrome
async def test_function_prototype_tostring_itself_camouflaged() -> None:
    """Function.prototype.toString.toString() must also look native."""
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        s = await tab.evaluate("Function.prototype.toString.toString()")
        assert "[native code]" in s


@pytestmark_chrome
async def test_fb_m_marker_not_exposed_on_window() -> None:
    """The registration helper is deleted at the end of script injection."""
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        leaked = await tab.evaluate("typeof window.__fb_m")
        assert leaked == "undefined"


@pytestmark_chrome
async def test_rtc_peer_connection_strips_host_candidates() -> None:
    """createOffer SDP should not contain a=candidate ... host lines."""
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        sdp = await tab.evaluate(
            "(async () => {"
            "  const pc = new RTCPeerConnection({iceServers:[]});"
            "  pc.createDataChannel('x');"
            "  const offer = await pc.createOffer();"
            "  pc.close();"
            "  return offer.sdp;"
            "})()"
        )
        assert sdp is not None
        for line in sdp.splitlines():
            line = line.strip()
            if line.startswith("a=candidate:"):
                # No host-type candidates may slip through the filter.
                assert " host " not in line.lower(), f"host candidate leaked: {line}"


# ── geo lookup with a mock httpx transport ───────────────────────────────


async def test_lookup_proxy_geo_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "ip-api.com" in str(request.url)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "country": "United States",
                "countryCode": "US",
                "region": "California",
                "city": "San Francisco",
                "timezone": "America/Los_Angeles",
                "query": "1.2.3.4",
            },
        )

    from funbrowser.proxy import Proxy

    proxy = Proxy("http", "1.2.3.4", 8080)

    # Patch httpx.AsyncClient to use the MockTransport.
    import funbrowser.geo as geo_mod

    real_client = httpx.AsyncClient

    def fake_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        kwargs.pop("proxy", None)
        return real_client(*args, **kwargs)

    geo_mod.httpx.AsyncClient = fake_client  # type: ignore[misc]
    try:
        info = await lookup_proxy_geo(proxy)
        assert isinstance(info, GeoInfo)
        assert info.country_code == "US"
        assert info.timezone == "America/Los_Angeles"
        assert info.locale == "en-US"
        assert info.accept_language.startswith("en-US")
    finally:
        geo_mod.httpx.AsyncClient = real_client  # type: ignore[misc]


async def test_lookup_proxy_geo_failure_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    from funbrowser.proxy import Proxy

    proxy = Proxy("http", "1.2.3.4", 8080)

    import funbrowser.geo as geo_mod

    real_client = httpx.AsyncClient

    def fake_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        kwargs.pop("proxy", None)
        return real_client(*args, **kwargs)

    geo_mod.httpx.AsyncClient = fake_client  # type: ignore[misc]
    try:
        info = await lookup_proxy_geo(proxy)
        assert info is None
    finally:
        geo_mod.httpx.AsyncClient = real_client  # type: ignore[misc]
