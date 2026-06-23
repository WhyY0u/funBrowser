"""Run a BrowserPool with the web panel attached.

    pip install funbrowser[panel]   # or: uv add aiohttp
    uv run python examples/panel.py

Set FUNBROWSER_API_KEY in the environment to wire the funsolver client —
the panel then displays the live balance card and logs each captcha solve.

Open http://127.0.0.1:8765 in any browser after launch. Press Ctrl-C to
stop.
"""

from __future__ import annotations

import asyncio
import os

import funbrowser
from funbrowser import BrowserPool, Panel


async def main() -> None:
    api_key = os.environ.get("FUNBROWSER_API_KEY")
    if api_key:
        print("FunSolver: api key found, balance card will populate")

    async with BrowserPool(
        size=3,
        headless=True,
        mini=True,  # lean Chrome flags — ~50% lower RAM per browser
        api_key=api_key,
    ) as pool:
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
