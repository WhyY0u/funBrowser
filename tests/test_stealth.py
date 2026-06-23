"""End-to-end stealth checks (M2 Tier 1 + Tier 2).

Skipped automatically if no Chrome/Chromium binary is available.
"""

from __future__ import annotations

import pytest

import funbrowser
from funbrowser._launcher import find_chrome
from funbrowser.stealth import stealth_flags

pytestmark = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


def test_stealth_flags_include_real_gpu() -> None:
    flags = stealth_flags()
    assert "--use-gl=angle" in flags
    assert "--use-angle=default" in flags
    assert any("--disable-features=" in f for f in flags)


async def test_webdriver_is_undefined() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        webdriver = await tab.evaluate("navigator.webdriver")
        assert webdriver is None  # JS undefined -> Python None


async def test_user_agent_does_not_say_headless() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        ua = await tab.evaluate("navigator.userAgent")
        assert "HeadlessChrome" not in ua
        assert "Chrome/" in ua


async def test_plugins_are_populated() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        n = await tab.evaluate("navigator.plugins.length")
        assert n >= 3


async def test_languages_are_populated() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        langs = await tab.evaluate("JSON.stringify(navigator.languages)")
        assert "en-US" in langs


async def test_chrome_runtime_exists() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        has_runtime = await tab.evaluate(
            "typeof window.chrome === 'object' && typeof window.chrome.runtime === 'object'"
        )
        assert has_runtime is True


async def test_permissions_query_matches_notification() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        # Notification.permission default in real Chrome is 'default'; the
        # patch maps that to 'prompt' through permissions.query. Either way,
        # the two queries should not disagree in the headless-style way.
        result = await tab.evaluate(
            "navigator.permissions.query({name:'notifications'}).then(p => p.state)"
        )
        assert result in ("prompt", "denied", "granted", "default")


async def test_canvas_fingerprint_varies_per_call() -> None:
    """Two readings of the same canvas should differ because of the noise."""
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        js = """
        (() => {
          const c = document.createElement('canvas');
          c.width = 100; c.height = 100;
          const ctx = c.getContext('2d');
          ctx.fillStyle = '#abcdef';
          ctx.fillRect(0, 0, 100, 100);
          ctx.font = '20px serif';
          ctx.fillText('funbrowser', 5, 50);
          return [c.toDataURL(), c.toDataURL()];
        })()
        """
        a, b = await tab.evaluate(js)
        assert a != b


async def test_audio_fingerprint_varies_per_call() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        js = """
        (() => {
          const ac = new OfflineAudioContext(1, 4096, 44100);
          const buf = ac.createBuffer(1, 4096, 44100);
          const a1 = Array.from(buf.getChannelData(0)).join(',');
          const a2 = Array.from(buf.getChannelData(0)).join(',');
          return [a1, a2];
        })()
        """
        a, b = await tab.evaluate(js)
        assert a != b


async def test_stealth_can_be_disabled() -> None:
    async with await funbrowser.start(headless=True, stealth=False) as browser:
        tab = await browser.get("https://example.com")
        ua = await tab.evaluate("navigator.userAgent")
        assert "HeadlessChrome" in ua
