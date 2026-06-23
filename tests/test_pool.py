"""BrowserPool — concurrent farm with lazy spawn and round-robin proxies."""

from __future__ import annotations

import asyncio

import pytest

from funbrowser import BrowserPool
from funbrowser._launcher import find_chrome

pytestmark = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


async def test_size_must_be_positive() -> None:
    with pytest.raises(ValueError):
        BrowserPool(size=0)


async def test_browsers_spawn_lazily_on_first_acquire() -> None:
    async with BrowserPool(size=3, headless=True) as pool:
        assert pool.created == 0
        async with pool.acquire():
            assert pool.created == 1
            assert pool.busy == 1
            assert pool.idle == 0


async def test_acquire_release_reuses_browser() -> None:
    async with BrowserPool(size=1, headless=True) as pool:
        async with pool.acquire() as b1:
            id1 = id(b1)
        # Re-acquire: same instance, not a fresh spawn.
        async with pool.acquire() as b2:
            assert id(b2) == id1
        assert pool.created == 1


async def test_concurrent_acquires_share_pool() -> None:
    """3 tasks, pool size 2 → 2 run in parallel, 3rd queues."""
    async with BrowserPool(size=2, headless=True) as pool:

        async def work(b):
            tab = await b.get("https://example.com")
            return await tab.evaluate("document.title")

        results = await pool.run_all([work] * 3)
        assert results == ["Example Domain"] * 3
        assert pool.created == 2  # never grew past size


async def test_run_dispatches_single_task() -> None:
    async with BrowserPool(size=1, headless=True) as pool:

        async def work(b):
            tab = await b.get("https://example.com")
            return await tab.evaluate("document.title")

        title = await pool.run(work)
        assert title == "Example Domain"


async def test_stop_closes_all_browsers() -> None:
    pool = BrowserPool(size=2, headless=True)

    # Force both slots to spawn by holding both concurrently.
    ready = asyncio.Event()
    entered = [0]

    async def hold(_b):
        entered[0] += 1
        if entered[0] >= 2:
            ready.set()
        await ready.wait()

    await pool.run_all([hold, hold])
    assert pool.created == 2
    await pool.stop()
    # Acquiring on a closed pool raises.
    with pytest.raises(RuntimeError):
        async with pool.acquire():
            pass


async def test_proxies_are_assigned_round_robin() -> None:
    """Each created browser picks the next proxy from the list."""
    async with BrowserPool(
        size=3,
        headless=True,
        proxies=[
            "1.2.3.4:8080",
            "5.6.7.8:8080",
            "9.10.11.12:8080",
        ],
        # don't actually try a geo lookup against a fake proxy
        geo_autoconfigure=False,
    ) as pool:
        # nested acquires force three concurrent slots → three spawns
        async with pool.acquire():
            async with pool.acquire():
                async with pool.acquire():
                    pass
        hosts = [b.proxy.host for b in pool.browsers if b.proxy is not None]
        assert hosts == ["1.2.3.4", "5.6.7.8", "9.10.11.12"]


async def test_fourth_browser_with_2_proxies_wraps_back() -> None:
    async with BrowserPool(
        size=4,
        headless=True,
        proxies=["1.2.3.4:8080", "5.6.7.8:8080"],
        geo_autoconfigure=False,
    ) as pool:
        # Force 4 slots to spawn by holding all 4 concurrently.
        ready = asyncio.Event()
        entered = [0]

        async def hold(_b):
            entered[0] += 1
            if entered[0] >= 4:
                ready.set()
            await ready.wait()

        await pool.run_all([hold] * 4)
        hosts = [b.proxy.host for b in pool.browsers if b.proxy is not None]
        assert hosts == ["1.2.3.4", "5.6.7.8", "1.2.3.4", "5.6.7.8"]


async def test_proxies_assigned_three_distinct_when_three_browsers_spawn() -> None:
    """Replaces the prior 'round-robin with 3 proxies' test — we now force all
    3 slots to spawn before any release, so the proxy list is consumed."""
    async with BrowserPool(
        size=3,
        headless=True,
        proxies=["1.2.3.4:8080", "5.6.7.8:8080", "9.10.11.12:8080"],
        geo_autoconfigure=False,
    ) as pool:
        ready = asyncio.Event()
        entered = [0]

        async def hold(_b):
            entered[0] += 1
            if entered[0] >= 3:
                ready.set()
            await ready.wait()

        await pool.run_all([hold] * 3)
        hosts = [b.proxy.host for b in pool.browsers if b.proxy is not None]
        assert sorted(hosts) == sorted(["1.2.3.4", "5.6.7.8", "9.10.11.12"])
