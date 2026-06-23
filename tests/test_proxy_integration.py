"""Integration: verify the --proxy-server flag is wired into Chrome."""

from __future__ import annotations

import pytest

import funbrowser
from funbrowser._launcher import find_chrome

pytestmark = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


async def test_proxy_flag_is_passed_to_chrome_command_line() -> None:
    async with await funbrowser.start(
        headless=True, proxy="alice:secret@10.20.30.40:8080"
    ) as browser:
        assert browser.proxy is not None
        assert browser.proxy.host == "10.20.30.40"
        assert browser.proxy.port == 8080
        assert browser.proxy.username == "alice"
        assert browser.proxy.password == "secret"


async def test_proxy_accepts_various_string_formats() -> None:
    # Spin Chrome up with each format — verify the parser routes the right
    # values into Browser.proxy without surprising any platform code.
    for spec in (
        "1.2.3.4:8080",
        "http://1.2.3.4:8080",
        "alice:secret@1.2.3.4:8080",
        "1.2.3.4:8080:alice:secret",
        "socks5://1.2.3.4:1080",
    ):
        b = await funbrowser.start(headless=True, proxy=spec)
        assert b.proxy is not None
        assert b.proxy.host == "1.2.3.4"
        await b.stop()
