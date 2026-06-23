"""Local web panel for inspecting and controlling a :class:`BrowserPool`.

Optional dependency — install via ``pip install funbrowser[panel]`` (pulls
in ``aiohttp``). Without the extras installed, importing :class:`Panel`
raises ``ImportError`` immediately so the rest of FunBrowser stays
dependency-light.

Usage::

    async with BrowserPool(size=5) as pool:
        async with Panel(pool) as panel:
            print(panel.url)              # http://127.0.0.1:8765
            await long_running_task()

The dashboard is a single-page HTML+JS app embedded in this module — no
build step, no external assets — that polls ``/api/state`` once per
second. Designed for farm operators: bulk goto, per-browser controls,
running activity log, success-rate / avg-time stats.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
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

    from .browser import Browser
    from .pool import BrowserPool


@dataclass
class ScriptRun:
    """One execution of an uploaded script against one (or every) browser."""

    id: int
    name: str
    code: str
    target: str  # "all" or a browser-index string like "3"
    browsers: list[int]  # the browser indices this run touches
    status: str = "queued"  # queued | running | ok | fail
    started_at: float = 0.0
    ended_at: float | None = None
    # Per-browser output: index -> {"ok", "output", "error", "result", "ms"}
    results: dict[int, dict[str, Any]] = field(default_factory=dict)


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FunBrowser Pool</title>
<style>
  :root {
    --bg: #000000;
    --bg-card: #0d0d0d;
    --bg-card-2: #141414;
    --border: #262626;
    --border-soft: #1a1a1a;
    --text: #ffffff;
    --text-dim: #a8a8a8;
    --text-soft: #5a5a5a;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text);
               font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI",
                     Roboto, "Helvetica Neue", sans-serif; }
  .container { max-width: 1440px; margin: 0 auto; padding: 32px 32px 80px; }

  .header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 28px;
            padding-bottom: 20px; border-bottom: 1px solid var(--border-soft); }
  .header h1 { font-size: 18px; font-weight: 600; margin: 0;
               letter-spacing: -0.01em; }
  .header .sub { color: var(--text-soft); font-size: 13px; }
  .header .right { margin-left: auto; color: var(--text-soft); font-size: 12px;
                   font-family: ui-monospace, "SF Mono", Menlo, monospace; }

  .stats-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px;
                margin-bottom: 28px; }
  .stat-card { background: var(--bg-card); border: 1px solid var(--border);
               border-radius: 8px; padding: 18px 20px; }
  .stat-card .label { font-size: 11px; color: var(--text-soft);
                      letter-spacing: 0.05em; text-transform: uppercase;
                      margin-bottom: 10px; }
  .stat-card .value { font-size: 28px; font-weight: 700; letter-spacing: -0.01em;
                      color: var(--text); }
  .stat-card .unit { font-size: 13px; font-weight: 500; color: var(--text-soft);
                     margin-left: 4px; }

  .main { display: grid; grid-template-columns: 1fr 340px; gap: 16px; }
  .panel { background: var(--bg-card); border: 1px solid var(--border);
           border-radius: 8px; overflow: hidden; }
  .panel-head { padding: 14px 20px; border-bottom: 1px solid var(--border-soft);
                display: flex; align-items: center; justify-content: space-between; }
  .panel-head h2 { margin: 0; font-size: 12px; font-weight: 600;
                   color: var(--text); text-transform: uppercase;
                   letter-spacing: 0.06em; }
  .panel-head .badge { font-size: 11px; color: var(--text-soft);
                       font-family: ui-monospace, "SF Mono", Menlo, monospace; }

  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 11px 16px; text-align: left;
           border-bottom: 1px solid var(--border-soft); font-size: 13px; }
  th { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em;
       color: var(--text-soft); font-weight: 500; background: var(--bg-card-2); }
  tr:last-child td { border-bottom: none; }
  td.idx { font-weight: 600; color: var(--text);
           font-family: ui-monospace, "SF Mono", Menlo, monospace; }
  td.url { font-family: ui-monospace, "SF Mono", Menlo, monospace;
           font-size: 12px; color: var(--text-dim);
           max-width: 320px; overflow: hidden; text-overflow: ellipsis;
           white-space: nowrap; }
  td.status { font-family: ui-monospace, "SF Mono", Menlo, monospace;
              font-size: 11px; color: var(--text-dim);
              text-transform: uppercase; letter-spacing: 0.04em; }
  td.status.busy { color: var(--text); }

  .pill { display: inline-block; padding: 2px 8px; border-radius: 3px;
          background: var(--bg-card-2); color: var(--text-dim); font-size: 11px;
          font-family: ui-monospace, "SF Mono", Menlo, monospace;
          border: 1px solid var(--border-soft); }
  .pill.solid { background: var(--text); color: var(--bg);
                border-color: var(--text); font-weight: 600; }
  .ghost { color: var(--text-soft); }

  input, button { font: inherit; }
  input[type=text], input[type=url] {
    background: var(--bg-card-2); color: var(--text);
    border: 1px solid var(--border); border-radius: 4px;
    padding: 6px 10px; font-size: 12px; outline: none;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }
  input[type=text]:focus, input[type=url]:focus { border-color: var(--text-dim); }
  button {
    background: transparent; color: var(--text);
    border: 1px solid var(--border); border-radius: 4px;
    padding: 6px 14px; font-size: 12px; cursor: pointer;
    transition: background 0.08s ease, color 0.08s ease;
    text-transform: uppercase; letter-spacing: 0.05em; font-weight: 500;
  }
  button:hover { background: var(--text); color: var(--bg); border-color: var(--text); }
  button.solid { background: var(--text); color: var(--bg); border-color: var(--text); }
  button.solid:hover { background: var(--text-dim); border-color: var(--text-dim); }

  .row-actions { display: flex; gap: 6px; align-items: center; }
  .row-actions input { width: 200px; }
  .row-actions a { font-size: 11px; color: var(--text-soft); text-decoration: none;
                   text-transform: uppercase; letter-spacing: 0.05em;
                   padding: 0 6px; }
  .row-actions a:hover { color: var(--text); }

  .actions-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
                  padding: 14px 20px; }
  .actions-grid button { padding: 10px; font-size: 11px; }

  .sys-row { display: flex; justify-content: space-between; align-items: center;
             padding: 11px 20px; border-bottom: 1px solid var(--border-soft);
             font-size: 13px; }
  .sys-row:last-child { border-bottom: none; }
  .sys-row .key { color: var(--text-soft); font-size: 11px;
                  text-transform: uppercase; letter-spacing: 0.05em; }
  .sys-row .val { font-family: ui-monospace, "SF Mono", Menlo, monospace;
                  font-size: 12px; color: var(--text); }

  .log { padding: 0; max-height: 260px; overflow-y: auto; }
  .log-row { display: grid; grid-template-columns: 64px 56px 1fr 44px 60px;
             gap: 12px; padding: 7px 20px;
             border-bottom: 1px solid var(--border-soft);
             font-family: ui-monospace, "SF Mono", Menlo, monospace;
             font-size: 11px; align-items: center; }
  .log-row:last-child { border-bottom: none; }
  .log-row .t { color: var(--text-soft); }
  .log-row .b { color: var(--text); }
  .log-row .u { color: var(--text-dim); overflow: hidden; text-overflow: ellipsis;
                white-space: nowrap; }
  .log-row .s { text-transform: uppercase; letter-spacing: 0.06em; }
  .log-row .s.ok { color: var(--text); }
  .log-row .s.err { color: var(--text-soft); text-decoration: line-through; }
  .log-row .d { color: var(--text-soft); text-align: right; }

  .stack { display: flex; flex-direction: column; gap: 16px; }

  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.85);
              display: none; align-items: center; justify-content: center;
              z-index: 50; }
  .modal-bg.open { display: flex; }
  .modal { background: var(--bg-card); border: 1px solid var(--border);
           border-radius: 8px; padding: 24px; min-width: 420px; max-width: 90vw; }
  .modal h3 { margin: 0 0 16px 0; font-size: 12px; text-transform: uppercase;
              letter-spacing: 0.08em; font-weight: 600; }
  .modal .field { margin-bottom: 16px; }
  .modal .field label { display: block; margin-bottom: 6px; font-size: 11px;
                        color: var(--text-soft); text-transform: uppercase;
                        letter-spacing: 0.05em; }
  .modal .field input { width: 100%; padding: 10px; font-size: 13px; }
  .modal .row { display: flex; gap: 10px; justify-content: flex-end; }
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>FunBrowser</h1>
    <span class="sub">browser pool</span>
    <div class="right"><span id="hdr-uptime">up 0s</span></div>
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="label">Total Requests</div>
      <div class="value" id="stat-total">0</div>
    </div>
    <div class="stat-card">
      <div class="label">Success Rate</div>
      <div class="value"><span id="stat-success">0</span><span class="unit">%</span></div>
    </div>
    <div class="stat-card">
      <div class="label">Avg Response</div>
      <div class="value"><span id="stat-avg">0</span><span class="unit">ms</span></div>
    </div>
    <div class="stat-card">
      <div class="label">Browsers</div>
      <div class="value"><span id="stat-browsers">0</span><span class="unit" id="stat-browsers-cap">/0</span></div>
    </div>
    <div class="stat-card">
      <div class="label">Tabs</div>
      <div class="value" id="stat-tabs">0</div>
    </div>
    <div class="stat-card">
      <div class="label">FunSolver Balance</div>
      <div class="value"><span id="stat-balance">—</span><span class="unit" id="stat-balance-unit"></span></div>
    </div>
  </div>

  <div class="main">

    <div class="stack">
      <div class="panel">
        <div class="panel-head">
          <h2>Browser Fleet</h2>
          <span class="badge" id="fleet-status">—</span>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width:48px">#</th>
              <th style="width:72px">Status</th>
              <th>Proxy</th>
              <th style="width:60px">Geo</th>
              <th>Fingerprint</th>
              <th>Current</th>
              <th style="width:320px">Action</th>
            </tr>
          </thead>
          <tbody id="rows"><tr><td colspan="7" class="ghost" style="padding:24px;text-align:center">loading</td></tr></tbody>
        </table>
      </div>

      <div class="panel">
        <div class="panel-head">
          <h2>Activity</h2>
          <span class="badge" id="log-count">0 events</span>
        </div>
        <div class="log" id="log"><div style="padding:20px" class="ghost">no events yet</div></div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <h2>Scripts</h2>
          <span class="badge">async def main(browser)</span>
        </div>
        <div style="padding:16px 20px">
          <textarea id="script-code" rows="9" placeholder="async def main(browser):
    tab = await browser.get('https://example.com')
    print(await tab.evaluate('document.title'))
    return tab.url"
          style="width:100%;font-family:ui-monospace,'SF Mono',Menlo,monospace;
                 font-size:12px;background:var(--bg-card-2);color:var(--text);
                 border:1px solid var(--border);border-radius:4px;padding:10px;
                 outline:none;resize:vertical;"></textarea>
          <div style="display:flex;gap:8px;margin-top:10px;align-items:center;
                      flex-wrap:wrap;">
            <input id="script-name" placeholder="script.py" style="width:140px">
            <input id="script-target" placeholder="all or 0,1,2…" value="all" style="width:120px">
            <button class="solid" onclick="submitScript()">Run</button>
            <label class="ghost" style="font-size:11px;cursor:pointer;
                                         text-transform:uppercase;letter-spacing:0.05em;
                                         padding:6px 10px;border:1px solid var(--border);
                                         border-radius:4px">
              Load .py
              <input type="file" id="script-file" accept=".py,.txt"
                     onchange="loadFile(event)" style="display:none">
            </label>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <h2>Recent Script Runs</h2>
          <span class="badge" id="runs-count">0</span>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width:48px">#</th>
              <th>Name</th>
              <th style="width:72px">Target</th>
              <th style="width:80px">Status</th>
              <th style="width:90px">Result</th>
              <th style="width:80px">Duration</th>
              <th style="width:60px"></th>
            </tr>
          </thead>
          <tbody id="runs"><tr><td colspan="7" class="ghost" style="padding:24px;text-align:center">no runs yet</td></tr></tbody>
        </table>
      </div>
    </div>

    <div class="stack">
      <div class="panel">
        <div class="panel-head"><h2>Quick Actions</h2></div>
        <div class="actions-grid">
          <button class="solid" onclick="openGotoAll()">Navigate all</button>
          <button onclick="openNewTab()">New tab</button>
          <button onclick="openSettings()">Settings</button>
          <button onclick="manualRefresh()">Refresh</button>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head"><h2>System</h2></div>
        <div class="sys-row"><span class="key">API</span><span class="val">ONLINE</span></div>
        <div class="sys-row"><span class="key">Avg time</span><span class="val" id="sys-avg">0ms</span></div>
        <div class="sys-row"><span class="key">Browsers</span><span class="val" id="sys-browsers">0/0</span></div>
        <div class="sys-row"><span class="key">Tabs</span><span class="val" id="sys-tabs">0</span></div>
        <div class="sys-row"><span class="key">Today</span><span class="val" id="sys-today">0 req</span></div>
        <div class="sys-row"><span class="key">Solver</span><span class="val" id="sys-solver">—</span></div>
        <div class="sys-row"><span class="key">Captchas</span><span class="val" id="sys-captchas">0 / 0</span></div>
        <div class="sys-row"><span class="key">Uptime</span><span class="val" id="sys-uptime">0s</span></div>
      </div>
    </div>
  </div>
</div>

<div class="modal-bg" id="modal-goto">
  <div class="modal">
    <h3>Navigate every browser</h3>
    <div class="field">
      <label>URL</label>
      <input type="url" id="goto-all-url" placeholder="https://example.com" autofocus>
    </div>
    <div class="row">
      <button onclick="closeModals()">Cancel</button>
      <button class="solid" onclick="submitGotoAll()">Navigate</button>
    </div>
  </div>
</div>

<div class="modal-bg" id="modal-newtab">
  <div class="modal">
    <h3>Open new tab</h3>
    <div class="field">
      <label>Browser index</label>
      <input type="text" id="newtab-idx" value="0">
    </div>
    <div class="field">
      <label>URL (optional)</label>
      <input type="url" id="newtab-url" placeholder="about:blank">
    </div>
    <div class="row">
      <button onclick="closeModals()">Cancel</button>
      <button class="solid" onclick="submitNewTab()">Open</button>
    </div>
  </div>
</div>

<div class="modal-bg" id="modal-settings">
  <div class="modal">
    <h3>Settings</h3>
    <pre id="settings-body" style="background:var(--bg-card-2);border-radius:4px;
         padding:14px;font-size:12px;max-height:300px;overflow:auto;
         color:var(--text-dim);border:1px solid var(--border-soft)">loading</pre>
    <div class="row">
      <button onclick="closeModals()">Close</button>
    </div>
  </div>
</div>

<div class="modal-bg" id="modal-run">
  <div class="modal" style="min-width:680px;max-width:90vw">
    <h3 id="run-title">Run #—</h3>
    <div id="run-body" style="max-height:60vh;overflow:auto"></div>
    <div class="row" style="margin-top:16px">
      <button onclick="closeModals()">Close</button>
    </div>
  </div>
</div>

<script>
const escapeHtml = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const fmtPill = (text, solid = false) =>
  text ? `<span class="pill ${solid ? 'solid' : ''}">${escapeHtml(text)}</span>` : `<span class="ghost">—</span>`;
function fmtMs(ms) {
  if (ms < 1000) return Math.round(ms) + "ms";
  return (ms / 1000).toFixed(1) + "s";
}
function fmtUptime(s) {
  s = Math.floor(s);
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m " + (s % 60) + "s";
  return Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
}
function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toTimeString().slice(0, 8);
}

async function refresh() {
  let r;
  try { r = await fetch("/api/state"); } catch (e) { return; }
  if (!r.ok) return;
  const data = await r.json();
  const p = data.pool;
  const s = data.stats || {total:0, success:0, avg_ms:0, uptime_s:0};

  document.getElementById("hdr-uptime").textContent = "up " + fmtUptime(s.uptime_s);

  document.getElementById("stat-total").textContent = s.total;
  const rate = s.total > 0 ? Math.round((s.success / s.total) * 1000) / 10 : 0;
  document.getElementById("stat-success").textContent = rate;
  document.getElementById("stat-avg").textContent = Math.round(s.avg_ms);
  document.getElementById("stat-browsers").textContent = p.created;
  document.getElementById("stat-browsers-cap").textContent = "/" + p.size;
  const totalTabs = data.browsers.reduce((acc, b) => acc + b.tabs.length, 0);
  document.getElementById("stat-tabs").textContent = totalTabs;

  document.getElementById("sys-avg").textContent = Math.round(s.avg_ms) + "ms";
  document.getElementById("sys-browsers").textContent = p.created + "/" + p.size;
  document.getElementById("sys-tabs").textContent = totalTabs;
  document.getElementById("sys-today").textContent = s.total + " req";
  document.getElementById("sys-uptime").textContent = fmtUptime(s.uptime_s);
  document.getElementById("fleet-status").textContent =
    p.busy + " busy / " + p.idle + " idle";

  // FunSolver balance + captcha tally
  const solver = data.solver || {available:false, balance:null};
  if (!solver.available) {
    document.getElementById("stat-balance").textContent = "n/a";
    document.getElementById("stat-balance-unit").textContent = "";
    document.getElementById("sys-solver").textContent = "OFF";
  } else if (solver.balance === null) {
    document.getElementById("stat-balance").textContent = "…";
    document.getElementById("stat-balance-unit").textContent = "";
    document.getElementById("sys-solver").textContent = "ON";
  } else {
    document.getElementById("stat-balance").textContent = solver.balance.toFixed(2);
    document.getElementById("stat-balance-unit").textContent = "$";
    document.getElementById("sys-solver").textContent = "ON";
  }
  const caps = data.captchas || {total:0, success:0};
  document.getElementById("sys-captchas").textContent =
    caps.success + " / " + caps.total;

  if (data.browsers.length === 0) {
    document.getElementById("rows").innerHTML =
      `<tr><td colspan="7" class="ghost" style="padding:24px;text-align:center">
        no browsers spawned yet
      </td></tr>`;
  } else {
    const rows = data.browsers.map((b) => {
      const statusLabel = b.busy ? "busy" : "idle";
      const statusClass = b.busy ? "status busy" : "status";
      const currentUrl = b.tabs.length ? b.tabs[0].url : "—";
      return `
        <tr>
          <td class="idx">#${b.index}</td>
          <td class="${statusClass}">${statusLabel}</td>
          <td>${fmtPill(b.proxy)}</td>
          <td>${fmtPill(b.geo, true)}</td>
          <td>${fmtPill(b.fingerprint)}</td>
          <td class="url" title="${escapeHtml(currentUrl)}">${escapeHtml(currentUrl)}</td>
          <td>
            <form class="row-actions" onsubmit="rowGoto(event, ${b.index})">
              <input type="url" name="url" placeholder="https://…" required>
              <button type="submit" class="solid">Go</button>
              <a href="/api/browser/${b.index}/screenshot" target="_blank">shot</a>
            </form>
          </td>
        </tr>`;
    });
    document.getElementById("rows").innerHTML = rows.join("");
  }

  const events = data.events || [];
  document.getElementById("log-count").textContent = events.length + " events";
  if (events.length === 0) {
    document.getElementById("log").innerHTML =
      `<div style="padding:20px" class="ghost">no events yet</div>`;
  } else {
    const logHtml = events.map((e) => {
      // captcha events carry kind="captcha"; nav events carry action="goto" etc.
      let label;
      if (e.kind === "captcha") {
        const captcha = (e.captcha || "?").toUpperCase();
        const detail = e.ok
          ? `solved ${captcha}`
          : `failed ${captcha}: ${e.error || ""}`;
        label = detail + (e.url ? "  ·  " + e.url : "");
      } else {
        label = (e.action || "?") + (e.url ? "  ·  " + e.url : "");
      }
      return `
        <div class="log-row">
          <span class="t">${fmtTime(e.ts)}</span>
          <span class="b">#${e.browser}</span>
          <span class="u" title="${escapeHtml(label)}">${escapeHtml(label)}</span>
          <span class="s ${e.ok ? 'ok' : 'err'}">${e.ok ? 'OK' : 'FAIL'}</span>
          <span class="d">${fmtMs(e.ms || 0)}</span>
        </div>`;
    }).join("");
    document.getElementById("log").innerHTML = logHtml;
  }
}

async function rowGoto(e, idx) {
  e.preventDefault();
  const url = e.target.url.value;
  await fetch(`/api/browser/${idx}/goto`, {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({url}),
  });
  e.target.url.value = "";
  refresh();
}

function openGotoAll() { document.getElementById("modal-goto").classList.add("open"); }
function openNewTab() { document.getElementById("modal-newtab").classList.add("open"); }
async function openSettings() {
  document.getElementById("modal-settings").classList.add("open");
  const r = await fetch("/api/settings");
  document.getElementById("settings-body").textContent = JSON.stringify(await r.json(), null, 2);
}
function closeModals() {
  document.querySelectorAll(".modal-bg").forEach(el => el.classList.remove("open"));
}
async function submitGotoAll() {
  const url = document.getElementById("goto-all-url").value;
  if (!url) return;
  await fetch("/api/goto-all", {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({url}),
  });
  closeModals();
  refresh();
}
async function submitNewTab() {
  const idx = parseInt(document.getElementById("newtab-idx").value, 10);
  const url = document.getElementById("newtab-url").value || "about:blank";
  await fetch(`/api/browser/${idx}/new-tab`, {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({url}),
  });
  closeModals();
  refresh();
}
function manualRefresh() { refresh(); refreshRuns(); }

async function submitScript() {
  const code = document.getElementById("script-code").value;
  if (!code.trim()) return;
  const name = document.getElementById("script-name").value || "script.py";
  const target = (document.getElementById("script-target").value || "all").trim();
  // Multi-index: "0,1,3" → spawn one run per index (server only accepts a
  // single target string, but UI lets you fire-and-forget several).
  const targets = target === "all" ? ["all"] : target.split(",").map(s => s.trim());
  for (const t of targets) {
    await fetch("/api/scripts/run", {
      method: "POST", headers: {"content-type": "application/json"},
      body: JSON.stringify({code, name, target: t}),
    });
  }
  refreshRuns();
}

function loadFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById("script-code").value = e.target.result;
    document.getElementById("script-name").value = file.name;
  };
  reader.readAsText(file);
}

async function refreshRuns() {
  let r;
  try { r = await fetch("/api/scripts"); } catch (e) { return; }
  if (!r.ok) return;
  const data = await r.json();
  const runs = data.runs || [];
  document.getElementById("runs-count").textContent = runs.length;
  if (runs.length === 0) {
    document.getElementById("runs").innerHTML =
      `<tr><td colspan="7" class="ghost" style="padding:24px;text-align:center">
        no runs yet
      </td></tr>`;
    return;
  }
  const rows = runs.map((r) => {
    const dur = r.ms != null ? fmtMs(r.ms) : (r.status === "running" ? "…" : "—");
    const ok = r.status === "ok";
    const statusCls = (r.status === "ok" || r.status === "running") ? "ok" : "err";
    return `
      <tr>
        <td class="idx">#${r.id}</td>
        <td>${escapeHtml(r.name)}</td>
        <td><span class="pill">${escapeHtml(r.target)}</span></td>
        <td class="status ${ok ? 'busy' : ''}">${escapeHtml(r.status)}</td>
        <td class="status">${r.ok_count}/${r.total}</td>
        <td class="status">${dur}</td>
        <td><button onclick="openRun(${r.id})">View</button></td>
      </tr>`;
  });
  document.getElementById("runs").innerHTML = rows.join("");
}

async function openRun(id) {
  const r = await fetch("/api/scripts/" + id);
  if (!r.ok) return;
  const data = await r.json();
  document.getElementById("run-title").textContent =
    `Run #${data.id} · ${data.name} · target=${data.target}`;
  const sections = Object.entries(data.results || {}).map(([idx, res]) => {
    const status = res.ok ? "OK" : "FAIL";
    const cls = res.ok ? "ok" : "err";
    return `
      <div style="margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;align-items:baseline;
                    margin-bottom:6px;font-family:ui-monospace,'SF Mono',Menlo,monospace;
                    font-size:12px">
          <span><b>browser #${idx}</b> <span class="s ${cls}"
                style="margin-left:8px;text-transform:uppercase;
                       letter-spacing:0.05em;font-size:11px">${status}</span></span>
          <span class="ghost">${fmtMs(res.ms || 0)}</span>
        </div>
        ${res.result ? `<div style="font-size:11px;color:var(--text-dim);
                       padding:4px 8px;background:var(--bg-card-2);border-radius:3px;
                       margin-bottom:6px;font-family:ui-monospace,'SF Mono',Menlo,monospace">
                       return: ${escapeHtml(res.result)}</div>` : ""}
        <pre style="background:var(--bg-card-2);border:1px solid var(--border-soft);
                    border-radius:4px;padding:10px;font-size:11px;color:var(--text-dim);
                    overflow:auto;max-height:240px;margin:0">${escapeHtml(res.output || "(no stdout)")}</pre>
        ${res.error ? `<pre style="background:var(--bg-card-2);border:1px solid var(--border-soft);
                       border-radius:4px;padding:10px;font-size:11px;color:var(--text);
                       overflow:auto;max-height:200px;margin-top:6px">${escapeHtml(res.error)}</pre>` : ""}
      </div>`;
  });
  document.getElementById("run-body").innerHTML = sections.join("") || `<div class="ghost">no results yet</div>`;
  document.getElementById("modal-run").classList.add("open");
}

document.querySelectorAll(".modal-bg").forEach(m => {
  m.addEventListener("click", (e) => { if (e.target === m) closeModals(); });
});

refresh();
refreshRuns();
setInterval(refresh, 1500);
setInterval(refreshRuns, 2500);
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
        allow_scripts: bool = True,
    ) -> None:
        if web is None:
            raise ImportError(
                "Panel requires aiohttp. Install with `pip install funbrowser[panel]`."
            ) from _IMPORT_ERROR
        self._pool = pool
        self._host = host
        self._port = port
        self._allow_scripts = allow_scripts
        self._started_at = time.monotonic()
        self._total = 0
        self._success = 0
        self._total_ms = 0.0
        self._events: deque[dict[str, Any]] = deque(maxlen=50)
        # FunSolver balance cache. Refreshed in background once per 30s when
        # /api/state is hit, so the UI never blocks on a remote call.
        self._balance: float | None = None
        self._balance_fetched_at: float = 0.0
        self._balance_lock = asyncio.Lock()
        self._bg_tasks: set[asyncio.Task[None]] = set()
        # Script-run registry (most recent first).
        self._script_runs: deque[ScriptRun] = deque(maxlen=50)
        self._next_run_id = 1

        self._app: Application = web.Application()
        self._app.router.add_get("/", self._index)
        self._app.router.add_get("/api/state", self._api_state)
        self._app.router.add_get("/api/settings", self._api_settings)
        self._app.router.add_post("/api/browser/{idx}/goto", self._api_goto)
        self._app.router.add_post("/api/browser/{idx}/new-tab", self._api_new_tab)
        self._app.router.add_post("/api/goto-all", self._api_goto_all)
        self._app.router.add_get("/api/browser/{idx}/screenshot", self._api_screenshot)
        self._app.router.add_post("/api/scripts/run", self._api_script_run)
        self._app.router.add_get("/api/scripts", self._api_script_list)
        self._app.router.add_get("/api/scripts/{id}", self._api_script_get)
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

    # ── stats helpers ────────────────────────────────────────────────

    def _record(
        self,
        *,
        browser: int,
        action: str,
        url: str | None,
        ok: bool,
        ms: float,
        error: str | None = None,
    ) -> None:
        self._total += 1
        if ok:
            self._success += 1
        self._total_ms += ms
        self._events.appendleft(
            {
                "ts": time.time(),
                "browser": browser,
                "action": action,
                "url": url,
                "ok": ok,
                "ms": ms,
                "error": error,
            }
        )

    # ── routes ────────────────────────────────────────────────────────

    async def _index(self, _request: Request) -> Response:
        assert web is not None
        return web.Response(text=INDEX_HTML, content_type="text/html")

    async def _api_state(self, _request: Request) -> Response:
        assert web is not None
        queue: Any = self._pool._available
        idle_set = {id(b) for b in list(queue._queue)}

        solver_client = self._first_solver_client()
        if solver_client is not None:
            self._maybe_refresh_balance(solver_client)

        cap_total = 0
        cap_success = 0
        merged: list[dict[str, Any]] = list(self._events)
        browsers = []
        for i, b in enumerate(self._pool.browsers):
            tabs = [{"url": t.url} for t in b.tabs]
            for e in b.events:
                if e.get("kind") == "captcha":
                    cap_total += 1
                    if e.get("ok"):
                        cap_success += 1
                merged.append({"browser": i, **e})
            browsers.append(
                {
                    "index": i,
                    "busy": id(b) not in idle_set,
                    "proxy": (f"{b.proxy.host}:{b.proxy.port}" if b.proxy is not None else None),
                    "geo": b.geo.country_code if b.geo is not None else None,
                    "fingerprint": (b.fingerprint.label if b.fingerprint is not None else None),
                    "tabs": tabs,
                }
            )

        merged.sort(key=lambda e: e.get("ts", 0.0), reverse=True)
        merged = merged[:80]

        avg = (self._total_ms / self._total) if self._total > 0 else 0.0
        return web.json_response(
            {
                "pool": {
                    "size": self._pool.size,
                    "created": self._pool.created,
                    "busy": self._pool.busy,
                    "idle": self._pool.idle,
                },
                "stats": {
                    "total": self._total,
                    "success": self._success,
                    "avg_ms": avg,
                    "uptime_s": time.monotonic() - self._started_at,
                },
                "solver": {
                    "available": solver_client is not None,
                    "balance": self._balance,
                    "fetched_s_ago": (
                        time.monotonic() - self._balance_fetched_at
                        if self._balance_fetched_at > 0
                        else None
                    ),
                },
                "captchas": {"total": cap_total, "success": cap_success},
                "browsers": browsers,
                "events": merged,
            }
        )

    async def _api_settings(self, _request: Request) -> Response:
        assert web is not None
        kw = dict(self._pool._browser_kwargs)
        if "api_key" in kw:
            kw["api_key"] = "***"
        return web.json_response(
            {
                "pool": {"size": self._pool.size, "created": self._pool.created},
                "proxies": self._pool._proxies or [],
                "browser_kwargs": {
                    k: (v if isinstance(v, str | int | float | bool | None) else repr(v))
                    for k, v in kw.items()
                },
                "panel": {"host": self._host, "port": self._port},
            }
        )

    async def _api_goto(self, request: Request) -> Response:
        assert web is not None
        idx = self._parse_idx(request)
        if idx is None:
            return web.json_response({"error": "bad index"}, status=400)
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

        t0 = time.monotonic()
        ok = True
        error = None
        try:
            browser = browsers[idx]
            tab = browser.tabs[0] if browser.tabs else await browser.new_tab()
            await tab.goto(url)
        except Exception as exc:
            ok = False
            error = str(exc)
        ms = (time.monotonic() - t0) * 1000.0
        self._record(browser=idx, action="goto", url=url, ok=ok, ms=ms, error=error)
        return web.json_response({"ok": ok, "url": url, "ms": ms, "error": error})

    async def _api_new_tab(self, request: Request) -> Response:
        assert web is not None
        idx = self._parse_idx(request)
        if idx is None:
            return web.json_response({"error": "bad index"}, status=400)
        try:
            data: dict[str, Any] = await request.json()
        except json.JSONDecodeError:
            data = {}
        url = data.get("url") or "about:blank"
        browsers = list(self._pool.browsers)
        if not 0 <= idx < len(browsers):
            return web.json_response({"error": "unknown browser"}, status=404)
        t0 = time.monotonic()
        ok = True
        error = None
        try:
            tab = await browsers[idx].new_tab(url=url)
            if url != "about:blank":
                await tab.goto(url)
        except Exception as exc:
            ok = False
            error = str(exc)
        ms = (time.monotonic() - t0) * 1000.0
        self._record(browser=idx, action="new-tab", url=url, ok=ok, ms=ms, error=error)
        return web.json_response({"ok": ok, "url": url, "ms": ms, "error": error})

    async def _api_goto_all(self, request: Request) -> Response:
        assert web is not None
        try:
            data: dict[str, Any] = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "bad json"}, status=400)
        url = data.get("url")
        if not isinstance(url, str) or not url:
            return web.json_response({"error": "missing url"}, status=400)

        async def one(i: int, browser: Any) -> dict[str, Any]:
            t0 = time.monotonic()
            ok = True
            error = None
            try:
                tab = browser.tabs[0] if browser.tabs else await browser.new_tab()
                await tab.goto(url)
            except Exception as exc:
                ok = False
                error = str(exc)
            ms = (time.monotonic() - t0) * 1000.0
            self._record(browser=i, action="goto", url=url, ok=ok, ms=ms, error=error)
            return {"index": i, "ok": ok, "ms": ms, "error": error}

        results = await asyncio.gather(*(one(i, b) for i, b in enumerate(self._pool.browsers)))
        return web.json_response({"ok": True, "results": list(results)})

    async def _api_screenshot(self, request: Request) -> Response:
        assert web is not None
        idx = self._parse_idx(request)
        if idx is None:
            return web.Response(status=400, text="bad index")
        browsers = list(self._pool.browsers)
        if not 0 <= idx < len(browsers):
            return web.Response(status=404, text="unknown browser")
        browser = browsers[idx]
        if not browser.tabs:
            return web.Response(status=404, text="no tabs in this browser")
        png = await browser.tabs[0].screenshot()
        return web.Response(body=png, content_type="image/png")

    def _parse_idx(self, request: Request) -> int | None:
        try:
            return int(request.match_info["idx"])
        except (KeyError, ValueError):
            return None

    # ── scripts ───────────────────────────────────────────────────────

    async def _api_script_run(self, request: Request) -> Response:
        assert web is not None
        if not self._allow_scripts:
            return web.json_response({"error": "scripts disabled"}, status=403)
        try:
            data: dict[str, Any] = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "bad json"}, status=400)

        code = data.get("code")
        if not isinstance(code, str) or not code.strip():
            return web.json_response({"error": "missing code"}, status=400)
        name = str(data.get("name") or "script.py")
        target = str(data.get("target") or "all")

        browsers = list(self._pool.browsers)
        if not browsers:
            return web.json_response({"error": "no browsers spawned yet"}, status=409)

        if target == "all":
            indices = list(range(len(browsers)))
        else:
            try:
                idx = int(target)
            except ValueError:
                return web.json_response({"error": "bad target"}, status=400)
            if not 0 <= idx < len(browsers):
                return web.json_response({"error": "unknown browser"}, status=404)
            indices = [idx]

        run = ScriptRun(
            id=self._next_run_id,
            name=name,
            code=code,
            target=target,
            browsers=indices,
            status="queued",
            started_at=time.time(),
        )
        self._next_run_id += 1
        self._script_runs.appendleft(run)

        async def _do() -> None:
            run.status = "running"
            await asyncio.gather(
                *(self._exec_on(run, i, browsers[i]) for i in indices),
                return_exceptions=True,
            )
            run.ended_at = time.time()
            all_ok = all(r.get("ok") for r in run.results.values())
            run.status = "ok" if all_ok else "fail"

        task = asyncio.create_task(_do())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

        return web.json_response({"id": run.id, "ok": True, "target": target})

    async def _api_script_list(self, _request: Request) -> Response:
        assert web is not None
        return web.json_response(
            {
                "runs": [self._run_summary(r) for r in self._script_runs],
                "allow_scripts": self._allow_scripts,
            }
        )

    async def _api_script_get(self, request: Request) -> Response:
        assert web is not None
        try:
            rid = int(request.match_info["id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "bad id"}, status=400)
        for r in self._script_runs:
            if r.id == rid:
                return web.json_response(self._run_full(r))
        return web.json_response({"error": "unknown run"}, status=404)

    def _run_summary(self, r: ScriptRun) -> dict[str, Any]:
        return {
            "id": r.id,
            "name": r.name,
            "target": r.target,
            "browsers": r.browsers,
            "status": r.status,
            "started_at": r.started_at,
            "ended_at": r.ended_at,
            "ms": ((r.ended_at - r.started_at) * 1000.0 if r.ended_at is not None else None),
            "ok_count": sum(1 for v in r.results.values() if v.get("ok")),
            "total": len(r.browsers),
        }

    def _run_full(self, r: ScriptRun) -> dict[str, Any]:
        return {
            **self._run_summary(r),
            "code": r.code,
            "results": {
                str(i): r.results.get(i, {"ok": False, "output": "", "error": "no result"})
                for i in r.browsers
            },
        }

    async def _exec_on(self, run: ScriptRun, idx: int, browser: Browser) -> None:
        """Compile + run the script's `main(browser)` coroutine, capture I/O."""
        buf = io.StringIO()
        t0 = time.monotonic()
        ok = True
        error: str | None = None
        result: Any = None
        try:
            module_ns: dict[str, Any] = {"__name__": "__script__"}
            compiled = compile(run.code, run.name, "exec")
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                exec(compiled, module_ns)
                fn = module_ns.get("main") or module_ns.get("run")
                if fn is None or not asyncio.iscoroutinefunction(fn):
                    raise ValueError(
                        "script must define `async def main(browser): ...` "
                        "(or `async def run(browser): ...`)"
                    )
                result = await fn(browser)
        except Exception:
            ok = False
            error = traceback.format_exc()
        ms = (time.monotonic() - t0) * 1000.0
        # Captured output may contain anything; truncate to keep response size sane.
        out = buf.getvalue()
        if len(out) > 50_000:
            out = out[:50_000] + "\n…(truncated)…"
        run.results[idx] = {
            "ok": ok,
            "output": out,
            "error": error,
            "result": repr(result) if result is not None else None,
            "ms": ms,
        }
        # Also push into the browser's own event feed so it shows in Activity.
        browser.record_event(
            kind="script",
            name=run.name,
            run_id=run.id,
            ok=ok,
            ms=ms,
        )

    # ── solver balance background refresh ─────────────────────────────

    def _first_solver_client(self) -> Any:
        for b in self._pool.browsers:
            if b.solver_client is not None:
                return b.solver_client
        # Also peek at the pool's pre-configured kwargs in case nothing is
        # spawned yet but an api_key is wired up.
        return None

    def _maybe_refresh_balance(self, client: Any) -> None:
        now = time.monotonic()
        # First call: fetch immediately. Otherwise wait 30s between hits.
        if self._balance_fetched_at and now - self._balance_fetched_at < 30:
            return
        if self._balance_lock.locked():
            return
        self._balance_fetched_at = now  # claim the slot

        async def _do() -> None:
            async with self._balance_lock:
                try:
                    self._balance = float(await client.balance())
                except Exception:
                    pass  # leave the previous value visible

        task = asyncio.create_task(_do())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
