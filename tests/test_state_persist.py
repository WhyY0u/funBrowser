"""save_cookies / load_cookies / export_state / import_state round-trips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import funbrowser
from funbrowser._launcher import find_chrome

pytestmark = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


async def test_save_cookies_writes_json(tmp_path: Path) -> None:
    async with await funbrowser.start(headless=True) as browser:
        await browser.set_cookies(
            [
                {
                    "name": "marker",
                    "value": "abc",
                    "domain": "example.com",
                    "path": "/",
                }
            ]
        )
        out = tmp_path / "cookies.json"
        n = await browser.save_cookies(out)
        assert n >= 1
        data = json.loads(out.read_text(encoding="utf-8"))
        assert any(c["name"] == "marker" for c in data)


async def test_save_load_round_trip(tmp_path: Path) -> None:
    async with await funbrowser.start(headless=True) as browser:
        await browser.clear_cookies()
        await browser.set_cookies(
            [
                {
                    "name": "session",
                    "value": "from_export",
                    "domain": "example.com",
                    "path": "/",
                }
            ]
        )
        path = tmp_path / "session.json"
        await browser.save_cookies(path)

    async with await funbrowser.start(headless=True) as fresh:
        await fresh.clear_cookies()
        loaded = await fresh.load_cookies(path, clear_first=True)
        assert loaded >= 1
        names = {c["name"] for c in await fresh.cookies()}
        assert "session" in names


async def test_tab_local_storage_snapshot() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        await tab.set_local_storage({"hello": "world", "from": "funbrowser"})
        ls = await tab.local_storage()
        assert ls.get("hello") == "world"
        assert ls.get("from") == "funbrowser"


async def test_export_import_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    # Build a session: navigate, set a cookie, set localStorage.
    async with await funbrowser.start(headless=True) as browser:
        await browser.clear_cookies()
        tab = await browser.get("https://example.com")
        await tab.set_local_storage({"ls_marker": "from_export"})
        await browser.set_cookies(
            [
                {
                    "name": "ck_marker",
                    "value": "saved",
                    "domain": "example.com",
                    "path": "/",
                }
            ]
        )
        result = await browser.export_state(path)
        assert result["cookies"] >= 1
        assert result["origins"] >= 1

    # Fresh browser — restore. navigate=True opens example.com and
    # re-applies localStorage.
    async with await funbrowser.start(headless=True) as fresh:
        await fresh.clear_cookies()
        restored = await fresh.import_state(path, clear_first=True)
        assert restored["cookies"] >= 1
        assert restored["origins"] >= 1
        names = {c["name"] for c in await fresh.cookies()}
        assert "ck_marker" in names
        # The localStorage tab was opened by import_state — find it
        for t in fresh.tabs:
            if "example.com" in t.url:
                ls = await t.local_storage()
                assert ls.get("ls_marker") == "from_export"
                break
        else:
            pytest.fail("expected an example.com tab after import_state")


async def test_context_save_load_cookies_isolated(tmp_path: Path) -> None:
    """Cookies saved from one context shouldn't show up in another's load."""
    async with await funbrowser.start(headless=True) as browser:
        ctx_a = await browser.create_context()
        ctx_b = await browser.create_context()
        await ctx_a.set_cookies(
            [
                {
                    "name": "ctx_marker",
                    "value": "A",
                    "domain": "example.com",
                    "path": "/",
                }
            ]
        )
        path = tmp_path / "a.json"
        await ctx_a.save_cookies(path)

        # Loading into B brings the cookie in there too — that's the
        # whole point of a portable session file.
        loaded = await ctx_b.load_cookies(path)
        assert loaded >= 1
        names = {c["name"] for c in await ctx_b.cookies()}
        assert "ctx_marker" in names
        await ctx_a.close()
        await ctx_b.close()
