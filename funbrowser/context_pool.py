"""ContextPool — lightweight pool of BrowserContexts on a shared Chrome.

API mirrors :class:`funbrowser.BrowserPool`: ``acquire()`` / ``run()`` /
``run_all()`` / ``stop()`` / async-context-manager support — only the
unit of isolation changes. Where ``BrowserPool`` keeps N Chrome
processes alive, ``ContextPool`` keeps **one** Chrome alive with N
isolated browser contexts.

Memory comparison (typical example, headless + mini):

- ``BrowserPool(size=10)``  -> ~10 x 100 MB  = ~1.0 GB
- ``ContextPool(size=10)``  -> ~1 x 180 MB + 10 x 8 MB = ~260 MB

You give up the process-level isolation: if the host Chrome crashes,
every context dies with it. For farms where the workload is "many
parallel lightweight scrapes" this is the right shape; for "long-lived
high-value sessions where crash recovery matters", stick with
``BrowserPool``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, Self, TypeVar

from .browser import Browser
from .context import BrowserContext
from .proxy import Proxy

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ContextPool:
    def __init__(
        self,
        size: int = 5,
        *,
        proxies: Sequence[str | Proxy] | None = None,
        **browser_kwargs: Any,
    ) -> None:
        if size < 1:
            raise ValueError("pool size must be >= 1")
        self._size = size
        self._proxies = list(proxies) if proxies else None
        self._browser_kwargs = browser_kwargs
        self._lock = asyncio.Lock()
        self._browser: Browser | None = None
        self._contexts: list[BrowserContext] = []
        self._available: asyncio.Queue[BrowserContext] = asyncio.Queue()
        self._closed = False

    @property
    def size(self) -> int:
        return self._size

    @property
    def created(self) -> int:
        """Number of contexts actually spawned so far (lazy)."""
        return len(self._contexts)

    @property
    def idle(self) -> int:
        return self._available.qsize()

    @property
    def busy(self) -> int:
        return len(self._contexts) - self._available.qsize()

    @property
    def contexts(self) -> tuple[BrowserContext, ...]:
        return tuple(self._contexts)

    @property
    def browser(self) -> Browser | None:
        """The shared host Browser. ``None`` until first acquire."""
        return self._browser

    async def _ensure_browser(self) -> Browser:
        if self._browser is None:
            self._browser = await Browser.start(**self._browser_kwargs)
        return self._browser

    async def _spawn(self, index: int) -> BrowserContext:
        browser = await self._ensure_browser()
        proxy = self._proxies[index % len(self._proxies)] if self._proxies else None
        logger.debug("context-pool: spawning context %d/%d", index + 1, self._size)
        return await browser.create_context(proxy=proxy)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[BrowserContext]:
        if self._closed:
            raise RuntimeError("pool is closed")

        ctx: BrowserContext | None = None
        try:
            ctx = self._available.get_nowait()
        except asyncio.QueueEmpty:
            ctx = None

        if ctx is None:
            async with self._lock:
                try:
                    ctx = self._available.get_nowait()
                except asyncio.QueueEmpty:
                    if len(self._contexts) < self._size:
                        idx = len(self._contexts)
                        ctx = await self._spawn(idx)
                        self._contexts.append(ctx)
            if ctx is None:
                ctx = await self._available.get()

        try:
            yield ctx
        finally:
            if not self._closed:
                self._available.put_nowait(ctx)

    async def run(self, task: Callable[[BrowserContext], Awaitable[T]]) -> T:
        async with self.acquire() as ctx:
            return await task(ctx)

    async def run_all(self, tasks: Iterable[Callable[[BrowserContext], Awaitable[T]]]) -> list[T]:
        return list(await asyncio.gather(*(self.run(t) for t in tasks)))

    async def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        for ctx in self._contexts:
            try:
                await ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._browser is not None:
            try:
                await self._browser.stop()
            except Exception:
                pass
            self._browser = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.stop()
