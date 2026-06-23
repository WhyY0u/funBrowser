"""ImpersonatedHTTPClient unit tests (no network)."""

from __future__ import annotations

import pytest

from funbrowser.tls import SUPPORTED_PROFILES, ImpersonatedHTTPClient, available


def test_extras_available() -> None:
    """funbrowser[tls] is in the dev group — curl_cffi must import."""
    assert available() is True


def test_constructor_validates_profile() -> None:
    with pytest.raises(ValueError):
        ImpersonatedHTTPClient(profile="not-a-real-profile")


def test_default_profile_is_chrome_recent() -> None:
    c = ImpersonatedHTTPClient()
    assert c.profile.startswith("chrome")


def test_supported_profiles_include_chrome_safari_firefox() -> None:
    profiles = set(SUPPORTED_PROFILES)
    assert any(p.startswith("chrome") for p in profiles)
    assert any(p.startswith("safari") for p in profiles)
    assert any(p.startswith("firefox") for p in profiles)


async def test_set_cookies_accepts_browser_cookie_shape() -> None:
    c = ImpersonatedHTTPClient()
    # The shape Browser.cookies() returns (CDP Network.Cookie).
    c.set_cookies(
        [
            {"name": "session", "value": "abc", "domain": ".example.com"},
            {"name": "csrf", "value": "xyz", "domain": "example.com"},
        ]
    )
    # No exception means we accepted the dicts. We don't assert the
    # internal cookie jar shape — curl_cffi handles that.
    await c.aclose()


@pytest.mark.skip(reason="network — run manually to verify TLS impersonation works")
async def test_real_tls_impersonation_changes_ja4() -> None:
    """Hit tls.peet.ws once per profile and confirm the JA4 differs."""
    async with ImpersonatedHTTPClient(profile="chrome131") as c1:
        r1 = (await c1.get("https://tls.peet.ws/api/all")).json()
    async with ImpersonatedHTTPClient(profile="safari17_0") as c2:
        r2 = (await c2.get("https://tls.peet.ws/api/all")).json()
    assert r1["tls"]["ja4"] != r2["tls"]["ja4"]
