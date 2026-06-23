"""Local web panel for inspecting and controlling a :class:`BrowserPool`.

Optional dependency — install via ``pip install funbrowser[panel]`` (pulls
in ``aiohttp``). Without the extras installed, importing :class:`Panel`
raises ``ImportError`` immediately so the rest of FunBrowser stays
dependency-light.

Usage::

    async with BrowserPool(size=3) as pool:
        async with Panel(pool) as panel:
            print(panel.url)              # http://127.0.0.1:8765
            await long_running_task()

The dashboard is a single-page HTML+JS app embedded in this module — no
build step, no external assets — that polls ``/api/state`` once per
second.
"""

from __future__ import annotations

import json
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

try:
    from aiohttp import web
except ImportError as _import_error:
    web = None  # type: ignore[assignment]
    _IMPORT_ERROR: ImportError | None = _import_error
else:
    _IMPORT_ERROR = None

if TYPE_CHECKING:
    from aiohttp.web import Application, AppRunner, Request, Response, TCPSite

    from .pool import BrowserPool


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FunBrowser Panel</title>
<style>
  body { font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; background: #0b0d12; color: #e5e7eb; padding: 24px; }
  h1 { font-size: 22px; margin: 0 0 16px 0; font-weight: 600; }
  .stats { display: flex; gap: 16px; margin-bottom: 24px; }
  .card { background: #161922; border: 1px solid #232735; border-radius: 8px;
          padding: 14px 18px; min-width: 90px; }
  .card .label { font-size: 11px; text-transform: uppercase; color: #6b7280;
                 letter-spacing: 0.06em; }
  .card .value { font-size: 22px; font-weight: 600; margin-top: 2px; }
  table { width: 100%; border-collapse: collapse; background: #161922;
          border: 1px solid #232735; border-radius: 8px; overflow: hidden; }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #232735; }
  th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
       color: #6b7280; background: #11141c; }
  tr:last-child td { border-bottom: none; }
  td.idx { font-weight: 600; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 4px;
          background: #232735; font-size: 12px; }
  .pill.geo { background: #1e3a8a; color: #dbeafe; }
  input { background: #0b0d12; color: #e5e7eb; border: 1px solid #232735;
          border-radius: 4px; padding: 4px 8px; font: inherit; width: 280px; }
  button { background: #2563eb; color: white; border: none; border-radius: 4px;
           padding: 4px 12px; font: inherit; cursor: pointer; }
  button:hover { background: #1d4ed8; }
  .ghost { font-style: italic; color: #6b7280; }
  .row-actions { display: flex; gap: 6px; align-items: center; }
  a { color: #93c5fd; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
</head>
<body>
<h1>FunBrowser pool</h1>
<div class="stats" id="stats"></div>
<table>
  <thead>
    <tr>
      <th>#</th>
      <th>Proxy</th>
      <th>Geo</th>
      <th>Fingerprint</th>
      <th>Tabs</th>
      <th>Action</th>
    </tr>
  </thead>
  <tbody id="rows"></tbody>
</table>
<script>
const fmtPill = (text, klass = "") =>
  text ? `<span class="pill ${klass}">${text}</span>` : `<span class="ghost">—</span>`;

async function refresh() {
  const r = await fetch("/api/state");
  if (!r.ok) return;
  const data = await r.json();
  const p = data.pool;
  document.getElementById("stats").innerHTML = `
    <div class="card"><div class="label">size</div><div class="value">${p.size}</div></div>
    <div class="card"><div class="label">created</div><div class="value">${p.created}</div></div>
    <div class="card"><div class="label">busy</div><div class="value">${p.busy}</div></div>
    <div class="card"><div class="label">idle</div><div class="value">${p.idle}</div></div>
  `;
  const rows = data.browsers.map((b) => {
    const tabsHtml = b.tabs.length
      ? b.tabs.map((t) => `<div>${t.url || "—"}</div>`).join("")
      : '<span class="ghost">no tabs</span>';
    return `
      <tr>
        <td class="idx">#${b.index}</td>
        <td>${fmtPill(b.proxy)}</td>
        <td>${fmtPill(b.geo, "geo")}</td>
        <td>${fmtPill(b.fingerprint)}</td>
        <td>${tabsHtml}</td>
        <td>
          <form class="row-actions" onsubmit="goto(event, ${b.index})">
            <input name="url" placeholder="https://…" required>
            <button type="submit">go</button>
            <a href="/api/browser/${b.index}/screenshot" target="_blank">screenshot</a>
          </form>
        </td>
      </tr>`;
  });
  document.getElementById("rows").innerHTML = rows.join("");
}

async function goto(e, idx) {
  e.preventDefault();
  const url = e.target.url.value;
  await fetch(`/api/browser/${idx}/goto`, {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({url}),
  });
  refresh();
}

refresh();
setInterval(refresh, 1500);
</script>
</body>
</html>
"""


class Panel:
    def __init__(
        self,
        pool: BrowserPool,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        if web is None:
            raise ImportError(
                "Panel requires aiohttp. Install with `pip install funbrowser[panel]`."
            ) from _IMPORT_ERROR
        self._pool = pool
        self._host = host
        self._port = port
        self._app: Application = web.Application()
        self._app.router.add_get("/", self._index)
        self._app.router.add_get("/api/state", self._api_state)
        self._app.router.add_post("/api/browser/{idx}/goto", self._api_goto)
        self._app.router.add_get("/api/browser/{idx}/screenshot", self._api_screenshot)
        self._runner: AppRunner | None = None
        self._site: TCPSite | None = None

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    async def start(self) -> None:
        assert web is not None
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
            self._site = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.stop()

    # ── routes ────────────────────────────────────────────────────────

    async def _index(self, _request: Request) -> Response:
        assert web is not None
        return web.Response(text=INDEX_HTML, content_type="text/html")

    async def _api_state(self, _request: Request) -> Response:
        assert web is not None
        browsers = []
        for i, b in enumerate(self._pool.browsers):
            tabs = [{"url": t.url} for t in b.tabs]
            browsers.append(
                {
                    "index": i,
                    "proxy": (f"{b.proxy.host}:{b.proxy.port}" if b.proxy is not None else None),
                    "geo": b.geo.country_code if b.geo is not None else None,
                    "fingerprint": (b.fingerprint.label if b.fingerprint is not None else None),
                    "tabs": tabs,
                }
            )
        return web.json_response(
            {
                "pool": {
                    "size": self._pool.size,
                    "created": self._pool.created,
                    "busy": self._pool.busy,
                    "idle": self._pool.idle,
                },
                "browsers": browsers,
            }
        )

    async def _api_goto(self, request: Request) -> Response:
        assert web is not None
        idx = int(request.match_info["idx"])
        try:
            data: dict[str, Any] = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "bad json"}, status=400)
        url = data.get("url")
        if not isinstance(url, str) or not url:
            return web.json_response({"error": "missing url"}, status=400)
        browsers = list(self._pool.browsers)
        if not 0 <= idx < len(browsers):
            return web.json_response({"error": "unknown browser"}, status=404)
        browser = browsers[idx]
        tab = browser.tabs[0] if browser.tabs else await browser.new_tab()
        await tab.goto(url)
        return web.json_response({"ok": True, "url": url})

    async def _api_screenshot(self, request: Request) -> Response:
        assert web is not None
        idx = int(request.match_info["idx"])
        browsers = list(self._pool.browsers)
        if not 0 <= idx < len(browsers):
            return web.Response(status=404, text="unknown browser")
        browser = browsers[idx]
        if not browser.tabs:
            return web.Response(status=404, text="no tabs in this browser")
        png = await browser.tabs[0].screenshot()
        return web.Response(body=png, content_type="image/png")
