"""Tab — a CDP-attached page target you can drive."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ._cdp import CDPConnection
from ._errors import TargetClosed
from .element import ElementHandle
from .humanly import HumanBehavior

if TYPE_CHECKING:
    from .browser import Browser


_UNSET: Any = object()


def _is_navigation_race(details: dict[str, Any]) -> bool:
    """True if ``exceptionDetails`` is a CDP synthetic "context destroyed"
    rather than a real JS error.

    When a page starts navigating while ``Runtime.evaluate`` is in flight,
    Chrome destroys the execution context and CDP returns a stub with
    ``text="Uncaught"`` and no real ``exception`` object (no objectId,
    no className, no description). Real JS errors always carry a populated
    ``exception`` object.
    """
    text = details.get("text", "")
    exc = details.get("exception", {}) or {}
    has_real_exception = bool(
        exc.get("objectId")
        or exc.get("className")
        or exc.get("description")
        or exc.get("value") is not None
    )
    return text in ("Uncaught", "") and not has_real_exception


class Tab:
    """One browser tab, attached via a flat CDP session."""

    def __init__(self, browser: Browser, target_id: str, session_id: str) -> None:
        self._browser = browser
        self._target_id = target_id
        self._session_id = session_id
        self._cdp: CDPConnection = browser._cdp
        self._closed = False
        self._url = "about:blank"
        self._blocked_patterns: list[str] = []
        self._block_unsub: Any = None
        # cursor + humanly profile carried from Browser
        self._cursor: tuple[float, float] | None = None
        self._humanly: HumanBehavior | None = browser._humanly

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

    async def evaluate(self, expression: str, *, default: Any = _UNSET) -> Any:
        """Run JS in the tab and return the result by value.

        Navigation-race note: if the page starts navigating while this
        call is in flight, Chrome destroys the execution context and CDP
        returns a synthetic ``exceptionDetails`` with ``text="Uncaught"``
        and no real exception object. That's not a script error — the JS
        never ran — so we return ``None`` instead of raising. Callers
        that need to distinguish should re-evaluate after the navigation
        settles.

        Pass ``default=<value>`` to also swallow **real** JS exceptions
        (e.g. ``document.body.innerText`` while the page is still
        loading and ``document.body`` is null) and return that default
        instead of raising. Without ``default``, real JS errors still
        raise ``RuntimeError`` so bugs in your expression are visible.

        ::

            text = await tab.evaluate("document.body.innerText", default="")
        """
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
            if _is_navigation_race(details):
                return None if default is _UNSET else default
            if default is not _UNSET:
                return default
            raise RuntimeError(f"JS exception: {details.get('text', '')}")
        return result.get("result", {}).get("value")

    # ── element queries ───────────────────────────────────────────────

    async def query(self, selector: str) -> ElementHandle | None:
        """Return an ElementHandle for the first match, or None. No waiting."""
        result = await self._send(
            "Runtime.evaluate",
            {
                "expression": f"document.querySelector({selector!r})",
                "returnByValue": False,
            },
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            if _is_navigation_race(details):
                return None
            raise RuntimeError(f"JS exception: {details.get('text', '')}")
        obj = result.get("result", {})
        if obj.get("subtype") == "null" or "objectId" not in obj:
            return None
        return ElementHandle(self, obj["objectId"])

    async def query_all(self, selector: str) -> list[ElementHandle]:
        """Return ElementHandles for every match (possibly empty)."""
        result = await self._send(
            "Runtime.evaluate",
            {
                "expression": f"Array.from(document.querySelectorAll({selector!r}))",
                "returnByValue": False,
            },
        )
        array_id = result.get("result", {}).get("objectId")
        if not array_id:
            return []
        props = await self._cdp.send(
            "Runtime.getProperties",
            {"objectId": array_id, "ownProperties": True},
            session_id=self._session_id,
        )
        ids: list[str] = []
        for prop in props.get("result", []):
            if not prop.get("enumerable"):
                continue
            value = prop.get("value", {})
            obj_id = value.get("objectId")
            if obj_id and value.get("subtype") == "node":
                ids.append(obj_id)
        return [ElementHandle(self, i) for i in ids]

    async def find(
        self,
        selector: str,
        *,
        timeout: float = 30.0,
        poll_interval: float = 0.1,
    ) -> ElementHandle:
        """Wait until an element matches and return its ElementHandle.

        Raises TimeoutError after ``timeout`` seconds with nothing matching.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            handle = await self.query(selector)
            if handle is not None:
                return handle
            if loop.time() >= deadline:
                raise TimeoutError(f"timed out waiting for {selector!r} after {timeout}s")
            await asyncio.sleep(poll_interval)

    async def wait_for(self, selector: str, *, timeout: float = 30.0) -> ElementHandle:
        """Alias for :meth:`find`."""
        return await self.find(selector, timeout=timeout)

    async def exists(self, selector: str) -> bool:
        """True if a matching element exists right now, no waiting."""
        return (await self.query(selector)) is not None

    # ── interaction shortcuts (auto-wait) ─────────────────────────────

    async def click(self, selector: str, *, timeout: float = 30.0) -> None:
        """Wait for, then click via real Input.dispatchMouseEvent."""
        handle = await self.find(selector, timeout=timeout)
        await handle.click()

    async def type(
        self,
        selector: str,
        text: str,
        *,
        timeout: float = 30.0,
        delay_ms: float = 0.0,
    ) -> None:
        """Wait for, focus, and type ``text`` keystroke-by-keystroke."""
        handle = await self.find(selector, timeout=timeout)
        await handle.type(text, delay_ms=delay_ms)

    async def fill(
        self,
        selector: str,
        value: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        """Wait for, then set ``.value`` and fire input + change events."""
        handle = await self.find(selector, timeout=timeout)
        await handle.fill(value)

    async def hover(self, selector: str, *, timeout: float = 30.0) -> None:
        handle = await self.find(selector, timeout=timeout)
        await handle.hover()

    # ── read shortcuts ────────────────────────────────────────────────

    async def text(self, selector: str, *, timeout: float = 30.0) -> str:
        """Wait for and return ``innerText`` of the first match."""
        handle = await self.find(selector, timeout=timeout)
        return await handle.text()

    async def attribute(
        self,
        selector: str,
        name: str,
        *,
        timeout: float = 30.0,
    ) -> str | None:
        handle = await self.find(selector, timeout=timeout)
        return await handle.attribute(name)

    async def get_value(self, selector: str, *, timeout: float = 30.0) -> str:
        handle = await self.find(selector, timeout=timeout)
        return await handle.value()

    # ── network ───────────────────────────────────────────────────────

    async def block_urls(self, patterns: Sequence[str]) -> None:
        """Block requests whose URL matches any of the given ``*``-glob patterns.

        Example: ``await tab.block_urls(["*google-analytics.com*", "*.png"])``
        cuts ad/tracking calls and image bandwidth — common 2-5x speedup on
        ad-heavy pages.

        Implementation note: this re-enables ``Fetch`` with the new pattern
        set, replacing any prior ``Fetch`` config. If proxy-auth was wired in
        on this tab, call :meth:`block_urls` first and then proxy-auth will
        be lost — file an issue if you hit this; composing both is M5.6 work.
        """
        if not patterns:
            await self.unblock_urls()
            return
        fetch_patterns = [{"urlPattern": p, "requestStage": "Request"} for p in patterns]
        await self._send("Fetch.enable", {"patterns": fetch_patterns})

        sub = self._block_unsub
        if sub is not None:
            sub()
        self._blocked_patterns = list(patterns)

        async def _on_paused(params: dict[str, Any]) -> None:
            try:
                await self._cdp.send(
                    "Fetch.failRequest",
                    {
                        "requestId": params["requestId"],
                        "errorReason": "BlockedByClient",
                    },
                    session_id=self._session_id,
                )
            except Exception:
                pass

        self._block_unsub = self._cdp.on(
            "Fetch.requestPaused", _on_paused, session_id=self._session_id
        )

    async def unblock_urls(self) -> None:
        if self._block_unsub is not None:
            self._block_unsub()
            self._block_unsub = None
        self._blocked_patterns = []
        try:
            await self._send("Fetch.disable")
        except Exception:
            pass

    async def screenshot(self, *, format: str = "png") -> bytes:
        if format not in ("png", "jpeg"):
            raise ValueError(f"Unsupported format: {format!r}")
        result = await self._send("Page.captureScreenshot", {"format": format})
        data = result.get("data", "")
        return base64.b64decode(data)

    async def local_storage(self) -> dict[str, str]:
        """Snapshot of ``window.localStorage`` for the current origin.

        Only entries reachable via the standard ``localStorage`` API are
        captured (i.e. for this tab's origin — Chrome partitions storage
        by origin).
        """
        result = await self.evaluate("Object.fromEntries(Object.entries(localStorage))")
        if not isinstance(result, dict):
            return {}
        return {str(k): str(v) for k, v in result.items()}

    async def set_local_storage(
        self,
        items: dict[str, str],
        *,
        clear_first: bool = False,
    ) -> None:
        """Bulk-set ``localStorage`` keys on the current origin.

        ``clear_first=True`` wipes existing keys before applying. The tab
        must already be navigated to the target origin — Chrome refuses
        ``localStorage`` writes for an origin you haven't loaded.
        """
        import json as _json

        payload = _json.dumps(items)
        clear = "localStorage.clear();" if clear_first else ""
        await self.evaluate(
            "(() => {"
            f" const __items = {payload};"
            f" {clear}"
            " for (const [k, v] of Object.entries(__items))"
            "   localStorage.setItem(k, v);"
            " return true;"
            "})()"
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._cdp.send("Target.closeTarget", {"targetId": self._target_id})
        finally:
            self._browser._on_tab_closed(self)
