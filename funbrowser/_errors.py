"""Exceptions raised by funbrowser."""

from __future__ import annotations


class FunBrowserError(Exception):
    """Base class for all funbrowser errors."""


class BrowserNotFoundError(FunBrowserError):
    """No Chrome / Chromium executable could be located."""


class BrowserLaunchError(FunBrowserError):
    """The browser process failed to start or expose a DevTools endpoint."""


class CDPError(FunBrowserError):
    """A CDP command returned an error response."""

    def __init__(self, message: str, *, code: int | None = None, data: object = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


class CDPConnectionClosed(FunBrowserError):
    """The CDP WebSocket connection closed unexpectedly."""


class TargetClosed(FunBrowserError):
    """Operation attempted on a tab whose target has been destroyed."""
