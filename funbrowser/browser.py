"""Browser — the launched Chrome process plus the CDP control plane."""

from __future__ import annotations

import asyncio
import dataclasses
import shutil
import time
from collections import deque
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

from ._cdp import CDPConnection
from ._flags import merge_flags, mini_flags
from ._launcher import LaunchedBrowser, launch_chrome
from .fingerprint import Fingerprint
from .geo import GeoInfo, lookup_proxy_geo
from .humanly import DEFAULT as DEFAULT_HUMANLY
from .humanly import HumanBehavior
from .proxy import Proxy
from .proxy import parse as parse_proxy
from .solver import FunSolverClient
from .stealth import stealth_flags
from .tab import Tab

if TYPE_CHECKING:
    from .context import BrowserContext as BrowserContextT


def _enrich_with_geo(fp: Fingerprint | None, geo: GeoInfo) -> Fingerprint:
    """Layer a geo lookup into a Fingerprint without clobbering caller values."""
    if fp is None:
        return Fingerprint(
            timezone=geo.timezone or None,
            locale=geo.locale or None,
            accept_language=geo.accept_language or None,
        )
    return dataclasses.replace(
        fp,
        timezone=fp.timezone or geo.timezone or None,
        locale=fp.locale or geo.locale or None,
        accept_language=fp.accept_language or geo.accept_language or None,
    )


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
        geo: GeoInfo | None = None,
    ) -> None:
        self._launched = launched
        self._cdp = cdp
        self._stealth = stealth
        self._fingerprint = fingerprint
        self._proxy = proxy
        self._humanly = humanly
        self._solver_client = solver_client
        self._geo = geo
        self._tabs: dict[str, Tab] = {}
        # Browser-scoped event log — populated by the solver bridge whenever
        # a captcha is attempted. Panel and any other observer can read it.
        self._events: deque[dict[str, Any]] = deque(maxlen=100)
        # Browser contexts (CDP browserContextIds) currently alive on this
        # process. Populated by funbrowser.context._create_context_on,
        # drained by BrowserContext.close.
        self._contexts: set[str] = set()

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

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        """Recent browser-scoped events (most recent first)."""
        return tuple(self._events)

    def record_event(self, **fields: Any) -> None:
        """Append an event to the browser's log. Timestamp added automatically."""
        self._events.appendleft({"ts": time.time(), **fields})

    async def create_context(
        self,
        *,
        proxy: str | Proxy | None = None,
        proxy_bypass: list[str] | None = None,
    ) -> BrowserContextT:
        """Create an isolated :class:`BrowserContext` inside this Browser.

        Cheap (~5-15 MB) compared to launching a fresh Chrome. Each
        context has its own cookies / storage / cache, and optionally
        its own proxy. See :mod:`funbrowser.context` for the trade-offs.
        """
        from .context import _create_context_on

        return await _create_context_on(self, proxy=proxy, proxy_bypass=proxy_bypass)

    @property
    def geo(self) -> GeoInfo | None:
        return self._geo

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
        geo_autoconfigure: bool = True,
        humanly: bool | HumanBehavior = False,
        mini: bool = False,
        api_key: str | None = None,
        auto_solve: bool = True,
        solver_base_url: str | None = None,
        args: Sequence[str] = (),
    ) -> Self:
        parts: list[list[str]] = []
        if stealth:
            parts.append(stealth_flags())
        if mini:
            parts.append(mini_flags())

        proxy_obj: Proxy | None = None
        if proxy is not None:
            proxy_obj = parse_proxy(proxy)
            parts.append([f"--proxy-server={proxy_obj.chrome_arg()}"])

        parts.append(list(args))
        extra = merge_flags(*parts)

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

        # Geo auto-coupling: ask ip-api.com (through the proxy) for the exit
        # IP's timezone + locale, fill any matching fingerprint fields the
        # caller didn't already set. Skip silently on any failure.
        geo: GeoInfo | None = None
        if proxy_obj is not None and geo_autoconfigure:
            geo = await lookup_proxy_geo(proxy_obj)
            if geo is not None:
                fingerprint = _enrich_with_geo(fingerprint, geo)

        return cls(
            launched,
            cdp,
            stealth=stealth,
            fingerprint=fingerprint,
            proxy=proxy_obj,
            humanly=humanly_profile,
            solver_client=solver_client,
            geo=geo,
        )

    @property
    def tabs(self) -> list[Tab]:
        return list(self._tabs.values())

    def get_tabs(self) -> list[Tab]:
        """Same as the ``tabs`` property — provided because some users
        instinctively reach for a method instead of a property."""
        return self.tabs

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

    async def switch_tab(self, tab: Tab | int | str) -> Tab:
        """Bring a tab to the foreground of the browser window and return it.

        Tabs are always independently drivable by their :class:`Tab`
        handle — you do **not** need to switch to a tab to type / click
        / evaluate on it. This method is for the UI side: it sends
        ``Target.activateTarget`` so the tab becomes the visible one
        when you're running headful and watching the window.

        ``tab`` may be:

        - an existing :class:`Tab` instance you already hold
        - an ``int`` — index into :attr:`tabs` (negatives count from the
          end, ``-1`` is the most recently opened tab)
        - a ``str`` — matched as a *substring* of each tab's current
          URL; the first match wins. Handy for "switch to the gmail
          one" without tracking handles.

        Raises :class:`IndexError` for an out-of-range int and
        :class:`LookupError` for a string that matches nothing.
        """
        resolved: Tab
        if isinstance(tab, Tab):
            resolved = tab
        elif isinstance(tab, int):
            resolved = self.tabs[tab]
        else:
            match = next((t for t in self.tabs if tab in t.url), None)
            if match is None:
                raise LookupError(f"No open tab matches URL substring {tab!r}")
            resolved = match
        await self._cdp.send("Target.activateTarget", {"targetId": resolved.target_id})
        return resolved

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

    async def save_cookies(self, path: str | Path) -> int:
        """Dump every cookie to a JSON file. Returns the count saved."""
        import json as _json

        cookies = await self.cookies()
        p = Path(path)
        await asyncio.to_thread(p.write_text, _json.dumps(cookies, indent=2), encoding="utf-8")
        return len(cookies)

    async def load_cookies(self, path: str | Path, *, clear_first: bool = False) -> int:
        """Load cookies from a JSON file produced by :meth:`save_cookies`.

        ``clear_first=True`` wipes existing cookies before applying. Returns
        the count loaded.
        """
        import json as _json

        p = Path(path)
        raw = await asyncio.to_thread(p.read_text, encoding="utf-8")
        cookies = _json.loads(raw)
        if clear_first:
            await self.clear_cookies()
        await self.set_cookies(cookies)
        return len(cookies)

    async def export_state(self, path: str | Path) -> dict[str, int]:
        """Snapshot cookies + per-open-tab localStorage to one JSON file.

        Localstorage is collected per tab whose origin currently has a tab
        open in this browser. Cookies are browser-wide. Returns
        ``{"cookies": N, "origins": M}``.
        """
        import json as _json

        cookies = await self.cookies()
        origins: list[dict[str, Any]] = []
        for tab in self.tabs:
            try:
                url = tab.url
                if not url or url == "about:blank":
                    continue
                ls = await tab.local_storage()
                if ls:
                    origins.append({"url": url, "local_storage": ls})
            except Exception:
                pass

        data = {"version": 1, "cookies": cookies, "origins": origins}
        p = Path(path)
        await asyncio.to_thread(p.write_text, _json.dumps(data, indent=2), encoding="utf-8")
        return {"cookies": len(cookies), "origins": len(origins)}

    async def import_state(
        self,
        path: str | Path,
        *,
        navigate: bool = True,
        clear_first: bool = False,
    ) -> dict[str, int]:
        """Restore cookies + localStorage from a :meth:`export_state` file.

        ``navigate=True`` (default) opens a tab on each saved origin and
        re-applies its localStorage there — required because Chrome won't
        let you write localStorage for an origin you haven't loaded.
        Pass ``navigate=False`` for cookies-only restore.
        Returns ``{"cookies": N, "origins": M}``.
        """
        import json as _json

        p = Path(path)
        raw = await asyncio.to_thread(p.read_text, encoding="utf-8")
        data = _json.loads(raw)
        cookies = data.get("cookies", [])
        origins = data.get("origins", [])

        if clear_first:
            await self.clear_cookies()
        await self.set_cookies(cookies)

        applied = 0
        if navigate:
            for entry in origins:
                url = entry.get("url")
                ls = entry.get("local_storage") or {}
                if not url or not ls:
                    continue
                try:
                    tab = await self.new_tab(url=url)
                    await tab.goto(url)
                    await tab.set_local_storage(ls)
                    applied += 1
                except Exception:
                    pass
        return {"cookies": len(cookies), "origins": applied}

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
