"""M5 hardening: real input events, retries, multi-tab concurrency."""

from __future__ import annotations

import asyncio

import pytest

import funbrowser
from funbrowser._launcher import find_chrome

pytestmark = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


async def test_click_uses_real_input_events() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        # Set up a button that records the event it received.
        await tab.evaluate(
            "(() => {"
            "  const b = document.createElement('button');"
            "  b.id = 'fb-test-btn';"
            "  b.textContent = 'click me';"
            "  b.style.cssText = 'position:fixed;left:10px;top:10px;width:100px;height:30px;';"
            "  window.__lastEvent = null;"
            "  b.addEventListener('click', (e) => {"
            "    window.__lastEvent = { isTrusted: e.isTrusted, type: e.type };"
            "  });"
            "  document.body.appendChild(b);"
            "})()"
        )
        await tab.click("#fb-test-btn")
        info = await tab.evaluate("window.__lastEvent")
        assert info is not None
        assert info["type"] == "click"
        # Real CDP-dispatched events ARE trusted; JS .click() would be false.
        assert info["isTrusted"] is True


async def test_click_on_missing_element_raises() -> None:
    """Click auto-waits up to timeout; missing element times out."""
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        with pytest.raises(TimeoutError):
            await tab.click("#does-not-exist", timeout=0.5)


async def test_goto_retries_on_timeout() -> None:
    """retries=N causes _goto_once to be called N+1 times on consistent timeout."""
    from unittest.mock import AsyncMock, patch

    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.new_tab()
        with patch.object(
            tab, "_goto_once", AsyncMock(side_effect=TimeoutError("nope"))
        ) as mock_goto:
            with pytest.raises(TimeoutError):
                await tab.goto("https://x", timeout=1.0, retries=2)
            assert mock_goto.call_count == 3  # initial + 2 retries


async def test_goto_succeeds_after_one_retry() -> None:
    """retries stops as soon as a goto_once succeeds."""
    from unittest.mock import AsyncMock, patch

    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.new_tab()
        mock = AsyncMock(side_effect=[TimeoutError(), None])
        with patch.object(tab, "_goto_once", mock):
            await tab.goto("https://x", timeout=1.0, retries=3)
        assert mock.call_count == 2


async def test_multi_tab_concurrent() -> None:
    """Open many tabs at once — no leaks, no cross-talk."""
    async with await funbrowser.start(headless=True) as browser:
        tabs = await asyncio.gather(*[browser.get("https://example.com") for _ in range(8)])
        assert len(tabs) == 8
        titles = await asyncio.gather(*[t.evaluate("document.title") for t in tabs])
        assert all(title == "Example Domain" for title in titles)
        assert len(browser.tabs) == 8


async def test_stealth_applies_to_iframes() -> None:
    """addScriptToEvaluateOnNewDocument runs in iframes too — chrome.runtime,
    navigator.webdriver should all be patched inside iframes."""
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        # Inject an iframe; check that the patches landed inside it.
        info = await tab.evaluate(
            "new Promise((resolve) => {"
            "  const f = document.createElement('iframe');"
            "  f.src = 'about:blank';"
            "  f.onload = () => {"
            "    const w = f.contentWindow;"
            "    resolve({"
            "      webdriverIsUndefined: w.navigator.webdriver === undefined,"
            "      hasChromeRuntime: typeof w.chrome?.runtime === 'object',"
            "      plugins: w.navigator.plugins.length,"
            "    });"
            "  };"
            "  document.body.appendChild(f);"
            "})"
        )
        assert info["webdriverIsUndefined"] is True
        assert info["hasChromeRuntime"] is True
        assert info["plugins"] >= 3
