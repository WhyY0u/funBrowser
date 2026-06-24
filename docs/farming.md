# Browser farming: `BrowserPool` vs `ContextPool`

For workloads that run many isolated workers in parallel — scraping at
scale, multi-account automation, captcha-gated flow farming — FunBrowser
ships two pool shapes. Pick by your isolation vs memory trade-off.

## `BrowserPool` — full Chrome per slot

```python
from funbrowser import BrowserPool

async with BrowserPool(
    size=5,
    headless=True,
    mini=True,
    proxies=[
        "user:pass@us-1.proxy.io:8080",
        "user:pass@us-2.proxy.io:8080",
        "user:pass@gb-1.proxy.io:8080",
        "user:pass@de-1.proxy.io:8080",
        "user:pass@jp-1.proxy.io:8080",
    ],
) as pool:
    async def scrape(browser):
        tab = await browser.get("https://example.com")
        return await tab.evaluate("document.title")

    results = await pool.run_all([scrape] * 100)
```

- Each slot is a separate Chrome process
- One process crash doesn't take the others down
- Round-robin proxy assignment by slot index
- `geo_autoconfigure=True` (default) pins each slot's timezone / locale
  to its exit IP

Memory at 10 slots, headless + mini: **~1.0 GB** total.

## `ContextPool` — one Chrome, N isolated contexts

```python
from funbrowser import ContextPool

async with ContextPool(size=10, headless=True, mini=True) as pool:
    async def scrape(ctx):
        tab = await ctx.get("https://example.com")
        return await tab.evaluate("document.title")

    results = await pool.run_all([scrape] * 100)
```

- One shared Chrome process; each slot is a `BrowserContext` via
  CDP `Target.createBrowserContext`
- Each context has its own cookies / localStorage / IndexedDB / cache
- Per-context proxy via `Target.createBrowserContext({proxyServer})`
- Same `acquire` / `run` / `run_all` / `stop` surface as `BrowserPool`

Memory at 10 slots, headless + mini: **~260 MB** total
(~180 MB host + ~8 MB per context).

The trade-off: host Chrome crashes take **every** context down with it.
For high-volume short-task workloads where you'd otherwise oversubscribe
RAM, this is the right shape. For long-lived sessions where loss of a
slot is expensive, stick with `BrowserPool`.

## Same code, swap the pool

The script signature is the only thing that differs:

```python
# BrowserPool: callable receives a Browser
async def work_browser(browser):
    tab = await browser.get(URL)
    ...

# ContextPool: callable receives a BrowserContext
async def work_ctx(ctx):
    tab = await ctx.get(URL)
    ...
```

Both have `.get(url)`, `.new_tab(url)`, `.tabs`, `.cookies()`,
`.set_cookies()`, `.clear_cookies()`.

## `mini=True`

A curated set of Chrome flags that cut ~50% RAM per browser without
touching the antidetect surface: site isolation off, background
throttling, audio muted, extensions / sync / translate / breakpad
disabled, small caches, V8 heap cap. Works on `Browser`, `BrowserPool`,
and `ContextPool`. Does **not** disable the real GPU (stealth needs the
WebGL fingerprint).

Combine freely:

```python
ContextPool(size=20, headless=True, mini=True, proxies=[...])
```

20 slots through a single mini-tuned Chrome process: ~360 MB on the
machine this README was tested on.

## Stop semantics

- `async with` exits clean: pool.stop() disposes every context / kills
  every process / drains the queue so no caller waits forever on a
  closed pool.
- `pool.stop()` mid-flight tears everything down; pending `acquire()`
  callers see `RuntimeError("pool is closed")`.

## Stress testing

`examples/pool.py` runs eight URLs through a 3-browser process pool.
`examples/context_pool.py` runs the same eight URLs through a 3-context
shared pool. Wall times are essentially identical; the memory delta is
the point.
