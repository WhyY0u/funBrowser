"""Proxy parsing for every format a proxy provider has ever invented.

Accepted on the wire — pass any of these to ``funbrowser.start(proxy=...)``:

- ``scheme://user:pass@host:port`` — RFC 3986
- ``scheme://host:port``
- ``user:pass@host:port``                — same with implicit ``http``
- ``host:port@user:pass``                — some Bright Data exports
- ``host:port``                          — no auth
- ``host:port:user:pass``                — IPRoyal, Smartproxy, most lists
- ``user:pass:host:port``                — some legacy lists
- ``host:port:user``                     — port-then-user (no password)

Schemes recognised: ``http``, ``https``, ``socks4``, ``socks5``, ``socks5h``.

The format is auto-detected by inspecting which segment contains a valid
TCP port and which side of an ``@`` looks like a ``host:port`` pair.

HTTP/HTTPS authentication is plumbed through CDP automatically. SOCKS
authentication isn't exposed by Chrome at the HTTP-auth layer; front it
with a local HTTP proxy that adds credentials upstream.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tab import Tab

logger = logging.getLogger(__name__)

VALID_SCHEMES = frozenset({"http", "https", "socks", "socks4", "socks5", "socks5h"})

_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


class ProxyParseError(ValueError):
    """Raised when a proxy string cannot be parsed into a Proxy."""


@dataclass(frozen=True, slots=True)
class Proxy:
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @property
    def has_auth(self) -> bool:
        return self.username is not None

    @property
    def is_socks(self) -> bool:
        return self.scheme.startswith("socks")

    def chrome_arg(self) -> str:
        """``--proxy-server=`` value. Auth is excluded — Chrome ignores it in the URL."""
        scheme = "socks5" if self.scheme == "socks5h" else self.scheme
        return f"{scheme}://{self.host}:{self.port}"

    def url(self) -> str:
        """Full URL including auth, for libraries that take a single proxy URL."""
        if self.has_auth:
            return f"{self.scheme}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.scheme}://{self.host}:{self.port}"


def parse(s: str | Proxy) -> Proxy:
    """Parse a proxy string in any supported format. See module docstring."""
    if isinstance(s, Proxy):
        return s
    if not isinstance(s, str):
        raise ProxyParseError(f"expected str or Proxy, got {type(s).__name__}")
    raw = s.strip()
    if not raw:
        raise ProxyParseError("empty proxy string")

    scheme = "http"
    if "://" in raw:
        scheme_part, _, rest = raw.partition("://")
        scheme = scheme_part.lower()
        if scheme not in VALID_SCHEMES:
            raise ProxyParseError(f"unknown scheme {scheme!r}")
        raw = rest

    if "@" in raw:
        return _parse_with_at(scheme, raw)
    return _parse_colon_only(scheme, raw)


def _parse_with_at(scheme: str, s: str) -> Proxy:
    left, _, right = s.rpartition("@")
    if _looks_like_server(right) and not _looks_like_server(left):
        auth, server = left, right
    elif _looks_like_server(left) and not _looks_like_server(right):
        auth, server = right, left
    elif _looks_like_server(right) and _looks_like_server(left):
        # Both sides look like host:port — prefer the standard interpretation
        # (auth on the left, server on the right).
        auth, server = left, right
    else:
        raise ProxyParseError(f"could not locate host:port on either side of '@' in {s!r}")
    user, _, pwd = auth.partition(":")
    if not user:
        raise ProxyParseError(f"empty username in {s!r}")
    host, port = _split_host_port(server)
    return Proxy(scheme, host, port, user, pwd or None)


def _parse_colon_only(scheme: str, s: str) -> Proxy:
    parts = s.split(":")
    if len(parts) == 2:
        host, port = _split_host_port(s)
        return Proxy(scheme, host, port)

    if len(parts) == 3:
        # host:port:user — port-then-user, no password
        if _is_port(parts[1]) and _looks_like_host(parts[0]):
            return Proxy(scheme, parts[0], int(parts[1]), parts[2])
        raise ProxyParseError(f"ambiguous 3-segment proxy {s!r}")

    if len(parts) == 4:
        a, b, c, d = parts
        b_is_port = _is_port(b)
        d_is_port = _is_port(d)
        if b_is_port and not d_is_port:
            return Proxy(scheme, a, int(b), c, d)
        if d_is_port and not b_is_port:
            return Proxy(scheme, c, int(d), a, b)
        if b_is_port and d_is_port:
            # Both look like ports; disambiguate by the host slot.
            if _looks_like_host(a) and not _looks_like_host(c):
                return Proxy(scheme, a, int(b), c, d)
            if _looks_like_host(c) and not _looks_like_host(a):
                return Proxy(scheme, c, int(d), a, b)
            # Final fallback: assume host:port:user:pass (the more common
            # listing convention from proxy providers).
            return Proxy(scheme, a, int(b), c, d)
        raise ProxyParseError(f"could not find a port in 4-segment proxy {s!r}")

    raise ProxyParseError(f"could not parse proxy {s!r}")


def _is_port(s: str) -> bool:
    return s.isdigit() and 1 <= int(s) <= 65535


def _looks_like_host(s: str) -> bool:
    if not s:
        return False
    if s == "localhost":
        return True
    if _IPV4.match(s):
        return True
    if "." in s and any(ch.isalpha() for ch in s):
        return True
    return False


def _looks_like_server(s: str) -> bool:
    if ":" not in s:
        return False
    host, _, port = s.rpartition(":")
    return bool(host) and _is_port(port)


def _split_host_port(s: str) -> tuple[str, int]:
    host, _, port = s.rpartition(":")
    if not host:
        raise ProxyParseError(f"missing host in {s!r}")
    if not _is_port(port):
        raise ProxyParseError(f"invalid port in {s!r}")
    return host, int(port)


async def attach_auth(tab: Tab, proxy: Proxy) -> None:
    """Install a per-tab CDP handler that satisfies HTTP/HTTPS proxy auth.

    SOCKS proxies don't surface their auth as an HTTP challenge — Chrome
    doesn't expose a public hook for it. SOCKS-with-auth callers should
    front the SOCKS server with a local HTTP proxy that adds credentials
    upstream (e.g. ``microsocks``, ``proxychains``, or ``proxy.py``).
    """
    if not proxy.has_auth:
        return
    if proxy.is_socks:
        logger.warning(
            "SOCKS proxy auth (%s) is not wired through CDP; Chrome will "
            "fail the connection. Front with a local HTTP proxy that adds "
            "credentials upstream.",
            proxy.host,
        )
        return

    # `handleAuthRequests=True` without `patterns` means only auth-required
    # requests are paused — pass-through stays fast for everything else.
    await tab._send("Fetch.enable", {"handleAuthRequests": True})

    user = proxy.username or ""
    pwd = proxy.password or ""

    async def _on_auth_required(params: dict[str, object]) -> None:
        try:
            await tab._cdp.send(
                "Fetch.continueWithAuth",
                {
                    "requestId": params["requestId"],
                    "authChallengeResponse": {
                        "response": "ProvideCredentials",
                        "username": user,
                        "password": pwd,
                    },
                },
                session_id=tab.session_id,
            )
        except Exception:
            logger.exception("proxy auth: continueWithAuth failed")

    async def _on_request_paused(params: dict[str, object]) -> None:
        # Paired with each auth-required request; just let it through.
        try:
            await tab._cdp.send(
                "Fetch.continueRequest",
                {"requestId": params["requestId"]},
                session_id=tab.session_id,
            )
        except Exception:
            pass  # request may already have been resolved by the auth callback

    tab._cdp.on("Fetch.authRequired", _on_auth_required, session_id=tab.session_id)
    tab._cdp.on("Fetch.requestPaused", _on_request_paused, session_id=tab.session_id)
