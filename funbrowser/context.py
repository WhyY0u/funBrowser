"""BrowserContext — an isolated browsing context inside a shared Browser.

CDP exposes ``Target.createBrowserContext`` which carves a fresh, isolated
browsing identity out of an existing Chrome process: separate cookies,
localStorage, IndexedDB, cache, and (optionally) its own proxy. Each
context behaves like its own browser to the page running inside, but a
single Chrome process serves any number of them.

For farm operators who would otherwise spawn 10-50 standalone Chrome
processes, switching to one Chrome + N contexts cuts memory roughly
**7-10x** (each context adds ~5-15 MB on top of the host process, vs
~150 MB for a fresh Chrome).

Trade-offs vs full :class:`Browser` per slot:

- Crash in the host Chrome takes every context down with it
- All contexts share one process — kernel-level isolation is weaker
- Stealth + fingerprint patches still apply per-tab (each new tab gets
  its own ``Page.addScriptToEvaluateOnNewDocument`` set)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .proxy import Proxy
from .proxy import parse as parse_proxy
from .tab import Tab

if TYPE_CHECKING:
    from .browser import Browser

logger = logging.getLogger(__name__)


class BrowserContext:
    """One isolated browsing identity inside a shared :class:`Browser`."""

    def __init__(
        self,
        browser: Browser,
        context_id: str,
        *,
        proxy: Proxy | None = None,
    ) -> None:
        self._browser = browser
        self._context_id = context_id
        self._proxy = proxy
        self._tabs: dict[str, Tab] = {}
        self._closed = False

    @property
    def browser(self) -> Browser:
        return self._browser

    @property
    def context_id(self) -> str:
        return self._context_id

    @property
    def proxy(self) -> Proxy | None:
        return self._proxy

    @property
    def tabs(self) -> list[Tab]:
        return list(self._tabs.values())

    @property
    def closed(self) -> bool:
        return self._closed

    async def new_tab(self, url: str = "about:blank") -> Tab:
        if self._closed:
            raise RuntimeError("context is closed")
        res = await self._browser._cdp.send(
            "Target.createTarget",
            {"url": url, "browserContextId": self._context_id},
        )
        target_id = res["targetId"]
        attach = await self._browser._cdp.send(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        session_id = attach["sessionId"]
        tab = Tab(self._browser, target_id, session_id)
        await tab._initialize()
        self._tabs[target_id] = tab
        # Also register on the host browser so its tab counters stay accurate.
        self._browser._tabs[target_id] = tab
        return tab

    async def get(self, url: str, *, wait_until: str = "load") -> Tab:
        tab = await self.new_tab()
        await tab.goto(url, wait_until=wait_until)
        return tab

    async def cookies(self) -> list[dict[str, Any]]:
        """Cookies scoped to this context. No interference between contexts."""
        result = await self._browser._cdp.send(
            "Storage.getCookies",
            {"browserContextId": self._context_id},
        )
        return list(result.get("cookies", []))

    async def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        await self._browser._cdp.send(
            "Storage.setCookies",
            {"cookies": list(cookies), "browserContextId": self._context_id},
        )

    async def clear_cookies(self) -> None:
        await self._browser._cdp.send(
            "Storage.clearCookies",
            {"browserContextId": self._context_id},
        )

    async def save_cookies(self, path: str | Path) -> int:
        """Dump this context's cookies to a JSON file. Returns the count saved."""
        import asyncio
        import json as _json

        cookies = await self.cookies()
        p = Path(path)
        await asyncio.to_thread(p.write_text, _json.dumps(cookies, indent=2), encoding="utf-8")
        return len(cookies)

    async def load_cookies(self, path: str | Path, *, clear_first: bool = False) -> int:
        """Load cookies from a JSON file. ``clear_first`` wipes existing."""
        import asyncio
        import json as _json

        p = Path(path)
        raw = await asyncio.to_thread(p.read_text, encoding="utf-8")
        cookies = _json.loads(raw)
        if clear_first:
            await self.clear_cookies()
        await self.set_cookies(cookies)
        return len(cookies)

    async def close(self) -> None:
        """Close every tab in this context, then dispose the context itself."""
        if self._closed:
            return
        self._closed = True
        for tab in list(self._tabs.values()):
            try:
                await tab.close()
            except Exception:
                pass
        self._tabs.clear()
        try:
            await self._browser._cdp.send(
                "Target.disposeBrowserContext",
                {"browserContextId": self._context_id},
            )
        except Exception:
            logger.exception("context: disposeBrowserContext failed for %s", self._context_id)
        self._browser._contexts.discard(self._context_id)

    async def __aenter__(self) -> BrowserContext:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


async def _create_context_on(
    browser: Browser,
    *,
    proxy: str | Proxy | None = None,
    proxy_bypass: list[str] | None = None,
) -> BrowserContext:
    """Internal: create a browser context on a Browser instance."""
    params: dict[str, Any] = {}
    proxy_obj: Proxy | None = None
    if proxy is not None:
        proxy_obj = parse_proxy(proxy)
        params["proxyServer"] = proxy_obj.chrome_arg()
    if proxy_bypass:
        params["proxyBypassList"] = ",".join(proxy_bypass)

    res = await browser._cdp.send("Target.createBrowserContext", params)
    context_id = str(res["browserContextId"])
    browser._contexts.add(context_id)
    return BrowserContext(browser, context_id, proxy=proxy_obj)
