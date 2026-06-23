"""Auto-solve example: open a Turnstile-protected page, captcha solves itself.

Requires a funsolver.com API key. Set it via FUNBROWSER_API_KEY or edit below.

    FUNBROWSER_API_KEY=fs_xxx uv run python examples/auto_solve.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import funbrowser

# A public Turnstile demo page. Replace with the site you're targeting.
DEMO_URL = "https://nopecha.com/demo/turnstile"


async def main() -> None:
    api_key = os.environ.get("FUNBROWSER_API_KEY")
    if not api_key:
        print("Set FUNBROWSER_API_KEY first.", file=sys.stderr)
        sys.exit(1)

    async with await funbrowser.start(api_key=api_key) as browser:
        tab = await browser.get(DEMO_URL)
        # Give the detector + funsolver round-trip time to land.
        await asyncio.sleep(30)
        token = await tab.evaluate(
            "document.querySelector('[name=\"cf-turnstile-response\"]')?.value || null"
        )
        print(f"token = {token!r}")


if __name__ == "__main__":
    asyncio.run(main())
