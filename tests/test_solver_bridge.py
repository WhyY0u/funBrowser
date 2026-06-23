"""Integration test that the solver bridge installs on a real Tab."""

from __future__ import annotations

import pytest

import funbrowser
from funbrowser._launcher import find_chrome

pytestmark = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


async def test_solver_globals_installed_when_api_key_provided() -> None:
    async with await funbrowser.start(
        headless=True, api_key="test_key_for_install_only"
    ) as browser:
        tab = await browser.get("https://example.com")
        has_obj = await tab.evaluate("typeof window.__funbrowser === 'object'")
        has_solve = await tab.evaluate("typeof window.__funbrowser_solve === 'function'")
        has_resolve = await tab.evaluate("typeof window.__funbrowser_resolve === 'function'")
        assert has_obj is True
        assert has_solve is True
        assert has_resolve is True


async def test_no_solver_globals_without_api_key() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        has_obj = await tab.evaluate("typeof window.__funbrowser")
        assert has_obj == "undefined"
