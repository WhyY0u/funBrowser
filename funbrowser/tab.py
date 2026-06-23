"""Tab — a CDP-attached page target you can drive."""

from __future__ import annotations

import asyncio
import base64
from typing import TYPE_CHECKING, Any

from ._cdp import CDPConnection
from ._errors import TargetClosed

if TYPE_CHECKING:
    from .browser import Browser


class Tab:
    """One browser tab, attached via a flat CDP session."""

    def __init__(self, browser: Browser, target_id: str, session_id: str) -> None:
        self._browser = browser
        self._target_id = target_id
        self._session_id = session_id
        self._cdp: CDPConnection = browser._cdp
        self._closed = False
        self._url = "about:blank"

    @property
    def target_id(self) -> str:
        return self._target_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def url(self) -> str:
        return self._url

    @property
    def closed(self) -> bool:
        return self._closed

    async def _send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._closed:
            raise TargetClosed(f"tab {self._target_id} is closed")
        return await self._cdp.send(method, params, session_id=self._session_id)

    async def _initialize(self) -> None:
        # Page.enable is needed to receive Page.loadEventFired.
        # Runtime.enable is intentionally NOT called here — the solver bridge
        # below calls it only if the user opted into auto-solving, since
        # enabling Runtime is a known minor antibot tell.
        await self._send("Page.enable")
        if self._browser.stealth_enabled:
            from .stealth import apply_stealth

            await apply_stealth(self, self._browser.fingerprint)
        if self._browser.proxy is not None and self._browser.proxy.has_auth:
            from .proxy import attach_auth

            await attach_auth(self, self._browser.proxy)
        if self._browser.auto_solve_enabled:
            from .solver import apply_solver

            client = self._browser.solver_client
            assert client is not None  # auto_solve_enabled implies client present
            await apply_solver(self, client)

    async def goto(
        self,
        url: str,
        *,
        wait_until: str = "load",
        timeout: float = 30.0,
        retries: int = 0,
    ) -> None:
        """Navigate and wait for the page-load event.

        ``retries`` re-attempts the navigation on timeout — useful behind
        flaky proxies or slow targets. Other exceptions (e.g. closed
        target, CDP errors) bubble up immediately.
        """
        last_exc: BaseException | None = None
        for attempt in range(retries + 1):
            try:
                await self._goto_once(url, wait_until=wait_until, timeout=timeout)
                return
            except TimeoutError as exc:
                last_exc = exc
                if attempt >= retries:
                    raise
        if last_exc is not None:
            raise last_exc

    async def _goto_once(
        self,
        url: str,
        *,
        wait_until: str,
        timeout: float,
    ) -> None:
        if wait_until == "load":
            event = "Page.loadEventFired"
        elif wait_until == "domcontentloaded":
            event = "Page.domContentEventFired"
        else:
            raise ValueError(f"Unknown wait_until: {wait_until!r}")

        loaded: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        def _on_event(_params: dict[str, Any]) -> None:
            if not loaded.done():
                loaded.set_result(None)

        unsubscribe = self._cdp.on(event, _on_event, session_id=self._session_id)
        try:
            await self._send("Page.navigate", {"url": url})
            self._url = url
            try:
                async with asyncio.timeout(timeout):
                    await loaded
            except TimeoutError as exc:
                raise TimeoutError(f"Timed out waiting for {event} on {url}") from exc
        finally:
            unsubscribe()

    async def evaluate(self, expression: str) -> Any:
        """Run JS in the tab and return the result by value."""
        result = await self._send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            raise RuntimeError(f"JS exception: {details.get('text', '')}")
        return result.get("result", {}).get("value")

    async def query_selector(self, selector: str) -> bool:
        """Return True if a matching element exists.

        Real element-handle objects with click/text/etc land in M2 alongside
        Input.dispatchMouseEvent.
        """
        return bool(await self.evaluate(f"document.querySelector({selector!r}) !== null"))

    async def click(self, selector: str) -> None:
        """Click via real Input.dispatchMouseEvent at the element's center.

        Generates trusted-looking mouse events rather than a synthetic JS
        ``.click()``, so pages that gate on real input (some captchas, some
        antibots) accept it.
        """
        box = await self.evaluate(
            f"(() => {{ const el = document.querySelector({selector!r});"
            f" if (!el) return null;"
            f" const r = el.getBoundingClientRect();"
            f" if (r.width === 0 || r.height === 0) return null;"
            f" el.scrollIntoView({{block: 'center', inline: 'center'}});"
            f" const r2 = el.getBoundingClientRect();"
            f" return {{x: r2.left + r2.width/2, y: r2.top + r2.height/2}}; }})()"
        )
        if not box:
            raise ValueError(f"No visible element matched {selector!r}")
        x = float(box["x"])
        y = float(box["y"])
        await self._send(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": x, "y": y},
        )
        await self._send(
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            },
        )
        await self._send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            },
        )

    async def screenshot(self, *, format: str = "png") -> bytes:
        if format not in ("png", "jpeg"):
            raise ValueError(f"Unsupported format: {format!r}")
        result = await self._send("Page.captureScreenshot", {"format": format})
        data = result.get("data", "")
        return base64.b64decode(data)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._cdp.send("Target.closeTarget", {"targetId": self._target_id})
        finally:
            self._browser._on_tab_closed(self)
