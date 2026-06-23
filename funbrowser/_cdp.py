"""Raw CDP transport over WebSocket.

Spec: https://chromedevtools.github.io/devtools-protocol/

The connection multiplexes:
- request/response by sequential id (per the CDP spec)
- event broadcasts dispatched to per-method listeners
- flat session sub-targets — every outgoing message may carry a sessionId
  obtained from Target.attachToTarget(flatten=True); incoming events with a
  sessionId are routed to session-scoped listeners.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as ws_connect

from ._errors import CDPConnectionClosed, CDPError

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


class CDPConnection:
    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._listeners: dict[str, list[EventHandler]] = {}
        self._session_listeners: dict[tuple[str, str], list[EventHandler]] = {}
        self._ws: ClientConnection | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._listener_tasks: set[asyncio.Task[None]] = set()
        self._closed = asyncio.Event()
        self._send_lock = asyncio.Lock()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    async def connect(self) -> None:
        self._ws = await ws_connect(self._ws_url, max_size=None, ping_interval=None)
        self._recv_task = asyncio.create_task(self._receive_loop(), name="funbrowser-cdp-recv")

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
        timeout: float | None = 30.0,
    ) -> dict[str, Any]:
        if self._ws is None or self._closed.is_set():
            raise CDPConnectionClosed("CDP connection is not open")
        self._next_id += 1
        msg_id = self._next_id
        message: dict[str, Any] = {"id": msg_id, "method": method, "params": params or {}}
        if session_id is not None:
            message["sessionId"] = session_id

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[msg_id] = fut
        try:
            async with self._send_lock:
                await self._ws.send(json.dumps(message))
            if timeout is None:
                return await fut
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(msg_id, None)

    def on(
        self,
        method: str,
        handler: EventHandler,
        *,
        session_id: str | None = None,
    ) -> Unsubscribe:
        """Subscribe to a CDP event. Returns an unsubscribe callable."""
        if session_id is None:
            lst = self._listeners.setdefault(method, [])
        else:
            lst = self._session_listeners.setdefault((session_id, method), [])
        lst.append(handler)

        def _unsub() -> None:
            try:
                lst.remove(handler)
            except ValueError:
                pass

        return _unsub

    async def _receive_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("CDP: failed to decode message")
                    continue
                self._dispatch(msg)
        except Exception:
            logger.debug("CDP: receive loop ended", exc_info=True)
        finally:
            self._closed.set()
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(CDPConnectionClosed("CDP connection closed mid-request"))
            self._pending.clear()

    def _dispatch(self, msg: dict[str, Any]) -> None:
        if "id" in msg:
            fut = self._pending.pop(msg["id"], None)
            if fut is None or fut.done():
                return
            if "error" in msg:
                err = msg["error"]
                fut.set_exception(
                    CDPError(
                        err.get("message", "CDP error"),
                        code=err.get("code"),
                        data=err.get("data"),
                    )
                )
            else:
                fut.set_result(msg.get("result", {}))
            return

        method = msg.get("method")
        if not method:
            return
        session_id = msg.get("sessionId")
        params = msg.get("params", {})
        if session_id is not None:
            for h in list(self._session_listeners.get((session_id, method), [])):
                self._safe_invoke(h, params)
        for h in list(self._listeners.get(method, [])):
            self._safe_invoke(h, params)

    def _safe_invoke(self, handler: EventHandler, params: dict[str, Any]) -> None:
        try:
            result = handler(params)
        except Exception:
            logger.exception("CDP listener raised")
            return
        if asyncio.iscoroutine(result):
            task = asyncio.create_task(self._run_async(result))
            self._listener_tasks.add(task)
            task.add_done_callback(self._listener_tasks.discard)

    async def _run_async(self, coro: Awaitable[None]) -> None:
        try:
            await coro
        except Exception:
            logger.exception("CDP async listener raised")

    async def close(self) -> None:
        if self._closed.is_set():
            return
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._recv_task is not None:
            try:
                await asyncio.wait_for(self._recv_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                self._recv_task.cancel()
        self._closed.set()
