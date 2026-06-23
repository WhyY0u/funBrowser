"""Run a session through a proxy. Accepts any common proxy-string format.

uv run python examples/with_proxy.py 1.2.3.4:8080
uv run python examples/with_proxy.py user:pass@1.2.3.4:8080
uv run python examples/with_proxy.py 1.2.3.4:8080:user:pass
uv run python examples/with_proxy.py socks5://1.2.3.4:1080
"""

from __future__ import annotations

import asyncio
import sys

import funbrowser


async def main(proxy: str) -> None:
    async with await funbrowser.start(headless=True, proxy=proxy) as browser:
        tab = await browser.get("https://api.ipify.org?format=json")
        body = await tab.evaluate("document.body.innerText")
        print("exit IP =", body)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: with_proxy.py <proxy>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
