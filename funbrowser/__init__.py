"""FunBrowser — undetect browser with built-in captcha solving via funsolver.com."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import helpers as helpers_mod
from . import humanly as humanly_mod
from . import mail as mail_mod
from . import tls as tls_mod
from ._errors import (
    BrowserLaunchError,
    BrowserNotFoundError,
    CDPConnectionClosed,
    CDPError,
    FunBrowserError,
    TargetClosed,
)
from .browser import Browser
from .context import BrowserContext
from .context_pool import ContextPool
from .element import ElementHandle
from .fingerprint import Fingerprint, presets
from .geo import GeoInfo, lookup_proxy_geo
from .humanly import HumanBehavior
from .mail import IMAPMail, MailMessage
from .pool import BrowserPool

# Panel is optional — only available when aiohttp is installed.
try:
    from .panel import Panel
except ImportError:
    Panel = None  # type: ignore[assignment, misc]
from .profile import Profile
from .proxy import Proxy, ProxyParseError
from .proxy import parse as parse_proxy
from .solver import FunSolverClient, FunSolverError
from .tab import Response, Tab

helpers = helpers_mod
humanly = humanly_mod
mail = mail_mod
tls = tls_mod

__version__ = "0.1.24"

__all__ = [
    "Browser",
    "BrowserContext",
    "BrowserLaunchError",
    "BrowserNotFoundError",
    "BrowserPool",
    "CDPConnectionClosed",
    "CDPError",
    "ContextPool",
    "ElementHandle",
    "Fingerprint",
    "FunBrowserError",
    "FunSolverClient",
    "FunSolverError",
    "GeoInfo",
    "HumanBehavior",
    "IMAPMail",
    "MailMessage",
    "Panel",
    "Profile",
    "Proxy",
    "ProxyParseError",
    "Response",
    "Tab",
    "TargetClosed",
    "__version__",
    "helpers",
    "humanly",
    "lookup_proxy_geo",
    "mail",
    "parse_proxy",
    "presets",
    "start",
    "tls",
    "wait_forever",
]


async def wait_forever() -> None:
    """Block until cancelled / KeyboardInterrupt. Idiomatic
    "keep the browser open" for scripts that hand control to a human.

    ::

        async with funbrowser.start(headless=False) as browser:
            await browser.get("https://target.com/login")
            print("log in manually, Ctrl-C when done")
            await funbrowser.wait_forever()
    """
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


class _Starting:
    """Return value of :func:`funbrowser.start`. Dual-purpose:

    - ``async with funbrowser.start(...) as browser:`` — preferred,
      starts on enter, stops on exit.
    - ``browser = await funbrowser.start(...)`` — legacy single-shot;
      you call ``await browser.stop()`` yourself later.

    Both end up handing you the same :class:`Browser` instance.
    """

    __slots__ = ("_browser", "_kwargs")

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs
        self._browser: Browser | None = None

    def __await__(self) -> Any:
        return Browser.start(**self._kwargs).__await__()

    async def __aenter__(self) -> Browser:
        self._browser = await Browser.start(**self._kwargs)
        return self._browser

    async def __aexit__(self, *exc: object) -> None:
        if self._browser is not None:
            await self._browser.stop()
            self._browser = None


def start(
    *,
    executable: str | Path | None = None,
    user_data_dir: str | Path | None = None,
    headless: bool = False,
    stealth: bool = True,
    fingerprint: Fingerprint | None = None,
    proxy: str | Proxy | None = None,
    geo_autoconfigure: bool = True,
    humanly: bool | HumanBehavior = False,
    mini: bool = False,
    nano: bool = False,
    api_key: str | None = None,
    auto_solve: bool = True,
    solver_base_url: str | None = None,
    args: Sequence[str] = (),
) -> _Starting:
    """Launch Chrome with stealth + optional captcha solver + optional proxy.

    Use as an async-context-manager (preferred)::

        async with funbrowser.start(headless=True) as browser:
            tab = await browser.get("https://example.com")
            ...

    Or as an awaitable (legacy)::

        browser = await funbrowser.start(headless=True)
        ...
        await browser.stop()

    ``proxy`` accepts any string format common in proxy lists — see
    :mod:`funbrowser.proxy` — or a pre-built :class:`Proxy`. HTTP/HTTPS
    auth is handled automatically via CDP; SOCKS auth is not (front with
    a local HTTP proxy).

    Pass ``fingerprint=`` (a :class:`Fingerprint` or a value from
    :mod:`funbrowser.presets`) to override the JS-visible identity
    (UA, platform, languages, CPU cores, screen, WebGL strings, ...).

    If ``api_key`` is provided and ``auto_solve`` is true, captchas
    detected on each tab will be sent to funsolver.com and solved
    automatically.
    """
    return _Starting(
        executable=executable,
        user_data_dir=user_data_dir,
        headless=headless,
        stealth=stealth,
        fingerprint=fingerprint,
        proxy=proxy,
        geo_autoconfigure=geo_autoconfigure,
        humanly=humanly,
        mini=mini,
        nano=nano,
        api_key=api_key,
        auto_solve=auto_solve,
        solver_base_url=solver_base_url,
        args=args,
    )
