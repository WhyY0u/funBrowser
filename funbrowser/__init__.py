"""FunBrowser — undetect browser with built-in captcha solving via funsolver.com."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ._errors import (
    BrowserLaunchError,
    BrowserNotFoundError,
    CDPConnectionClosed,
    CDPError,
    FunBrowserError,
    TargetClosed,
)
from .browser import Browser
from .tab import Tab

__version__ = "0.0.1"

__all__ = [
    "Browser",
    "BrowserLaunchError",
    "BrowserNotFoundError",
    "CDPConnectionClosed",
    "CDPError",
    "FunBrowserError",
    "Tab",
    "TargetClosed",
    "__version__",
    "start",
]


async def start(
    *,
    executable: str | Path | None = None,
    user_data_dir: str | Path | None = None,
    headless: bool = False,
    args: Sequence[str] = (),
) -> Browser:
    """Launch Chrome and return a connected Browser."""
    return await Browser.start(
        executable=executable,
        user_data_dir=user_data_dir,
        headless=headless,
        args=args,
    )
