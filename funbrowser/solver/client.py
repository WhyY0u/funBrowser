"""Async client for the funsolver.com captcha API.

The API surface follows the 2captcha / anti-captcha JSON convention
(``POST /createTask`` then poll ``POST /getTaskResult``). If the actual
funsolver.com endpoints diverge, override ``base_url`` or subclass and
override ``_create_task`` / ``_poll`` rather than monkey-patching.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class FunSolverError(Exception):
    """A funsolver.com request failed or returned an error response."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class FunSolverClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.funsolver.com",
        timeout: float = 120.0,
        poll_interval: float = 3.0,
        http_timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._http = httpx.AsyncClient(timeout=http_timeout, transport=transport)

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> FunSolverClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def balance(self) -> float:
        data = await self._post("/getBalance", {"clientKey": self._api_key})
        return float(data.get("balance", 0.0))

    async def solve_turnstile(
        self,
        *,
        sitekey: str,
        page_url: str,
        action: str | None = None,
        cdata: str | None = None,
    ) -> str:
        task: dict[str, Any] = {
            "type": "TurnstileTask",
            "websiteURL": page_url,
            "websiteKey": sitekey,
        }
        if action is not None:
            task["action"] = action
        if cdata is not None:
            task["data"] = cdata
        return await self._solve(task)

    async def solve_recaptcha_v2(
        self,
        *,
        sitekey: str,
        page_url: str,
        invisible: bool = False,
        data_s: str | None = None,
        is_enterprise: bool = False,
    ) -> str:
        """reCAPTCHA v2 — both checkbox and invisible variants.

        ``data_s`` is the value of the ``data-s`` attribute used on
        Google-owned properties; safe to omit elsewhere. ``is_enterprise``
        switches the task type for Enterprise sites.
        """
        if is_enterprise:
            task_type = "RecaptchaV2EnterpriseTaskProxyless"
        else:
            task_type = "RecaptchaV2TaskProxyless"
        task: dict[str, Any] = {
            "type": task_type,
            "websiteURL": page_url,
            "websiteKey": sitekey,
        }
        if invisible:
            task["isInvisible"] = True
        if data_s is not None:
            task["recaptchaDataSValue"] = data_s
        return await self._solve(task)

    async def solve_recaptcha_v3(
        self,
        *,
        sitekey: str,
        page_url: str,
        action: str = "verify",
        min_score: float = 0.7,
        is_enterprise: bool = False,
    ) -> str:
        """reCAPTCHA v3 — score-based, needs the page's expected action name."""
        task_type = (
            "RecaptchaV3EnterpriseTaskProxyless" if is_enterprise else "RecaptchaV3TaskProxyless"
        )
        return await self._solve(
            {
                "type": task_type,
                "websiteURL": page_url,
                "websiteKey": sitekey,
                "pageAction": action,
                "minScore": min_score,
            }
        )

    async def solve_hcaptcha(
        self,
        *,
        sitekey: str,
        page_url: str,
        is_invisible: bool = False,
        enterprise_payload: dict[str, Any] | None = None,
    ) -> str:
        task: dict[str, Any] = {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": sitekey,
        }
        if is_invisible:
            task["isInvisible"] = True
        if enterprise_payload is not None:
            task["enterprisePayload"] = enterprise_payload
        return await self._solve(task)

    async def solve_funcaptcha(
        self,
        *,
        public_key: str,
        page_url: str,
        surl: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> str:
        """FunCaptcha / Arkose Labs.

        ``public_key`` is the value of the widget's ``data-pkey``.
        ``surl`` is the FunCaptcha API URL — required for some setups,
        ``data`` carries additional context the site computes (the
        encrypted ``data`` blob).
        """
        task: dict[str, Any] = {
            "type": "FunCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websitePublicKey": public_key,
        }
        if surl is not None:
            task["funcaptchaApiJSSubdomain"] = surl
        if data is not None:
            task["data"] = data
        return await self._solve(task)

    async def solve_geetest(
        self,
        *,
        gt: str,
        challenge: str,
        page_url: str,
        api_server: str | None = None,
        version: int = 3,
        init_parameters: dict[str, Any] | None = None,
    ) -> str:
        """GeeTest v3/v4.

        For v3: pass ``gt`` and ``challenge`` (both fetched from the
        site's challenge endpoint just before solving). For v4: pass
        ``gt`` as the captchaId and set ``version=4``.
        """
        task: dict[str, Any] = {
            "type": "GeeTestTaskProxyless",
            "websiteURL": page_url,
            "gt": gt,
            "challenge": challenge,
            "version": version,
        }
        if api_server is not None:
            task["geetestApiServerSubdomain"] = api_server
        if init_parameters is not None:
            task["initParameters"] = init_parameters
        return await self._solve(task)

    async def _solve(self, task: dict[str, Any]) -> str:
        task_id = await self._create_task(task)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout
        while True:
            await asyncio.sleep(self._poll_interval)
            data = await self._post(
                "/getTaskResult",
                {"clientKey": self._api_key, "taskId": task_id},
            )
            status = data.get("status")
            if status == "ready":
                token = data.get("solution", {}).get("token")
                if not token:
                    raise FunSolverError("solver returned ready without a token")
                return str(token)
            if loop.time() > deadline:
                raise FunSolverError(f"task {task_id} did not complete within {self._timeout}s")

    async def _create_task(self, task: dict[str, Any]) -> int:
        data = await self._post(
            "/createTask",
            {"clientKey": self._api_key, "task": task},
        )
        task_id = data.get("taskId")
        if not task_id:
            raise FunSolverError("solver did not return a taskId")
        return int(task_id)

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = await self._http.post(f"{self._base}{path}", json=body)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise FunSolverError(f"non-dict response from {path}: {data!r}")
        if data.get("errorId"):
            raise FunSolverError(
                data.get("errorDescription") or data.get("errorCode") or "solver error",
                code=int(data.get("errorId", 0)),
            )
        return data
