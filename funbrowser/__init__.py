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
from .solver import FunSolverClient, FunSolverError
from .tab import Tab

__version__ = "0.0.1"

__all__ = [
    "Browser",
    "BrowserLaunchError",
    "BrowserNotFoundError",
    "CDPConnectionClosed",
    "CDPError",
    "FunBrowserError",
    "FunSolverClient",
    "FunSolverError",
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
    stealth: bool = True,
    api_key: str | None = None,
    auto_solve: bool = True,
    solver_base_url: str | None = None,
    args: Sequence[str] = (),
) -> Browser:
    """Launch Chrome and return a connected Browser.

    If ``api_key`` is provided and ``auto_solve`` is true, captchas detected
    on each tab will be sent to funsolver.com and solved automatically.
    """
    return await Browser.start(
        executable=executable,
        user_data_dir=user_data_dir,
        headless=headless,
        stealth=stealth,
        api_key=api_key,
        auto_solve=auto_solve,
        solver_base_url=solver_base_url,
        args=args,
    )
