"""Browser — the launched Chrome process plus the CDP control plane."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from ._cdp import CDPConnection
from ._launcher import LaunchedBrowser, launch_chrome
from .fingerprint import Fingerprint
from .humanly import DEFAULT as DEFAULT_HUMANLY
from .humanly import HumanBehavior
from .proxy import Proxy
from .proxy import parse as parse_proxy
from .solver import FunSolverClient
from .stealth import stealth_flags
from .tab import Tab


class Browser:
    def __init__(
        self,
        launched: LaunchedBrowser,
        cdp: CDPConnection,
        *,
        stealth: bool = True,
        fingerprint: Fingerprint | None = None,
        proxy: Proxy | None = None,
        humanly: HumanBehavior | None = None,
        solver_client: FunSolverClient | None = None,
    ) -> None:
        self._launched = launched
        self._cdp = cdp
        self._stealth = stealth
        self._fingerprint = fingerprint
        self._proxy = proxy
        self._humanly = humanly
        self._solver_client = solver_client
        self._tabs: dict[str, Tab] = {}

    @property
    def stealth_enabled(self) -> bool:
        return self._stealth

    @property
    def fingerprint(self) -> Fingerprint | None:
        return self._fingerprint

    @property
    def proxy(self) -> Proxy | None:
        return self._proxy

    @property
    def auto_solve_enabled(self) -> bool:
        return self._solver_client is not None

    @property
    def solver_client(self) -> FunSolverClient | None:
        return self._solver_client

    @property
    def humanly(self) -> HumanBehavior | None:
        return self._humanly

    @classmethod
    async def start(
        cls,
        *,
        executable: str | Path | None = None,
        user_data_dir: str | Path | None = None,
        headless: bool = False,
        stealth: bool = True,
        fingerprint: Fingerprint | None = None,
        proxy: str | Proxy | None = None,
        humanly: bool | HumanBehavior = False,
        api_key: str | None = None,
        auto_solve: bool = True,
        solver_base_url: str | None = None,
        args: Sequence[str] = (),
    ) -> Self:
        extra: list[str] = list(args)
        if stealth:
            extra = [*stealth_flags(), *extra]

        proxy_obj: Proxy | None = None
        if proxy is not None:
            proxy_obj = parse_proxy(proxy)
            extra.append(f"--proxy-server={proxy_obj.chrome_arg()}")

        launched = await launch_chrome(
            executable=Path(executable) if executable else None,
            user_data_dir=Path(user_data_dir) if user_data_dir else None,
            headless=headless,
            extra_args=extra,
        )
        cdp = CDPConnection(launched.ws_url)
        await cdp.connect()

        solver_client: FunSolverClient | None = None
        if api_key and auto_solve:
            if solver_base_url:
                solver_client = FunSolverClient(api_key, base_url=solver_base_url)
            else:
                solver_client = FunSolverClient(api_key)

        humanly_profile: HumanBehavior | None
        if humanly is True:
            humanly_profile = DEFAULT_HUMANLY
        elif humanly is False:
            humanly_profile = None
        elif isinstance(humanly, HumanBehavior):
            humanly_profile = humanly
        else:
            humanly_profile = None

        return cls(
            launched,
            cdp,
            stealth=stealth,
            fingerprint=fingerprint,
            proxy=proxy_obj,
            humanly=humanly_profile,
            solver_client=solver_client,
        )

    @property
    def tabs(self) -> list[Tab]:
        return list(self._tabs.values())

    async def new_tab(self, url: str = "about:blank") -> Tab:
        res = await self._cdp.send("Target.createTarget", {"url": url})
        target_id = res["targetId"]
        attach = await self._cdp.send(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        session_id = attach["sessionId"]
        tab = Tab(self, target_id, session_id)
        await tab._initialize()
        self._tabs[target_id] = tab
        return tab

    async def get(self, url: str, *, wait_until: str = "load") -> Tab:
        tab = await self.new_tab(url="about:blank")
        await tab.goto(url, wait_until=wait_until)
        return tab

    def _on_tab_closed(self, tab: Tab) -> None:
        self._tabs.pop(tab.target_id, None)

    # ── cookie store (browser-wide) ───────────────────────────────────

    async def cookies(self) -> list[dict[str, Any]]:
        """Every cookie the browser is currently holding."""
        result = await self._cdp.send("Storage.getCookies")
        return list(result.get("cookies", []))

    async def set_cookies(self, cookies: Sequence[dict[str, Any]]) -> None:
        """Add or overwrite cookies. Same dict shape as :meth:`cookies` returns."""
        await self._cdp.send("Storage.setCookies", {"cookies": list(cookies)})

    async def clear_cookies(self) -> None:
        """Wipe every cookie. Useful between tests."""
        await self._cdp.send("Storage.clearCookies")

    async def stop(self) -> None:
        for tab in list(self._tabs.values()):
            try:
                await tab.close()
            except Exception:
                pass
        await self._cdp.close()
        if self._solver_client is not None:
            try:
                await self._solver_client.close()
            except Exception:
                pass
        proc = self._launched.process
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        if self._launched.user_data_dir_is_tmp:
            shutil.rmtree(self._launched.user_data_dir, ignore_errors=True)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.stop()
