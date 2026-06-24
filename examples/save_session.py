"""Save a logged-in session and restore it in a fresh browser.

Two paths are demonstrated:

1. Cookies-only — small, fast, works when the target site is cookie-driven.
2. Full state — cookies + localStorage, so SPA-style sites that stash auth
   state in localStorage also restore.

    uv run python examples/save_session.py
"""

from __future__ import annotations

import asyncio

import funbrowser

SESSION_FILE = "session.json"


async def save() -> None:
    """Open a tab, drop a cookie + localStorage entry, persist."""
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        # Pretend we just logged in.
        await tab.set_local_storage({"auth_token": "ey...your.session"})
        await browser.set_cookies(
            [
                {
                    "name": "session",
                    "value": "saved-from-script",
                    "domain": "example.com",
                    "path": "/",
                }
            ]
        )
        result = await browser.export_state(SESSION_FILE)
        print(
            f"  saved {result['cookies']} cookies + {result['origins']} origin(s) to {SESSION_FILE}"
        )


async def restore() -> None:
    """Fresh browser. Restore cookies + localStorage. Confirm they're back."""
    async with await funbrowser.start(headless=True) as browser:
        restored = await browser.import_state(SESSION_FILE, clear_first=True)
        print(f"  restored {restored['cookies']} cookies + {restored['origins']} origin(s)")
        # Find the auto-opened tab and read back.
        for tab in browser.tabs:
            if "example.com" in tab.url:
                ls = await tab.local_storage()
                print(f"  localStorage on {tab.url}: {ls}")
        cookies = await browser.cookies()
        print(f"  cookies in fresh browser: {[c['name'] for c in cookies]}")


async def main() -> None:
    print("--- save ---")
    await save()
    print("--- restore (different browser process) ---")
    await restore()


if __name__ == "__main__":
    asyncio.run(main())
