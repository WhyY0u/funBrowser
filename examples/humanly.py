"""Humanly mode: realistic mouse + keyboard timing for clicks and typing.

uv run python examples/humanly.py
"""

from __future__ import annotations

import asyncio
import time

import funbrowser
from funbrowser import HumanBehavior, humanly

PAGE = "data:text/html," + (
    "<html><body style='font-family:sans-serif'>"
    "<h1>Humanly demo</h1>"
    "<button id='b' style='margin:120px 0 0 220px;padding:8px 20px;'>Click me</button>"
    "<form style='margin-top:30px'>"
    "<input id='name' placeholder='your name' style='padding:6px'>"
    "</form>"
    "<div id='out'></div>"
    "<script>"
    "window.__moves = 0;"
    "document.addEventListener('mousemove', () => window.__moves++);"
    "document.getElementById('b').onclick = () =>"
    "  document.getElementById('out').innerText = 'clicked at ' + Date.now();"
    "</script>"
    "</body></html>"
)


async def run(label: str, profile: bool | HumanBehavior) -> None:
    print(f"\n--- {label} ---")
    t0 = time.monotonic()
    async with await funbrowser.start(headless=True, humanly=profile) as browser:
        tab = await browser.get(PAGE)
        # Seed a starting cursor so the curve has a "from".
        tab._cursor = (10.0, 10.0)
        await tab.click("#b")
        await tab.type("#name", "Ada Lovelace")
        moves = await tab.evaluate("window.__moves")
        clicked = await tab.text("#out")
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  mouseMoved events  = {moves}")
        print(f"  click result       = {clicked}")
        print(f"  total wall time    = {elapsed:.0f} ms")


async def main() -> None:
    await run("Instant (no humanly)", False)
    await run("FAST profile", humanly.FAST)
    await run("DEFAULT profile", True)
    await run("CAREFUL profile", humanly.CAREFUL)


if __name__ == "__main__":
    asyncio.run(main())
