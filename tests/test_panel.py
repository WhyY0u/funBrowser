"""Web panel — HTTP endpoints + integration on a real BrowserPool."""

from __future__ import annotations

import socket

import httpx
import pytest

from funbrowser import BrowserPool
from funbrowser._launcher import find_chrome
from funbrowser.panel import Panel

pytestmark = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def test_index_returns_html() -> None:
    pool = BrowserPool(size=1, headless=True)
    panel = Panel(pool, port=_free_port())
    async with panel:
        async with httpx.AsyncClient() as client:
            r = await client.get(panel.url)
            assert r.status_code == 200
            assert "text/html" in r.headers["content-type"]
            assert "FunBrowser" in r.text
            assert "Browser Fleet" in r.text
    await pool.stop()


async def test_api_state_reflects_empty_pool() -> None:
    pool = BrowserPool(size=3, headless=True)
    panel = Panel(pool, port=_free_port())
    async with panel:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{panel.url}/api/state")
            assert r.status_code == 200
            data = r.json()
            assert data["pool"]["size"] == 3
            assert data["pool"]["created"] == 0
            assert data["browsers"] == []
    await pool.stop()


async def test_api_state_after_acquire() -> None:
    pool = BrowserPool(size=2, headless=True)
    panel = Panel(pool, port=_free_port())
    async with panel:
        async with pool.acquire() as b:
            await b.get("https://example.com")
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{panel.url}/api/state")
                data = r.json()
                assert data["pool"]["created"] == 1
                assert len(data["browsers"]) == 1
                assert len(data["browsers"][0]["tabs"]) == 1
                assert "example.com" in data["browsers"][0]["tabs"][0]["url"]
    await pool.stop()


async def test_api_goto_drives_an_existing_browser() -> None:
    pool = BrowserPool(size=1, headless=True)
    panel = Panel(pool, port=_free_port())
    async with panel:
        # Force a browser to spawn first.
        async with pool.acquire():
            pass
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{panel.url}/api/browser/0/goto",
                json={"url": "https://example.com"},
            )
            assert r.status_code == 200
            assert r.json()["ok"] is True
    await pool.stop()


async def test_api_goto_404_for_unknown_browser() -> None:
    pool = BrowserPool(size=1, headless=True)
    panel = Panel(pool, port=_free_port())
    async with panel:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{panel.url}/api/browser/99/goto",
                json={"url": "https://example.com"},
            )
            assert r.status_code == 404
    await pool.stop()


async def test_api_screenshot_returns_png() -> None:
    pool = BrowserPool(size=1, headless=True)
    panel = Panel(pool, port=_free_port())
    async with panel:
        async with pool.acquire() as b:
            await b.get("https://example.com")
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{panel.url}/api/browser/0/screenshot")
            assert r.status_code == 200
            assert r.headers["content-type"] == "image/png"
            assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    await pool.stop()
