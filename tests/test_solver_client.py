"""Unit tests for FunSolverClient using httpx.MockTransport."""

from __future__ import annotations

from collections.abc import Iterable

import httpx
import pytest

from funbrowser.solver import FunSolverClient, FunSolverError


def _client(responses: Iterable[httpx.Response]) -> FunSolverClient:
    iterator = iter(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        return next(iterator)

    transport = httpx.MockTransport(handler)
    return FunSolverClient(
        "test_key",
        transport=transport,
        poll_interval=0.01,
        timeout=5.0,
    )


async def test_solve_turnstile_happy_path() -> None:
    client = _client(
        [
            httpx.Response(200, json={"errorId": 0, "taskId": 12345}),
            httpx.Response(200, json={"errorId": 0, "status": "processing"}),
            httpx.Response(
                200,
                json={
                    "errorId": 0,
                    "status": "ready",
                    "solution": {"token": "0xABC"},
                },
            ),
        ]
    )
    async with client:
        token = await client.solve_turnstile(sitekey="0xKEY", page_url="https://example.com")
        assert token == "0xABC"


async def test_create_task_error_response_raises() -> None:
    client = _client(
        [
            httpx.Response(
                200,
                json={
                    "errorId": 1,
                    "errorCode": "ERROR_KEY_DOES_NOT_EXIST",
                    "errorDescription": "Bad key",
                },
            ),
        ]
    )
    async with client:
        with pytest.raises(FunSolverError) as exc:
            await client.solve_turnstile(sitekey="x", page_url="https://example.com")
        assert "Bad key" in str(exc.value)
        assert exc.value.code == 1


async def test_solve_timeout() -> None:
    # createTask succeeds, but the result polls forever (always "processing").
    responses = [httpx.Response(200, json={"errorId": 0, "taskId": 99})]
    responses.extend(
        httpx.Response(200, json={"errorId": 0, "status": "processing"}) for _ in range(50)
    )
    client = _client(responses)
    # Override timeout to be very short.
    client._timeout = 0.05
    async with client:
        with pytest.raises(FunSolverError) as exc:
            await client.solve_turnstile(sitekey="x", page_url="https://example.com")
        assert "did not complete" in str(exc.value)


async def test_balance() -> None:
    client = _client([httpx.Response(200, json={"errorId": 0, "balance": 12.34})])
    async with client:
        assert await client.balance() == pytest.approx(12.34)


async def test_passes_optional_turnstile_params() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/createTask":
            return httpx.Response(200, json={"errorId": 0, "taskId": 1})
        return httpx.Response(
            200,
            json={"errorId": 0, "status": "ready", "solution": {"token": "ok"}},
        )

    client = FunSolverClient(
        "key",
        transport=httpx.MockTransport(handler),
        poll_interval=0.01,
    )
    async with client:
        await client.solve_turnstile(
            sitekey="K",
            page_url="https://x.com",
            action="login",
            cdata="extra",
        )

    import json

    body = json.loads(captured[0].content)
    task = body["task"]
    assert task["type"] == "TurnstileTask"
    assert task["websiteKey"] == "K"
    assert task["websiteURL"] == "https://x.com"
    assert task["action"] == "login"
    assert task["data"] == "extra"
