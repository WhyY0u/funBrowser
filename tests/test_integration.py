"""End-to-end smoke test exercising M1 exit criteria.

Skipped automatically if no Chrome/Chromium binary is available.
"""

from __future__ import annotations

import pytest

import funbrowser
from funbrowser._launcher import find_chrome

pytestmark = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


async def test_get_returns_tab_and_evaluate_returns_html_title() -> None:
    browser = await funbrowser.start(headless=True)
    async with browser:
        tab = await browser.get("https://example.com")
        title = await tab.evaluate("document.title")
        assert title == "Example Domain"


async def test_screenshot_returns_png_bytes() -> None:
    browser = await funbrowser.start(headless=True)
    async with browser:
        tab = await browser.get("https://example.com")
        png = await tab.screenshot()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


async def test_query_selector_and_click() -> None:
    browser = await funbrowser.start(headless=True)
    async with browser:
        tab = await browser.get("https://example.com")
        assert await tab.exists("h1") is True
        assert await tab.exists("h2") is False
