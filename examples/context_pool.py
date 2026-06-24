"""ContextPool: 1 Chrome process, N isolated browsing contexts.

    uv run python examples/context_pool.py

For the same workload, compare against examples/pool.py (10 Chrome
processes vs 1 + 10 contexts) — the difference in RAM is the point.
"""

from __future__ import annotations

import asyncio
import time

import funbrowser
from funbrowser import BrowserContext, ContextPool


async def scrape_title(ctx: BrowserContext, url: str) -> str:
    tab = await ctx.get(url)
    title = await tab.evaluate("document.title")
    await tab.close()
    return f"{url} -> {title}"


async def main() -> None:
    urls = [
        "https://example.com",
        "https://example.org",
        "https://example.net",
        "https://www.iana.org/help/example-domains",
        "https://example.com/?a=1",
        "https://example.com/?a=2",
        "https://example.com/?a=3",
        "https://example.com/?a=4",
    ]

    tasks = [lambda ctx, u=u: scrape_title(ctx, u) for u in urls]

    t0 = time.monotonic()
    async with ContextPool(size=3, headless=True, mini=True) as pool:
        results = await pool.run_all(tasks)
    elapsed = time.monotonic() - t0

    for r in results:
        print(r)
    print(f"\n{len(urls)} pages through 1 Chrome + {3} isolated contexts in {elapsed:.1f}s")

    _ = funbrowser  # keep the import meaningful even if unused above


if __name__ == "__main__":
    asyncio.run(main())
