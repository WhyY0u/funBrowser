"""Tab — a CDP-attached page target you can drive."""

from __future__ import annotations

import asyncio
import base64
import fnmatch
import json as _json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any, Literal

from ._cdp import CDPConnection
from ._errors import CDPError, TargetClosed
from .element import ElementHandle
from .humanly import HumanBehavior

logger = logging.getLogger(__name__)

ResponseHandler = Callable[["Response"], Awaitable[None] | None]
ResponsePredicate = Callable[["Response"], bool]
RequestHandler = Callable[["Request"], Awaitable[None] | None]
RequestPredicate = Callable[["Request"], bool]
RouteHandler = Callable[["Route"], Awaitable[None] | None]
# Fetch dispatcher returns True if it handled the paused request
# (called continueRequest / failRequest / fulfillRequest), False to pass.
_FetchDispatcher = Callable[[dict[str, Any]], Awaitable[bool]]

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
        self._network_enabled = False
        # Shared Fetch.enable infrastructure used by block_urls + route().
        # _fetch_patterns is the union of all patterns currently registered
        # with Chrome; _fetch_dispatchers is the chain that decides what to
        # do with each paused request (block, route, or pass through).
        self._fetch_enabled = False
        self._fetch_patterns: list[dict[str, Any]] = []
        self._fetch_dispatchers: list[_FetchDispatcher] = []
        self._fetch_unsub: Any = None
        # (url_pattern, handler, stage) where stage ∈ {"request", "response"}
        self._route_entries: list[tuple[str, RouteHandler, str]] = []
        # Keeps strong refs to background resync tasks spawned from
        # route-unsubscribe so they aren't GC'd mid-flight.
        self._bg_tasks: set[asyncio.Task[None]] = set()
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

        Composes with :meth:`route` — both share a single underlying
        ``Fetch.enable`` and a dispatch chain. The block layer runs
        before route handlers, so a blocked URL is killed before any
        route gets to see it. Calling ``block_urls`` again replaces
        the block pattern set (not additive); route handlers stay.
        """
        # Drop any old block dispatcher (block_urls is a "set", not "add").
        self._fetch_dispatchers = [
            d for d in self._fetch_dispatchers if getattr(d, "_kind", None) != "block"
        ]
        self._blocked_patterns = list(patterns)

        if not patterns and not self._route_entries:
            # Nothing left to do — tear down Fetch entirely.
            await self._fetch_disable_if_idle()
            return

        if patterns:

            async def _block_dispatcher(params: dict[str, Any]) -> bool:
                url = params.get("request", {}).get("url", "")
                for p in self._blocked_patterns:
                    if fnmatch.fnmatchcase(url, p):
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
                        return True
                return False

            _block_dispatcher._kind = "block"  # type: ignore[attr-defined]
            # Block runs FIRST so it can short-circuit before routes.
            self._fetch_dispatchers.insert(0, _block_dispatcher)

        await self._fetch_sync_patterns()

    async def unblock_urls(self) -> None:
        self._blocked_patterns = []
        self._fetch_dispatchers = [
            d for d in self._fetch_dispatchers if getattr(d, "_kind", None) != "block"
        ]
        if not self._route_entries:
            await self._fetch_disable_if_idle()
        else:
            await self._fetch_sync_patterns()

    async def route(
        self,
        url_pattern: str,
        handler: RouteHandler,
        *,
        stage: Literal["request", "response"] = "request",
    ) -> Callable[[], None]:
        """Intercept requests matching ``url_pattern`` and decide their fate.

        The handler receives a :class:`Route` and must call exactly one of
        ``route.continue_()``, ``route.abort()``, or ``route.fulfill(...)``
        — otherwise the request hangs until Chrome times it out. If the
        handler raises, the request is auto-continued so the page doesn't
        wedge.

        ``stage`` picks where to intercept:

        - ``"request"`` (default) — before the request leaves the browser.
          You can rewrite the URL, method, headers, or post body via
          ``route.continue_(**overrides)`` and let it through, or
          short-circuit with ``abort()`` / ``fulfill()``.
        - ``"response"`` — *after* the server replies but before the page
          sees it. ``route.response`` is populated with the actual
          server response (status, headers, body) — you can inspect it,
          modify it, and ``fulfill()`` with the modified version, or
          ``continue_()`` to let it pass through unchanged. This is the
          equivalent of Playwright's ``route.fetch()`` + ``fulfill()``
          dance, but without the second HTTP roundtrip: we use the
          response that already came back from the origin.

        ``url_pattern`` uses Chrome's URL-pattern syntax (``*`` matches
        anything). Routes are stackable: register many; they fire in
        registration order; the first whose URL matches AND whose handler
        resolves the request wins. Routes compose with :meth:`block_urls`
        — blocks run first.

        Returns an unsubscribe callable. Calling it removes only this
        route; other routes and any block patterns stay in place.

        Request-stage example::

            async def _mock_captcha(route):
                if route.request.method == "POST":
                    await route.fulfill(
                        status=200,
                        body=b'{"token":"fake"}',
                        content_type="application/json",
                    )
                else:
                    await route.continue_()

            unsub = await tab.route("*captcha*", _mock_captcha)

        Response-stage example — strip a tracking field out of an API
        response on the fly::

            async def _strip_pii(route):
                payload = await route.response.json()
                payload.pop("user_email", None)
                await route.fulfill(
                    status=route.response.status,
                    body=json.dumps(payload),
                    headers=route.response.headers,
                )

            unsub = await tab.route("*api/profile*", _strip_pii, stage="response")
        """
        if stage not in ("request", "response"):
            raise ValueError(f"stage must be 'request' or 'response', got {stage!r}")
        entry = (url_pattern, handler, stage)
        self._route_entries.append(entry)

        async def _route_dispatcher(params: dict[str, Any]) -> bool:
            url = params.get("request", {}).get("url", "")
            if not fnmatch.fnmatchcase(url, url_pattern):
                return False
            # Filter by stage: response-stage events carry responseStatusCode.
            is_response_stage = "responseStatusCode" in params
            if stage == "response" and not is_response_stage:
                return False
            if stage == "request" and is_response_stage:
                return False
            request = _request_from_paused(self, params)
            response: Response | None = None
            if is_response_stage:
                response = _response_from_paused(self, params)
            route_obj = Route(
                self,
                str(params.get("requestId", "")),
                request,
                response=response,
                stage=stage,
            )
            try:
                result = handler(route_obj)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("route handler raised for %s", url)
                if not route_obj._resolved:
                    # Don't strand the request — fall through to auto-continue.
                    return False
            return route_obj._resolved

        _route_dispatcher._kind = "route"  # type: ignore[attr-defined]
        _route_dispatcher._entry = entry  # type: ignore[attr-defined]
        self._fetch_dispatchers.append(_route_dispatcher)

        await self._fetch_sync_patterns()

        def _unsub() -> None:
            try:
                self._route_entries.remove(entry)
            except ValueError:
                pass
            self._fetch_dispatchers = [
                d for d in self._fetch_dispatchers if getattr(d, "_entry", None) is not entry
            ]
            # Best-effort resync — the user may not be in an async context here.
            task = asyncio.ensure_future(self._fetch_resync_after_unroute())
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

        return _unsub

    async def mock(
        self,
        url_pattern: str,
        body: bytes | str,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        content_type: str | None = None,
    ) -> Callable[[], None]:
        """Shorthand for ``tab.route(url, lambda r: r.fulfill(...))``.

        ::

            await tab.mock("*api/token*", '{"token":"abc"}',
                           content_type="application/json")
        """

        async def _handler(route: Route) -> None:
            await route.fulfill(
                status=status,
                body=body,
                headers=headers,
                content_type=content_type,
            )

        return await self.route(url_pattern, _handler)

    async def _fetch_resync_after_unroute(self) -> None:
        if not self._route_entries and not self._blocked_patterns:
            await self._fetch_disable_if_idle()
        else:
            try:
                await self._fetch_sync_patterns()
            except Exception:
                pass

    async def _fetch_sync_patterns(self) -> None:
        """Re-call ``Fetch.enable`` with the union of all active patterns."""
        patterns: list[dict[str, Any]] = []
        for p in self._blocked_patterns:
            patterns.append({"urlPattern": p, "requestStage": "Request"})
        for url_pat, _, stage in self._route_entries:
            patterns.append(
                {
                    "urlPattern": url_pat,
                    "requestStage": "Response" if stage == "response" else "Request",
                }
            )
        self._fetch_patterns = patterns

        await self._send("Fetch.enable", {"patterns": patterns})
        self._fetch_enabled = True

        if self._fetch_unsub is None:

            async def _on_paused(params: dict[str, Any]) -> None:
                for d in list(self._fetch_dispatchers):
                    try:
                        if await d(params):
                            return
                    except Exception:
                        logger.exception("fetch dispatcher raised")
                # No dispatcher claimed the request — pass it through.
                try:
                    await self._cdp.send(
                        "Fetch.continueRequest",
                        {"requestId": params["requestId"]},
                        session_id=self._session_id,
                    )
                except Exception:
                    pass

            self._fetch_unsub = self._cdp.on(
                "Fetch.requestPaused", _on_paused, session_id=self._session_id
            )

    async def _fetch_disable_if_idle(self) -> None:
        if not self._fetch_enabled:
            return
        if self._fetch_unsub is not None:
            self._fetch_unsub()
            self._fetch_unsub = None
        self._fetch_enabled = False
        self._fetch_patterns = []
        try:
            await self._send("Fetch.disable")
        except Exception:
            pass

    async def _ensure_network_enabled(self) -> None:
        if self._network_enabled:
            return
        await self._send("Network.enable")
        self._network_enabled = True

    async def on_request(self, handler: RequestHandler) -> Callable[[], None]:
        """Register a callback for every HTTP request on this tab.

        Mirrors :meth:`on_response`. Handler receives a :class:`Request`
        for each ``Network.requestWillBeSent`` event. Both sync and
        async handlers are accepted. Returns an unsubscribe callable.

        For pure observation. To intercept and modify / abort / fulfill
        a request, use :meth:`route` — it gives you a :class:`Route`
        with full control.
        """
        await self._ensure_network_enabled()

        async def _on_event(params: dict[str, Any]) -> None:
            req = _request_from_will_be_sent(self, params)
            if req is None:
                return
            try:
                result = handler(req)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("on_request handler raised for %s", req.url)

        return self._cdp.on("Network.requestWillBeSent", _on_event, session_id=self._session_id)

    async def wait_for_request(
        self,
        url_or_predicate: str | RequestPredicate,
        *,
        timeout: float = 30.0,
    ) -> Request:
        """Wait for the first request matching a URL substring or predicate.

        Mirrors :meth:`wait_for_response`. Raises :class:`asyncio.TimeoutError`
        if no match arrives in ``timeout`` seconds.
        """
        await self._ensure_network_enabled()

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Request] = loop.create_future()

        _matches: RequestPredicate
        if isinstance(url_or_predicate, str):
            needle = url_or_predicate
            _matches = lambda r: needle in r.url  # noqa: E731
        else:
            _matches = url_or_predicate

        def _on_event(params: dict[str, Any]) -> None:
            if fut.done():
                return
            req = _request_from_will_be_sent(self, params)
            if req is None:
                return
            try:
                if _matches(req):
                    fut.set_result(req)
            except Exception:
                logger.exception("wait_for_request predicate raised for %s", req.url)

        unsub = self._cdp.on("Network.requestWillBeSent", _on_event, session_id=self._session_id)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            unsub()

    async def on_response(
        self,
        handler: ResponseHandler,
        *,
        prefetch_body: bool = False,
    ) -> Callable[[], None]:
        """Register a callback for every HTTP response on this tab.

        The handler is invoked with a :class:`Response` for each
        ``Network.responseReceived`` event. Both sync and async
        handlers are accepted. Returns an unsubscribe callable.

        The response body is NOT fetched eagerly — call
        ``await response.body()`` (or ``.text()`` / ``.json()``) from
        inside the handler when you need it. Chrome buffers bodies for
        a limited window after the request completes; reading them
        later may fail with "no data found for resource".

        Use this for response-snooping flows like the DataDome SDK
        intercept (read body of a specific XHR, extract the payload,
        feed it to a solver). For just blocking or modifying requests,
        see :meth:`block_urls`.

        Pass ``prefetch_body=True`` to have FunBrowser fetch and cache
        each response's body *before* invoking your handler. This
        sidesteps Chrome's body-eviction window — useful when your
        handler may yield to the event loop before reading the body,
        or when you want to access the body outside the handler. Costs
        an extra ``Network.getResponseBody`` per response, so leave it
        off for high-volume tabs unless you need it.

        ::

            async def _snoop(resp):
                if "datadome.co" in resp.url and resp.status == 200:
                    payload = await resp.json()
                    print("got DD payload:", payload.keys())

            unsub = await tab.on_response(_snoop)
            await tab.goto("https://target.com")
            ...
            unsub()
        """
        await self._ensure_network_enabled()

        async def _on_event(params: dict[str, Any]) -> None:
            resp = _response_from_event(self, params)
            if resp is None:
                return
            if prefetch_body:
                try:
                    await resp.body()
                except Exception:
                    pass
            try:
                result = handler(resp)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("on_response handler raised for %s", resp.url)

        return self._cdp.on("Network.responseReceived", _on_event, session_id=self._session_id)

    async def wait_for_response(
        self,
        url_or_predicate: str | ResponsePredicate,
        *,
        timeout: float = 30.0,
        prefetch_body: bool = False,
    ) -> Response:
        """Wait for the first response matching a URL substring or predicate.

        ``url_or_predicate`` is either a substring matched against
        ``response.url``, or a callable ``(Response) -> bool``.
        Returns the matching :class:`Response`; the body has not been
        fetched yet — ``await resp.body()`` / ``.text()`` / ``.json()``
        to read it.

        Raises :class:`asyncio.TimeoutError` if no match arrives in
        ``timeout`` seconds.

        ::

            async with funbrowser.start(headless=True) as browser:
                tab = await browser.new_tab()
                # arm the wait BEFORE the action that triggers the response
                waiter = asyncio.create_task(
                    tab.wait_for_response("/api/captcha", timeout=20)
                )
                await tab.goto("https://target.com")
                resp = await waiter
                payload = await resp.json()
        """
        await self._ensure_network_enabled()

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Response] = loop.create_future()

        _matches: ResponsePredicate
        if isinstance(url_or_predicate, str):
            needle = url_or_predicate
            _matches = lambda r: needle in r.url  # noqa: E731
        else:
            _matches = url_or_predicate

        def _on_event(params: dict[str, Any]) -> None:
            if fut.done():
                return
            resp = _response_from_event(self, params)
            if resp is None:
                return
            try:
                if _matches(resp):
                    fut.set_result(resp)
            except Exception:
                logger.exception("wait_for_response predicate raised for %s", resp.url)

        unsub = self._cdp.on("Network.responseReceived", _on_event, session_id=self._session_id)
        try:
            resp = await asyncio.wait_for(fut, timeout=timeout)
            if prefetch_body:
                try:
                    await resp.body()
                except Exception:
                    pass
            return resp
        finally:
            unsub()

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


class Response:
    """A snapshot of an HTTP response observed via CDP.

    Yielded by :meth:`Tab.on_response` and :meth:`Tab.wait_for_response`.
    Metadata (``url``, ``status``, ``headers``) is captured at the
    moment ``Network.responseReceived`` fires. The body is lazy — call
    ``await body()`` / ``text()`` / ``json()`` to fetch it via
    ``Network.getResponseBody``. The fetched body is cached.

    Chrome buffers response bodies for a limited window after the
    request completes. Reading the body well after the response fired
    (e.g. several seconds later, or after navigation) may fail with
    "No data found for resource with given identifier" — read it
    promptly from inside your handler if you need it.
    """

    __slots__ = ("_body", "_request_id", "_tab", "_via_fetch", "headers", "status", "url")

    def __init__(
        self,
        tab: Tab,
        request_id: str,
        url: str,
        status: int,
        headers: dict[str, str],
        *,
        via_fetch: bool = False,
    ) -> None:
        self._tab = tab
        self._request_id = request_id
        self.url = url
        self.status = status
        self.headers = headers
        self._body: bytes | None = None
        # When True, body is fetched via Fetch.getResponseBody (only
        # valid inside the response stage of a route handler); when
        # False, via Network.getResponseBody (the observation path).
        self._via_fetch = via_fetch

    def __repr__(self) -> str:
        return f"<Response {self.status} {self.url!r}>"

    async def body(self) -> bytes:
        """Fetch the raw response body. Cached after first call."""
        if self._body is not None:
            return self._body
        method = "Fetch.getResponseBody" if self._via_fetch else "Network.getResponseBody"
        try:
            result = await self._tab._send(method, {"requestId": self._request_id})
        except CDPError as exc:
            raise RuntimeError(
                f"Could not fetch body for {self.url!r}: {exc}. The body "
                "may have been evicted from Chrome's buffer — read it from "
                "inside the on_response handler instead of saving the "
                "Response for later, or pass prefetch_body=True so "
                "FunBrowser fetches the body before invoking your handler."
            ) from exc
        raw = result.get("body", "")
        if result.get("base64Encoded"):
            self._body = base64.b64decode(raw)
        elif isinstance(raw, bytes):
            self._body = raw
        else:
            self._body = str(raw).encode("utf-8")
        return self._body

    async def text(self) -> str:
        """Body decoded as UTF-8 (replacement on invalid sequences)."""
        return (await self.body()).decode("utf-8", errors="replace")

    async def json(self) -> Any:
        """Body parsed as JSON. Raises ``json.JSONDecodeError`` on bad input."""
        return _json.loads(await self.text())


def _response_from_event(tab: Tab, params: dict[str, Any]) -> Response | None:
    """Build a Response from a ``Network.responseReceived`` event payload."""
    resp_data = params.get("response")
    if not isinstance(resp_data, dict):
        return None
    headers_in = resp_data.get("headers") or {}
    headers: dict[str, str] = {}
    if isinstance(headers_in, dict):
        for k, v in headers_in.items():
            headers[str(k)] = str(v)
    return Response(
        tab=tab,
        request_id=str(params.get("requestId", "")),
        url=str(resp_data.get("url", "")),
        status=int(resp_data.get("status", 0) or 0),
        headers=headers,
    )


class Request:
    """Snapshot of an HTTP request seen on this tab.

    Yielded by :meth:`Tab.on_request`, :meth:`Tab.wait_for_request`,
    and as the ``.request`` attribute of :class:`Route`. The fields
    captured here mirror what Chrome reports on
    ``Network.requestWillBeSent`` (or ``Fetch.requestPaused`` for
    routed requests):

    - ``url``, ``method``, ``headers`` — request line + headers
    - ``post_data`` — request body if present, otherwise ``None``.
      Truncated by Chrome for large bodies; treat as a preview.
    - ``resource_type`` — Chrome's classification (``Document``,
      ``XHR``, ``Fetch``, ``Image``, ``Script``, ``Stylesheet``, ...)
    - ``is_navigation`` — True for the top-level navigation request
    """

    __slots__ = (
        "_request_id",
        "_tab",
        "headers",
        "is_navigation",
        "method",
        "post_data",
        "resource_type",
        "url",
    )

    def __init__(
        self,
        tab: Tab,
        request_id: str,
        url: str,
        method: str,
        headers: dict[str, str],
        post_data: str | None = None,
        resource_type: str = "",
        is_navigation: bool = False,
    ) -> None:
        self._tab = tab
        self._request_id = request_id
        self.url = url
        self.method = method
        self.headers = headers
        self.post_data = post_data
        self.resource_type = resource_type
        self.is_navigation = is_navigation

    def __repr__(self) -> str:
        return f"<Request {self.method} {self.url!r}>"


def _request_from_will_be_sent(tab: Tab, params: dict[str, Any]) -> Request | None:
    """Build a Request from a ``Network.requestWillBeSent`` event payload."""
    req_data = params.get("request")
    if not isinstance(req_data, dict):
        return None
    headers_in = req_data.get("headers") or {}
    headers: dict[str, str] = {}
    if isinstance(headers_in, dict):
        for k, v in headers_in.items():
            headers[str(k)] = str(v)
    post_data = req_data.get("postData")
    return Request(
        tab=tab,
        request_id=str(params.get("requestId", "")),
        url=str(req_data.get("url", "")),
        method=str(req_data.get("method", "GET")),
        headers=headers,
        post_data=str(post_data) if post_data is not None else None,
        resource_type=str(params.get("type", "")),
        is_navigation=bool(params.get("requestId") == params.get("loaderId")),
    )


def _response_from_paused(tab: Tab, params: dict[str, Any]) -> Response:
    """Build a Response from a response-stage ``Fetch.requestPaused`` payload.

    The returned Response is wired to Fetch.getResponseBody — only valid
    while the route handler is running, since the body lives in Chrome's
    fetch buffer until we call continueResponse / fulfillRequest.
    """
    req_data = params.get("request") or {}
    url = str(req_data.get("url", ""))
    status = int(params.get("responseStatusCode", 0) or 0)
    headers: dict[str, str] = {}
    for h in params.get("responseHeaders") or []:
        if isinstance(h, dict):
            name = str(h.get("name", ""))
            value = str(h.get("value", ""))
            headers[name] = value
    return Response(
        tab=tab,
        request_id=str(params.get("requestId", "")),
        url=url,
        status=status,
        headers=headers,
        via_fetch=True,
    )


def _request_from_paused(tab: Tab, params: dict[str, Any]) -> Request:
    """Build a Request from a ``Fetch.requestPaused`` event payload."""
    req_data = params.get("request") or {}
    headers_in = req_data.get("headers") or {}
    headers: dict[str, str] = {}
    if isinstance(headers_in, dict):
        for k, v in headers_in.items():
            headers[str(k)] = str(v)
    post_data = req_data.get("postData")
    return Request(
        tab=tab,
        request_id=str(params.get("requestId", "")),
        url=str(req_data.get("url", "")),
        method=str(req_data.get("method", "GET")),
        headers=headers,
        post_data=str(post_data) if post_data is not None else None,
        resource_type=str(params.get("resourceType", "")),
        is_navigation=False,
    )


class Route:
    """A paused request waiting for a verdict.

    Yielded to handlers registered via :meth:`Tab.route`. The handler
    MUST call exactly one of :meth:`continue_`, :meth:`abort`, or
    :meth:`fulfill` — otherwise the request hangs until Chrome's
    network timeout. If the handler raises before resolving, the
    request is auto-continued so the page doesn't wedge.

    Available context:

    - ``route.request`` — the request, always populated.
    - ``route.response`` — the server's response, populated only at
      response stage (None at request stage). Body is fetched lazily
      via ``await route.response.body()`` / ``.text()`` / ``.json()``
      from Chrome's Fetch buffer; this is only valid while the
      handler is running, so read it before you ``continue_`` /
      ``fulfill``.
    - ``route.stage`` — ``"request"`` or ``"response"``.
    """

    __slots__ = ("_request_id", "_resolved", "_tab", "request", "response", "stage")

    def __init__(
        self,
        tab: Tab,
        request_id: str,
        request: Request,
        *,
        response: Response | None = None,
        stage: str = "request",
    ) -> None:
        self._tab = tab
        self._request_id = request_id
        self.request = request
        self.response = response
        self.stage = stage
        self._resolved = False

    def __repr__(self) -> str:
        return f"<Route@{self.stage} {self.request.method} {self.request.url!r}>"

    async def continue_(
        self,
        *,
        url: str | None = None,
        method: str | None = None,
        headers: dict[str, str] | None = None,
        post_data: bytes | str | None = None,
    ) -> None:
        """Let the request proceed, optionally modifying it first.

        At **request stage**: ``url`` / ``method`` / ``headers`` /
        ``post_data`` rewrite the outgoing request. Any kwarg left
        unset keeps Chrome's original value. ``headers`` replaces the
        entire header set — to add a single header, merge it onto
        ``self.request.headers`` and pass the merged dict.

        At **response stage**: only ``headers`` is meaningful — it
        rewrites the response headers the page sees. ``url`` / ``method``
        / ``post_data`` raise ``ValueError`` (they're request-only).
        """
        if self._resolved:
            raise RuntimeError("route already resolved")
        if self.stage == "response":
            if url is not None or method is not None or post_data is not None:
                raise ValueError(
                    "url / method / post_data can't be overridden at response "
                    "stage — the request already went out. Use fulfill() to "
                    "rewrite the response body / status, or pass headers= to "
                    "override response headers."
                )
            params: dict[str, Any] = {"requestId": self._request_id}
            if headers is not None:
                params["responseHeaders"] = [{"name": k, "value": v} for k, v in headers.items()]
            self._resolved = True
            await self._tab._send("Fetch.continueResponse", params)
            return
        params = {"requestId": self._request_id}
        if url is not None:
            params["url"] = url
        if method is not None:
            params["method"] = method
        if headers is not None:
            params["headers"] = [{"name": k, "value": v} for k, v in headers.items()]
        if post_data is not None:
            if isinstance(post_data, str):
                post_data = post_data.encode("utf-8")
            params["postData"] = base64.b64encode(post_data).decode("ascii")
        self._resolved = True
        await self._tab._send("Fetch.continueRequest", params)

    async def abort(self, error_reason: str = "Failed") -> None:
        """Cancel the request with a CDP error reason.

        Valid reasons include ``Failed``, ``Aborted``, ``TimedOut``,
        ``AccessDenied``, ``ConnectionClosed``, ``ConnectionReset``,
        ``ConnectionRefused``, ``ConnectionAborted``, ``ConnectionFailed``,
        ``NameNotResolved``, ``InternetDisconnected``, ``AddressUnreachable``,
        ``BlockedByClient``, ``BlockedByResponse``.
        """
        if self._resolved:
            raise RuntimeError("route already resolved")
        self._resolved = True
        await self._tab._send(
            "Fetch.failRequest",
            {"requestId": self._request_id, "errorReason": error_reason},
        )

    async def fulfill(
        self,
        *,
        status: int = 200,
        body: bytes | str = b"",
        headers: dict[str, str] | None = None,
        content_type: str | None = None,
    ) -> None:
        """Return a synthetic response without hitting the network.

        Useful for mocking SDK endpoints in tests, feeding a solver's
        pre-computed token back as if it came from the server, or
        short-circuiting tracking calls with a 204.
        """
        if self._resolved:
            raise RuntimeError("route already resolved")
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        hdr_list: list[dict[str, str]] = []
        if content_type:
            hdr_list.append({"name": "Content-Type", "value": content_type})
        if headers:
            for k, v in headers.items():
                if content_type and k.lower() == "content-type":
                    continue
                hdr_list.append({"name": k, "value": v})
        self._resolved = True
        await self._tab._send(
            "Fetch.fulfillRequest",
            {
                "requestId": self._request_id,
                "responseCode": status,
                "responseHeaders": hdr_list,
                "body": base64.b64encode(body_bytes).decode("ascii"),
            },
        )
