# FunBrowser

[![PyPI - Version](https://img.shields.io/pypi/v/funbrowser)](https://pypi.org/project/funbrowser/)
[![Python Versions](https://img.shields.io/pypi/pyversions/funbrowser)](https://pypi.org/project/funbrowser/)
[![License](https://img.shields.io/pypi/l/funbrowser)](https://github.com/WhyY0u/funBrowser/blob/main/LICENSE)

**Undetect / anti-detect browser SDK for Python.** Drives real Chrome through
the DevTools Protocol with built-in stealth patches, customisable browser
fingerprints (UA, GPU, screen, timezone, CPU cores, …), full proxy support,
human-like input timing, browser-pool / context-pool farming, an optional
local web panel, and automatic captcha solving for **Cloudflare Turnstile**,
**reCAPTCHA v2 / v3**, **hCaptcha**, **FunCaptcha**, and **GeeTest** through
[funsolver.com](https://funsolver.com).

Built for web scraping, browser automation, and bypassing antibot services
(Cloudflare, DataDome, PerimeterX, Akamai) without the Selenium / Playwright
leaks that get scripts flagged.

```bash
pip install funbrowser              # core: stealth + automation + solver
pip install funbrowser[panel]       # + local web panel for the pool
pip install funbrowser[tls]         # + browser-grade TLS impersonation
```

## Quick start

```python
import asyncio
import funbrowser

async def main():
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        print(await tab.evaluate("document.title"))
        # → Example Domain
        print(await tab.evaluate("navigator.userAgent"))
        # → Mozilla/5.0 ... Chrome/... — no "HeadlessChrome"

asyncio.run(main())
```

```python
# Full automation: stealth + proxy + auto-solve captchas + humanly input
async with await funbrowser.start(
    headless=True,
    proxy="user:pass@us-1.proxy.io:8080",     # any common format works
    api_key="fs_xxx",                         # funsolver.com key
    humanly=True,                             # Bezier mouse + typing rhythm
    fingerprint=funbrowser.presets.windows_11_nvidia_rtx_4070(),
) as browser:
    tab = await browser.get("https://target-with-captcha.com")
    # captchas auto-solve in the background
    await tab.fill("#email", "alice@example.com")
    await tab.click("button[type=submit]")
```

## Features

### Stealth (passes 25/25 standard antidetect probes)

- `navigator.webdriver` → undefined, **with native `toString` camouflage**
- UA + Client Hints with `HeadlessChrome` stripped
- `chrome.runtime`, `plugins`, `languages`, permissions consistency
- **Real GPU** for WebGL (`--use-gl=angle`, not SwiftShader)
- Canvas + audio readout noise to break fingerprint tracking
- WebRTC IP leak blocked (flag-level + SDP filter)
- iframe stealth propagation
- Geo auto-couples timezone + locale to proxy exit IP

```bash
uv run python examples/detect_check.py      # self-audit
```

### Fingerprint customisation

17 ready presets (Windows × NVIDIA / Intel / AMD, macOS Apple Silicon /
Intel, Linux, plus 4 Android mobile) + arbitrary custom `Fingerprint(...)`.

```python
from funbrowser import Fingerprint, presets

fp = presets.macos_apple_silicon_m3_pro().merge(
    Fingerprint(timezone="Asia/Tokyo", languages=("ja-JP", "ja", "en"))
)
async with await funbrowser.start(fingerprint=fp) as browser:
    ...
```

### Humanly mode (Bezier-curve mouse + typing rhythm)

```python
async with await funbrowser.start(humanly=True) as browser:
    await tab.click("button")        # cursor curves toward target
    await tab.type("#email", "ada")  # per-keystroke random delay
```

Presets: `humanly.FAST`, `humanly.DEFAULT`, `humanly.CAREFUL`, plus arbitrary
custom `HumanBehavior(...)`.

### Captcha auto-solve

Paste a [funsolver.com](https://funsolver.com) API key. Five captcha
families detected on-page and solved automatically:

| | API method | Page integration |
|---|---|---|
| Cloudflare Turnstile | `solve_turnstile` | `.cf-turnstile` widgets |
| reCAPTCHA v2 (+ Enterprise) | `solve_recaptcha_v2` | `.g-recaptcha` widgets |
| reCAPTCHA v3 (+ Enterprise) | `solve_recaptcha_v3` | hooks `grecaptcha.execute()` |
| hCaptcha | `solve_hcaptcha` | `.h-captcha` widgets |
| FunCaptcha / Arkose | `solve_funcaptcha` | `[data-pkey]` elements |
| GeeTest v3 + v4 | `solve_geetest` | hooks `initGeetest` / `initGeetest4` |

### Proxies (every format)

`host:port`, `host:port:user:pass`, `user:pass@host:port`, `host:port@user:pass`,
`socks5://...`, `chrome` URL form — all auto-parsed. HTTP/HTTPS auth flows
through CDP automatically.

### Persistent profiles

```python
from funbrowser import Profile

alice = Profile.ensure("alice")   # ./funbrowser_profiles/alice
async with await funbrowser.start(user_data_dir=alice) as browser:
    # cookies + localStorage + login state persist between runs
    ...
```

### Browser farming — `BrowserPool` and `ContextPool`

```python
from funbrowser import BrowserPool, ContextPool

# Process pool — full Chrome per slot (max isolation)
async with BrowserPool(
    size=5,
    proxies=["proxy1:8080", "proxy2:8080", "proxy3:8080"],
    headless=True,
    mini=True,
) as pool:
    async def scrape(browser):
        tab = await browser.get("https://example.com")
        return await tab.evaluate("document.title")

    results = await pool.run_all([scrape] * 100)

# Context pool — 1 Chrome + N isolated contexts (~7-10x less RAM)
async with ContextPool(size=10, headless=True, mini=True) as pool:
    async def scrape(ctx):
        tab = await ctx.get("https://example.com")
        return await tab.evaluate("document.title")

    results = await pool.run_all([scrape] * 100)
```

Memory comparison on the same 10-slot workload:
- `BrowserPool(size=10)` → ~1.0 GB
- `ContextPool(size=10)` → ~260 MB (one Chrome + 10 contexts)

### `mini=True` mode

Curated set of Chrome flags that cut RAM / CPU / disk per browser
(~50% lower RSS): site isolation off, background throttling, audio
muted, extensions / sync / translate disabled, small disk caches,
V8 heap cap. Combines with stealth — does **not** turn off the real
GPU. Works on `Browser`, `BrowserPool`, and `ContextPool` alike.

### TLS fingerprint impersonation (`pip install funbrowser[tls]`)

Script-level HTTP that picks JA3/JA4 from real-browser profiles:

```python
from funbrowser.tls import ImpersonatedHTTPClient

async with ImpersonatedHTTPClient(profile="chrome131") as http:
    r = await http.get("https://protected-api.com/endpoint")
```

23 supported profiles: `chrome99..chrome133a`, `safari15..safari18`,
`firefox133/135`, Android variants. See
[docs/M10_M11_DESIGN.md](docs/M10_M11_DESIGN.md) for the deeper
browser-traffic mitm proxy roadmap.

### Local web panel (`pip install funbrowser[panel]`)

```python
from funbrowser import BrowserPool, Panel

async with BrowserPool(size=5) as pool:
    async with Panel(pool) as panel:
        print(panel.url)   # http://127.0.0.1:8765
        await long_running_task()
```

Black-and-white dashboard with: pool stats, FunSolver balance, browser
fleet table (proxy / geo / fingerprint / open tabs / per-row goto +
screenshot), activity log (panel actions + per-browser captcha solves),
quick actions, and a **script runner** — upload an `async def
main(browser)` script and run it on one browser or fan it out across
the whole pool, with per-run stdout / return / traceback captured.

## Documentation

- [docs/stealth.md](docs/stealth.md) — anti-detect coverage in depth
- [docs/captchas.md](docs/captchas.md) — solver integration guide
- [docs/farming.md](docs/farming.md) — `BrowserPool` vs `ContextPool`
- [docs/panel.md](docs/panel.md) — the local web dashboard
- [docs/M10_M11_DESIGN.md](docs/M10_M11_DESIGN.md) — TLS + engine-layer roadmap
- [examples/](examples/) — runnable demos for every feature

## Self-audit

```bash
uv run python examples/detect_check.py
```

```
[navigator.* basics]              9/9   PASS
[chrome runtime + iframe]         6/6   PASS
[stealth-detection probes]        5/5   PASS
[WebGL / canvas / audio]          4/4   PASS
[WebRTC IP leak]                  1/1   PASS

score:     25/25  (100%)
```

## Roadmap

| | Milestone | Status |
|---|---|---|
| M0 | Bootstrap | done |
| M1 | CDP core + Tab API | done |
| M2 | Stealth Tier 1 + 2 | done |
| M2.5 | Fingerprint customisation | done |
| M3 | Solver bridge + Turnstile | done |
| M4 | reCAPTCHA / hCaptcha / FunCaptcha / GeeTest | done |
| M5 | Production hardening (proxies, profiles, retries, multi-tab) | done |
| M5.5 | DX Tier S (auto-wait + ElementHandle + cookies + block_urls) | done |
| M5.5+ | Humanly mode | done |
| M5.5++ | WebRTC + toString camouflage + geo auto-couple | done |
| M5.5+++ | Mobile presets + expanded catalog | done |
| M5.6 | BrowserPool | done |
| M5.7 | Web Panel (+ FunSolver balance + per-browser logs + scripts) | done |
| M5.8 | Mini mode | done |
| M6 | **v0.1 release** | **in progress** |
| M10a | TLS HTTP client (curl_cffi) | done |
| M11-alt | ContextPool (lightweight pool) | done |
| M7 | Fingerprint consistency (Tier 3) | post-v0.1 |
| M8 | Real fingerprint pool (Tier 4) | post-v0.1 |
| M9 | Deep WebGL / canvas / shader spoofing | post-v0.1 |
| M10b | mitm proxy for Chrome traffic (production-grade) | post-v0.1 |
| M11 | Browser fork (Camoufox / Chromium) | post-v0.1 |
| M12 | Tauri UI for manual mode | post-v0.1 |

## Development

Uses [uv](https://docs.astral.sh/uv/) for env + deps.

```bash
uv sync                              # install
uv run pytest -q                     # full test suite (173 tests)
uv run ruff check . && uv run ruff format --check .
uv run mypy funbrowser
uv run python examples/detect_check.py
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues + PRs welcome.

## License

MIT. See [LICENSE](LICENSE).
