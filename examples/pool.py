"""BrowserPool: a fleet of browsers with bounded concurrency.

uv run python examples/pool.py
"""

from __future__ import annotations

import asyncio
import time

import funbrowser
from funbrowser import BrowserPool


async def fetch_title(url: str):
    async def task(browser: funbrowser.Browser) -> str:
        tab = await browser.get(url)
        title = await tab.evaluate("document.title")
        await tab.close()
        return f"{url} -> {title}"

    return task


async def main() -> None:
    urls = [
        "https://example.com",
        "https://example.org",
        "https://example.net",
        "https://www.iana.org/help/example-domains",
        "https://example.com/?q=1",
        "https://example.com/?q=2",
        "https://example.com/?q=3",
        "https://example.com/?q=4",
    ]

    tasks = [await fetch_title(u) for u in urls]

    t0 = time.monotonic()
    async with BrowserPool(size=3, headless=True) as pool:
        results = await pool.run_all(tasks)
    elapsed = time.monotonic() - t0

    for r in results:
        print(r)
    print(f"\n{len(urls)} pages through pool of 3 in {elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
