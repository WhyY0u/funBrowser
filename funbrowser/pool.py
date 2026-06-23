"""BrowserPool — run a farm of Browser instances with bounded concurrency.

Each pool holds up to ``size`` :class:`Browser` instances, created lazily on
first use and kept alive between tasks. Acquire one via the
``acquire()`` async-context-manager, or submit a callable via ``run(fn)`` /
``run_all([fn, ...])`` and the pool will dispatch + retrieve the result.

If ``proxies`` is given, each browser in the pool gets the next proxy from
the list (round-robin by creation order). Combined with
``geo_autoconfigure=True`` (default), the result is a fleet of browsers
each pinned to a different exit IP + timezone + locale.

Single-process only — for multi-machine farms, run separate pools.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, Self, TypeVar

from .browser import Browser
from .proxy import Proxy

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BrowserPool:
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
        self._created: list[Browser] = []
        self._available: asyncio.Queue[Browser] = asyncio.Queue()
        self._closed = False

    @property
    def size(self) -> int:
        return self._size

    @property
    def created(self) -> int:
        """Number of browsers actually spawned so far (lazy)."""
        return len(self._created)

    @property
    def idle(self) -> int:
        """How many of the created browsers are currently free."""
        return self._available.qsize()

    @property
    def busy(self) -> int:
        """How many of the created browsers are currently in-use."""
        return len(self._created) - self._available.qsize()

    @property
    def browsers(self) -> tuple[Browser, ...]:
        """Snapshot of all created browsers (busy or idle)."""
        return tuple(self._created)

    async def _spawn(self, index: int) -> Browser:
        kwargs = dict(self._browser_kwargs)
        if self._proxies:
            kwargs["proxy"] = self._proxies[index % len(self._proxies)]
        logger.debug("pool: spawning browser %d/%d", index + 1, self._size)
        return await Browser.start(**kwargs)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Browser]:
        if self._closed:
            raise RuntimeError("pool is closed")

        # Fast path — an idle browser is available.
        browser: Browser | None = None
        try:
            browser = self._available.get_nowait()
        except asyncio.QueueEmpty:
            browser = None

        if browser is None:
            # Either lazy-spawn a fresh one (under cap) or wait for a busy
            # browser to come back. The lock serialises the check.
            async with self._lock:
                try:
                    browser = self._available.get_nowait()
                except asyncio.QueueEmpty:
                    if len(self._created) < self._size:
                        idx = len(self._created)
                        browser = await self._spawn(idx)
                        self._created.append(browser)
            if browser is None:
                browser = await self._available.get()

        try:
            yield browser
        finally:
            if not self._closed:
                self._available.put_nowait(browser)

    async def run(self, task: Callable[[Browser], Awaitable[T]]) -> T:
        """Acquire a browser, run ``task(browser)``, release. Returns the result."""
        async with self.acquire() as browser:
            return await task(browser)

    async def run_all(self, tasks: Iterable[Callable[[Browser], Awaitable[T]]]) -> list[T]:
        """Dispatch every task across the pool concurrently and gather results.

        At most :attr:`size` tasks execute in parallel; the rest queue.
        """
        return list(await asyncio.gather(*(self.run(t) for t in tasks)))

    async def stop(self) -> None:
        """Tear down every created browser. The pool is then unusable."""
        if self._closed:
            return
        self._closed = True
        await asyncio.gather(
            *(b.stop() for b in self._created),
            return_exceptions=True,
        )
        self._created.clear()
        # Drain the queue so nobody waits forever on a closed pool.
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.stop()
