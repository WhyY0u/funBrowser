"""Async HTTP client that performs requests with real-browser TLS fingerprints.

Wraps ``curl_cffi.requests.AsyncSession`` so that JA3/JA4 / ALPN / extension
order / GREASE values on the wire match the picked browser profile. Useful
from inside automation scripts when you want to hit an API in parallel
with the browser and have the TLS fingerprint stay consistent.

Pair with :meth:`funbrowser.Browser.cookies` if you need to carry the
browser's session into the impersonated HTTP request.
"""

from __future__ import annotations

from typing import Any

try:
    from curl_cffi import requests as _cf
except ImportError:  # pragma: no cover - tested via test_tls_http
    _cf = None  # type: ignore[assignment]


#: All TLS-impersonation profiles curl_cffi currently ships. Latest entries
#: are the most useful — they match recent stable Chrome/Safari/Firefox.
SUPPORTED_PROFILES: tuple[str, ...] = (
    # Chrome (Desktop)
    "chrome99",
    "chrome100",
    "chrome101",
    "chrome104",
    "chrome107",
    "chrome110",
    "chrome116",
    "chrome119",
    "chrome120",
    "chrome123",
    "chrome124",
    "chrome131",
    "chrome133a",
    # Chrome Android
    "chrome99_android",
    "chrome131_android",
    # Safari (Desktop)
    "safari15_3",
    "safari15_5",
    "safari17_0",
    "safari17_2_ios",
    "safari18_0",
    "safari18_0_ios",
    # Firefox
    "firefox133",
    "firefox135",
)


def available() -> bool:
    """True if ``funbrowser[tls]`` extras are installed."""
    return _cf is not None


class ImpersonatedHTTPClient:
    """HTTP client with a swappable real-browser TLS fingerprint.

    Example::

        from funbrowser.tls import ImpersonatedHTTPClient

        async with ImpersonatedHTTPClient(profile="chrome131") as http:
            r = await http.get("https://tls.peet.ws/api/all")
            print(r.json()["tls"]["ja4"])

    The client also forwards cookies on the session, so calling
    :meth:`set_cookies` with ``Browser.cookies()`` results carries the
    browser's session across protocols.
    """

    def __init__(
        self,
        *,
        profile: str = "chrome131",
        timeout: float = 30.0,
        verify: bool = True,
    ) -> None:
        if _cf is None:
            raise ImportError(
                "funbrowser.tls requires `pip install funbrowser[tls]` "
                "(adds curl_cffi + cryptography)."
            )
        if profile not in SUPPORTED_PROFILES:
            raise ValueError(
                f"profile {profile!r} not supported. Pick one of: {', '.join(SUPPORTED_PROFILES)}"
            )
        self._profile = profile
        self._session: Any = _cf.AsyncSession(
            impersonate=profile,  # type: ignore[arg-type]
            timeout=timeout,
            verify=verify,
        )

    @property
    def profile(self) -> str:
        return self._profile

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        return await self._session.request(method, url, **kwargs)

    async def get(self, url: str, **kwargs: Any) -> Any:
        return await self._session.get(url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Any:
        return await self._session.post(url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> Any:
        return await self._session.put(url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> Any:
        return await self._session.delete(url, **kwargs)

    async def head(self, url: str, **kwargs: Any) -> Any:
        return await self._session.head(url, **kwargs)

    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Bulk-set cookies on the session.

        Accepts the shape returned by ``Browser.cookies()`` (CDP
        ``Network.Cookie`` objects with ``name`` / ``value`` / ``domain``).
        """
        for c in cookies:
            name = c.get("name")
            value = c.get("value")
            domain = c.get("domain")
            if name is None or value is None:
                continue
            if domain is not None:
                self._session.cookies.set(name, value, domain=str(domain))
            else:
                self._session.cookies.set(name, value)

    async def aclose(self) -> None:
        await self._session.close()

    async def __aenter__(self) -> ImpersonatedHTTPClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
