"""Unit tests for CDPConnection using an in-process websockets echo server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve

from funbrowser._cdp import CDPConnection
from funbrowser._errors import CDPError

Responder = Callable[[ServerConnection, dict[str, Any]], Awaitable[None]]


@asynccontextmanager
async def _server(responder: Responder) -> AsyncIterator[str]:
    async def handler(ws: ServerConnection) -> None:
        async for raw in ws:
            msg = json.loads(raw)
            await responder(ws, msg)

    server = await serve(handler, "127.0.0.1", 0)
    try:
        sock = next(iter(server.sockets))
        port = sock.getsockname()[1]
        yield f"ws://127.0.0.1:{port}"
    finally:
        server.close()
        await server.wait_closed()


async def test_send_returns_result_on_success() -> None:
    async def respond(ws: ServerConnection, msg: dict[str, Any]) -> None:
        await ws.send(json.dumps({"id": msg["id"], "result": {"ok": True}}))

    async with _server(respond) as url:
        cdp = CDPConnection(url)
        await cdp.connect()
        try:
            result = await cdp.send("Runtime.evaluate", {"expression": "1+1"})
            assert result == {"ok": True}
        finally:
            await cdp.close()


async def test_send_raises_on_error_response() -> None:
    async def respond(ws: ServerConnection, msg: dict[str, Any]) -> None:
        await ws.send(
            json.dumps(
                {
                    "id": msg["id"],
                    "error": {"code": -32601, "message": "Method not found"},
                }
            )
        )

    async with _server(respond) as url:
        cdp = CDPConnection(url)
        await cdp.connect()
        try:
            with pytest.raises(CDPError) as exc_info:
                await cdp.send("Bogus.method")
            assert exc_info.value.code == -32601
        finally:
            await cdp.close()


async def test_event_listener_called() -> None:
    received: asyncio.Event = asyncio.Event()

    async def respond(ws: ServerConnection, msg: dict[str, Any]) -> None:
        await ws.send(json.dumps({"id": msg["id"], "result": {}}))
        await ws.send(json.dumps({"method": "Page.loadEventFired", "params": {"timestamp": 1.0}}))

    async with _server(respond) as url:
        cdp = CDPConnection(url)
        await cdp.connect()
        try:
            cdp.on("Page.loadEventFired", lambda _params: received.set())
            await cdp.send("Page.enable")
            await asyncio.wait_for(received.wait(), timeout=2.0)
        finally:
            await cdp.close()


async def test_session_scoped_event_routing() -> None:
    global_calls: list[dict[str, Any]] = []
    session_calls: list[dict[str, Any]] = []

    async def respond(ws: ServerConnection, msg: dict[str, Any]) -> None:
        await ws.send(json.dumps({"id": msg["id"], "result": {}}))
        await ws.send(
            json.dumps(
                {
                    "sessionId": "S1",
                    "method": "Page.loadEventFired",
                    "params": {"from": "S1"},
                }
            )
        )
        await ws.send(
            json.dumps(
                {
                    "sessionId": "S2",
                    "method": "Page.loadEventFired",
                    "params": {"from": "S2"},
                }
            )
        )

    async with _server(respond) as url:
        cdp = CDPConnection(url)
        await cdp.connect()
        try:
            cdp.on("Page.loadEventFired", lambda p: global_calls.append(p))
            cdp.on(
                "Page.loadEventFired",
                lambda p: session_calls.append(p),
                session_id="S1",
            )
            await cdp.send("Page.enable")
            await asyncio.sleep(0.1)
            assert len(global_calls) == 2
            assert len(session_calls) == 1
            assert session_calls[0]["from"] == "S1"
        finally:
            await cdp.close()
