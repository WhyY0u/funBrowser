"""Unit tests for the new captcha solver client methods + bridge dispatch."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from funbrowser.solver import FunSolverClient
from funbrowser.solver.bridge import _solve_dispatch


class FakeSolver:
    """Captures the kwargs each solve_* method receives."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def solve_turnstile(self, **kw: Any) -> str:
        self.calls.append(("turnstile", kw))
        return "TS_TOKEN"

    async def solve_recaptcha_v2(self, **kw: Any) -> str:
        self.calls.append(("recaptcha2", kw))
        return "RC2_TOKEN"

    async def solve_recaptcha_v3(self, **kw: Any) -> str:
        self.calls.append(("recaptcha3", kw))
        return "RC3_TOKEN"

    async def solve_hcaptcha(self, **kw: Any) -> str:
        self.calls.append(("hcaptcha", kw))
        return "HC_TOKEN"

    async def solve_funcaptcha(self, **kw: Any) -> str:
        self.calls.append(("funcaptcha", kw))
        return "FC_TOKEN"

    async def solve_geetest(self, **kw: Any) -> str:
        self.calls.append(("geetest", kw))
        return "GT_TOKEN"


async def test_dispatch_routes_each_captcha_type() -> None:
    s = FakeSolver()
    base_url = "https://target.example.com/"
    payloads = [
        {"type": "turnstile", "sitekey": "TS", "url": base_url},
        {
            "type": "recaptcha2",
            "sitekey": "RC2",
            "url": base_url,
            "invisible": True,
            "enterprise": True,
        },
        {
            "type": "recaptcha3",
            "sitekey": "RC3",
            "url": base_url,
            "action": "login",
            "minScore": 0.9,
        },
        {"type": "hcaptcha", "sitekey": "HC", "url": base_url, "invisible": False},
        {"type": "funcaptcha", "sitekey": "FC", "url": base_url, "surl": "https://api.fc.example/"},
        {"type": "geetest", "gt": "GT_KEY", "challenge": "C", "url": base_url, "version": 4},
    ]
    tokens = []
    for p in payloads:
        token = await _solve_dispatch(s, p)  # type: ignore[arg-type]
        tokens.append(token)
    assert tokens == ["TS_TOKEN", "RC2_TOKEN", "RC3_TOKEN", "HC_TOKEN", "FC_TOKEN", "GT_TOKEN"]
    assert [c[0] for c in s.calls] == [
        "turnstile",
        "recaptcha2",
        "recaptcha3",
        "hcaptcha",
        "funcaptcha",
        "geetest",
    ]


async def test_recaptcha_v2_passes_invisible_and_enterprise() -> None:
    s = FakeSolver()
    await _solve_dispatch(
        s,  # type: ignore[arg-type]
        {
            "type": "recaptcha2",
            "sitekey": "K",
            "url": "https://x.com/",
            "invisible": True,
            "enterprise": True,
            "dataS": "extra-s",
        },
    )
    _, kw = s.calls[-1]
    assert kw["invisible"] is True
    assert kw["is_enterprise"] is True
    assert kw["data_s"] == "extra-s"


async def test_recaptcha_v3_passes_action_score_enterprise() -> None:
    s = FakeSolver()
    await _solve_dispatch(
        s,  # type: ignore[arg-type]
        {
            "type": "recaptcha3",
            "sitekey": "K",
            "url": "https://x.com/",
            "action": "signup",
            "minScore": 0.9,
            "enterprise": True,
        },
    )
    _, kw = s.calls[-1]
    assert kw["action"] == "signup"
    assert kw["min_score"] == 0.9
    assert kw["is_enterprise"] is True


async def test_geetest_version_routed() -> None:
    s = FakeSolver()
    await _solve_dispatch(
        s,  # type: ignore[arg-type]
        {
            "type": "geetest",
            "gt": "G",
            "challenge": "C",
            "url": "https://x.com/",
            "version": 4,
        },
    )
    _, kw = s.calls[-1]
    assert kw["version"] == 4


# ── Live solve_* method invocations against a MockTransport ─────────────


def _mock_client(handler: Any) -> FunSolverClient:
    transport = httpx.MockTransport(handler)
    return FunSolverClient("test_key", transport=transport, poll_interval=0.01)


async def test_solve_recaptcha_v2_sends_expected_task_shape() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if request.url.path == "/createTask":
            return httpx.Response(200, json={"errorId": 0, "taskId": 1})
        return httpx.Response(
            200,
            json={"errorId": 0, "status": "ready", "solution": {"token": "TOK"}},
        )

    async with _mock_client(handler) as c:
        tok = await c.solve_recaptcha_v2(
            sitekey="K",
            page_url="https://x.com",
            invisible=True,
            is_enterprise=True,
        )
        assert tok == "TOK"
    task = seen[0]["task"]
    assert task["type"] == "RecaptchaV2EnterpriseTaskProxyless"
    assert task["websiteKey"] == "K"
    assert task["isInvisible"] is True


async def test_solve_recaptcha_v3_sends_action_and_score() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if request.url.path == "/createTask":
            return httpx.Response(200, json={"errorId": 0, "taskId": 2})
        return httpx.Response(
            200,
            json={"errorId": 0, "status": "ready", "solution": {"token": "T"}},
        )

    async with _mock_client(handler) as c:
        await c.solve_recaptcha_v3(
            sitekey="K", page_url="https://x.com", action="signup", min_score=0.85
        )
    task = seen[0]["task"]
    assert task["type"] == "RecaptchaV3TaskProxyless"
    assert task["pageAction"] == "signup"
    assert task["minScore"] == 0.85


async def test_solve_hcaptcha_sends_task_shape() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if request.url.path == "/createTask":
            return httpx.Response(200, json={"errorId": 0, "taskId": 3})
        return httpx.Response(
            200,
            json={"errorId": 0, "status": "ready", "solution": {"token": "T"}},
        )

    async with _mock_client(handler) as c:
        await c.solve_hcaptcha(sitekey="K", page_url="https://x.com")
    assert seen[0]["task"]["type"] == "HCaptchaTaskProxyless"


async def test_solve_funcaptcha_sends_task_shape() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if request.url.path == "/createTask":
            return httpx.Response(200, json={"errorId": 0, "taskId": 4})
        return httpx.Response(
            200,
            json={"errorId": 0, "status": "ready", "solution": {"token": "T"}},
        )

    async with _mock_client(handler) as c:
        await c.solve_funcaptcha(public_key="K", page_url="https://x.com", surl="https://api.fc")
    task = seen[0]["task"]
    assert task["type"] == "FunCaptchaTaskProxyless"
    assert task["websitePublicKey"] == "K"
    assert task["funcaptchaApiJSSubdomain"] == "https://api.fc"


async def test_solve_geetest_sends_task_shape() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if request.url.path == "/createTask":
            return httpx.Response(200, json={"errorId": 0, "taskId": 5})
        return httpx.Response(
            200,
            json={"errorId": 0, "status": "ready", "solution": {"token": "T"}},
        )

    async with _mock_client(handler) as c:
        await c.solve_geetest(gt="GT", challenge="CHALL", page_url="https://x.com", version=4)
    task = seen[0]["task"]
    assert task["type"] == "GeeTestTaskProxyless"
    assert task["gt"] == "GT"
    assert task["challenge"] == "CHALL"
    assert task["version"] == 4


async def test_unsupported_type_raises() -> None:
    s = FakeSolver()
    from funbrowser.solver import FunSolverError

    with pytest.raises(FunSolverError):
        await _solve_dispatch(s, {"type": "vendor_blah"})  # type: ignore[arg-type]
