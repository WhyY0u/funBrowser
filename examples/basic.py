"""Minimal M1 example: launch Chrome, navigate, evaluate JS, screenshot.

Run with:
    uv run python examples/basic.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import funbrowser


async def main() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        title = await tab.evaluate("document.title")
        ua = await tab.evaluate("navigator.userAgent")
        print(f"title    = {title}")
        print(f"ua       = {ua}")
        print(f"has h1   = {await tab.query_selector('h1')}")

        out = Path("example.png").absolute()
        png = await tab.screenshot()
        await asyncio.to_thread(out.write_bytes, png)
        print(f"saved    = {out}")


if __name__ == "__main__":
    asyncio.run(main())
