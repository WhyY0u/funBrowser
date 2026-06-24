"""FunBrowser — undetect browser with built-in captcha solving via funsolver.com."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from . import humanly as humanly_mod
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
from .tab import Tab

humanly = humanly_mod
tls = tls_mod

__version__ = "0.1.0"

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
    "Panel",
    "Profile",
    "Proxy",
    "ProxyParseError",
    "Tab",
    "TargetClosed",
    "__version__",
    "humanly",
    "lookup_proxy_geo",
    "parse_proxy",
    "presets",
    "start",
    "tls",
]


async def start(
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
    api_key: str | None = None,
    auto_solve: bool = True,
    solver_base_url: str | None = None,
    args: Sequence[str] = (),
) -> Browser:
    """Launch Chrome and return a connected Browser.

    ``proxy`` accepts any string format common in proxy lists — see
    :mod:`funbrowser.proxy` for the full list — or a pre-built
    :class:`Proxy`. HTTP/HTTPS auth is handled automatically via CDP;
    SOCKS auth is not (front with a local HTTP proxy).

    Pass ``fingerprint=`` (a :class:`Fingerprint` or a value from
    :mod:`funbrowser.presets`) to override the JS-visible identity values
    (UA, platform, languages, CPU cores, screen, WebGL strings, etc.).

    If ``api_key`` is provided and ``auto_solve`` is true, captchas
    detected on each tab will be sent to funsolver.com and solved
    automatically.
    """
    return await Browser.start(
        executable=executable,
        user_data_dir=user_data_dir,
        headless=headless,
        stealth=stealth,
        fingerprint=fingerprint,
        proxy=proxy,
        geo_autoconfigure=geo_autoconfigure,
        humanly=humanly,
        mini=mini,
        api_key=api_key,
        auto_solve=auto_solve,
        solver_base_url=solver_base_url,
        args=args,
    )
