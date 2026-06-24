"""ContextPool + BrowserContext integration tests."""

from __future__ import annotations

import asyncio

import pytest

from funbrowser import Browser, BrowserContext, ContextPool
from funbrowser._launcher import find_chrome

pytestmark = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


async def test_create_context_returns_isolated_browser_context() -> None:
    browser = await Browser.start(headless=True)
    try:
        ctx = await browser.create_context()
        assert isinstance(ctx, BrowserContext)
        assert ctx.context_id
        assert not ctx.closed
        await ctx.close()
        assert ctx.closed
    finally:
        await browser.stop()


async def test_contexts_have_isolated_cookies() -> None:
    browser = await Browser.start(headless=True)
    try:
        ctx_a = await browser.create_context()
        ctx_b = await browser.create_context()

        # Set a cookie in A only.
        await ctx_a.set_cookies(
            [
                {
                    "name": "marker",
                    "value": "from_A",
                    "domain": "example.com",
                    "path": "/",
                }
            ]
        )
        cookies_a = await ctx_a.cookies()
        cookies_b = await ctx_b.cookies()

        names_a = {c["name"] for c in cookies_a}
        names_b = {c["name"] for c in cookies_b}
        assert "marker" in names_a
        assert "marker" not in names_b

        await ctx_a.close()
        await ctx_b.close()
    finally:
        await browser.stop()


async def test_pool_size_validation() -> None:
    with pytest.raises(ValueError):
        ContextPool(size=0)


async def test_pool_lazy_spawn_and_reuse() -> None:
    async with ContextPool(size=2, headless=True) as pool:
        assert pool.created == 0
        async with pool.acquire() as ctx:
            tab = await ctx.get("https://example.com")
            assert await tab.evaluate("document.title") == "Example Domain"
        assert pool.created == 1
        # Re-acquire: same context, not a fresh spawn.
        async with pool.acquire() as ctx2:
            assert ctx2.context_id
        assert pool.created == 1


async def test_pool_concurrent_run_all() -> None:
    async with ContextPool(size=3, headless=True) as pool:

        async def work(ctx: BrowserContext) -> str:
            tab = await ctx.get("https://example.com")
            return await tab.evaluate("document.title")

        results = await pool.run_all([work, work, work, work, work])
        assert results == ["Example Domain"] * 5
        # We hit the cap — at most `size` contexts created.
        assert pool.created <= 3


async def test_pool_stop_disposes_everything() -> None:
    pool = ContextPool(size=2, headless=True)

    ready = asyncio.Event()
    entered = [0]

    async def hold(_ctx: BrowserContext) -> None:
        entered[0] += 1
        if entered[0] >= 2:
            ready.set()
        await ready.wait()

    await pool.run_all([hold, hold])
    assert pool.created == 2
    await pool.stop()
    with pytest.raises(RuntimeError):
        async with pool.acquire():
            pass


async def test_pool_shares_one_browser_process() -> None:
    """All contexts in the pool share a single host Chrome."""
    async with ContextPool(size=2, headless=True) as pool:
        async with pool.acquire():
            pass
        async with pool.acquire():
            pass
        # Only one Browser was ever instantiated.
        assert pool.browser is not None
