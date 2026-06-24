# Local web panel

A built-in localhost dashboard for inspecting and controlling a
`BrowserPool` (or `ContextPool`). Install with the optional extra:

```bash
pip install funbrowser[panel]
```

```python
from funbrowser import BrowserPool, Panel

async with BrowserPool(size=5, headless=True) as pool:
    async with Panel(pool) as panel:
        print(panel.url)        # http://127.0.0.1:8765
        await long_running_task()
```

Open the URL in any browser. No build step, no external assets — the
HTML / CSS / JS dashboard is embedded in `funbrowser/panel.py`.

## What the dashboard shows

- **Header bar** — project name + uptime
- **6 stat cards** — Total Requests, Success Rate, Avg Response,
  Browsers (created/cap), Tabs (open across pool), FunSolver Balance
- **Browser Fleet table** — per slot: index, status (idle / busy),
  proxy host:port, geo country code, fingerprint label, current URL,
  per-row goto form, screenshot link
- **Activity log** — last 50 events merged from panel-initiated
  navigations + per-browser captcha solve attempts (type, ok / fail,
  duration)
- **Quick Actions** — Navigate all (modal), New tab, Settings, Refresh
- **System sidebar** — API state, avg time, browsers count, open tabs,
  today's request count, solver state (ON / OFF), captcha success rate,
  uptime
- **Scripts panel** — paste an `async def main(browser)` or upload a
  `.py` file, target one browser or all of them, see captured stdout +
  return value + traceback for every run

Auto-refreshes every 1.5 seconds.

## Settings

Default: black-and-white theme, port 8765, bound to 127.0.0.1.

```python
Panel(pool, host="127.0.0.1", port=8765, allow_scripts=True)
```

Set `allow_scripts=False` if the panel will be exposed beyond
localhost. The Script Runner uses `exec()` on user-supplied code,
which is fine for local control but dangerous on the open network.

## Scripts panel

Paste:

```python
async def main(browser):
    tab = await browser.get("https://api.ipify.org?format=json")
    body = await tab.evaluate("document.body.innerText")
    print(f"exit IP: {body}")
    return body
```

Set target = `all` (every browser in the pool) or a specific index
(`0`, `1`, ...) or a comma-separated list (`0,2,3`). Click **Run**.

Each run appears in the **Recent Runs** table with its status / total
duration / view button. Click View → modal shows per-browser stdout,
return value, and traceback if it failed.

Captured per browser:
- `output` (stdout + stderr, truncated to 50 KB)
- `result` (`repr()` of the return value)
- `error` (full traceback on exception)
- `ms` (wall time)

The script runs in a fresh namespace each time — no shared state
between invocations.

## REST API

If you want to drive the panel from outside the browser:

| | |
|---|---|
| `GET /` | the HTML dashboard |
| `GET /api/state` | pool stats + browser list + activity log + solver block |
| `GET /api/settings` | read-only view of the pool configuration |
| `POST /api/browser/{idx}/goto` | `{"url": "..."}` — navigate one browser |
| `POST /api/browser/{idx}/new-tab` | `{"url": "..."}` — open a new tab |
| `POST /api/goto-all` | `{"url": "..."}` — navigate every browser concurrently |
| `GET /api/browser/{idx}/screenshot` | PNG of the browser's first tab |
| `POST /api/scripts/run` | `{"code", "name", "target"}` — submit a script run |
| `GET /api/scripts` | list of recent runs (summary) |
| `GET /api/scripts/{id}` | full run with per-browser results |

Used together with `curl` or any HTTP client, the API makes the panel
a programmable headquarters for a remote farm. (Still bind to
localhost unless you know what you're doing.)
