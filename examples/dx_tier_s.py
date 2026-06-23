"""Tier-S developer experience tour: waits, ElementHandle, fill/type, cookies.

uv run python examples/dx_tier_s.py
"""

from __future__ import annotations

import asyncio

import funbrowser


async def main() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get(
            "data:text/html,"
            "<html><body>"
            "<h1>Demo</h1>"
            "<form>"
            "<input id='email' type='email' placeholder='you@example.com'>"
            "<input id='name' type='text' placeholder='name'>"
            "<button type='button' id='go'>Submit</button>"
            "</form>"
            "<div id='result'></div>"
            "<script>"
            "document.getElementById('go').addEventListener('click', () => {"
            " document.getElementById('result').innerText ="
            "   'hi ' + document.getElementById('name').value +"
            "   ' at ' + document.getElementById('email').value;"
            "});"
            "</script>"
            "</body></html>"
        )

        # Auto-wait + fill (faster than type, fires input + change events)
        await tab.fill("#email", "ada@lovelace.dev")

        # Real keystrokes (use when per-key handlers matter)
        await tab.type("#name", "Ada")

        # Click via real Input.dispatchMouseEvent (event.isTrusted == true)
        await tab.click("#go")

        # Read text back
        msg = await tab.text("#result")
        print("result =", msg)

        # ElementHandle: get a handle, reuse it
        email_input = await tab.find("#email")
        print("email value =", await email_input.value())
        print("email class =", await email_input.attribute("class"))

        # Cookies — browser-wide
        await browser.set_cookies(
            [
                {
                    "name": "session",
                    "value": "abc123",
                    "domain": "example.com",
                    "path": "/",
                }
            ]
        )
        cookies = await browser.cookies()
        print("cookies =", [c["name"] for c in cookies])


if __name__ == "__main__":
    asyncio.run(main())
