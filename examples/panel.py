"""Run a BrowserPool with the web panel attached.

    pip install funbrowser[panel]   # or: uv add aiohttp
    uv run python examples/panel.py

Then open http://127.0.0.1:8765 in another browser. The dashboard
shows pool stats, the current state of each browser, and lets you
navigate any of them to a URL or grab a screenshot.

Press Ctrl-C in the terminal to stop.
"""

from __future__ import annotations

import asyncio

import funbrowser
from funbrowser import BrowserPool, Panel


async def main() -> None:
    async with BrowserPool(size=3, headless=True) as pool:
        # Pre-warm two browsers so the panel has something to show on load.
        async def warm(b: funbrowser.Browser) -> None:
            await b.get("https://example.com")

        await pool.run_all([warm, warm])

        async with Panel(pool) as panel:
            print(f"Panel: {panel.url}")
            print("Ctrl-C to stop.")
            # Block until interrupted — Event.wait() never resolves on its own.
            stop = asyncio.Event()
            try:
                await stop.wait()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
