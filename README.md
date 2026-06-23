# FunBrowser

Undetect browser with built-in captcha solving via [funsolver.com](https://funsolver.com).

> Pre-alpha. Not yet released.

## Goals

- Deep stealth — runtime CDP patches today, forked browser later
- Captchas solve themselves — paste your funsolver.com API key and forget about reCAPTCHA / hCaptcha / Turnstile / FunCaptcha / GeeTest
- Python async SDK with first-class fingerprint customization (presets or custom)
- Raw CDP over WebSocket — no Selenium, no Playwright (both leak)

## Today (M1 + M2 shipped)

```python
import asyncio
import funbrowser

async def main():
    # stealth=True by default — strips HeadlessChrome UA, hides
    # navigator.webdriver, populates plugins/languages/chrome.runtime,
    # uses real GPU for WebGL, adds canvas/audio noise.
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        print(await tab.evaluate("navigator.userAgent"))
        # Mozilla/5.0 ... Chrome/149.0.0.0 ...   (no "HeadlessChrome")

asyncio.run(main())
```

Probe yourself:

```bash
uv run python examples/stealth_check.py
uv run python examples/stealth_check.py https://bot.sannysoft.com/
```

## Custom fingerprint (M2.5)

Pick a preset or build your own — the SDK plumbs the values into UA + Client
Hints + navigator + screen + WebGL.

```python
from funbrowser import Fingerprint, presets

# Preset
fp = presets.windows_11_amd_radeon_6700_xt()

# Preset + custom overrides
fp = presets.macos_apple_silicon_m3_pro().merge(
    Fingerprint(timezone="Asia/Tokyo", languages=("ja-JP", "ja", "en"))
)

# Fully custom
fp = Fingerprint(
    user_agent="Mozilla/5.0 ... Chrome/130.0.0.0 ...",
    hardware_concurrency=16,
    device_memory=8,
    webgl_vendor="Google Inc. (NVIDIA)",
    webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 3060, D3D11)",
)

async with await funbrowser.start(fingerprint=fp) as browser:
    tab = await browser.get("https://example.com")
```

Available presets: see `funbrowser.presets.ALL`. Filter with
`presets.filter_by_tag("windows")` / `("macos")` / `("high-end")` / etc.

Note on WebGL spoofing: overriding `webgl_vendor` + `webgl_renderer` only
changes the strings `getParameter()` returns. The rendered pixel output
still comes from the real GPU underneath, so top-tier antibots can still
catch the mismatch by comparing the claimed renderer to the actual pixels.
Full shader-level spoofing is M9.

## Proxies (M5)

Pass any common proxy-string format — the parser auto-detects layout.

```python
# All of these work:
funbrowser.start(proxy="1.2.3.4:8080")
funbrowser.start(proxy="http://1.2.3.4:8080")
funbrowser.start(proxy="user:pass@1.2.3.4:8080")
funbrowser.start(proxy="1.2.3.4:8080:user:pass")    # IPRoyal / Smartproxy lists
funbrowser.start(proxy="user:pass:1.2.3.4:8080")    # legacy listings
funbrowser.start(proxy="1.2.3.4:8080@user:pass")
funbrowser.start(proxy="socks5://user:pass@1.2.3.4:1080")
```

HTTP/HTTPS auth flows through CDP automatically. SOCKS auth needs an
upstream HTTP wrapper (Chrome doesn't expose SOCKS auth via DevTools).

## Persistent profiles (M5)

```python
from funbrowser import Profile

alice = Profile.ensure("alice")     # ./funbrowser_profiles/alice
async with await funbrowser.start(user_data_dir=alice) as browser:
    # cookies, localStorage, IndexedDB, login state persist between runs
    ...
```

`FUNBROWSER_PROFILES` env var changes the root.

## Auto-solve captchas (M3 — Cloudflare Turnstile today, the rest in M4)

```python
async with await funbrowser.start(api_key="fs_xxx") as browser:
    tab = await browser.get("https://site-with-turnstile.com")
    # detector spots the .cf-turnstile widget, sends sitekey + URL to
    # funsolver.com, drops the token into the response field and fires
    # the page's success callback — all without your code doing anything.
    await tab.click("button[type=submit]")
```

## Roadmap

See `CHANGELOG.md` for what's landed.

| | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Bootstrap | done | |
| M1 | CDP core + Tab API | done | raw CDP, no Selenium/Playwright |
| M2 | Stealth Tier 1 + 2 | done | basic markers + real GPU + canvas/audio noise |
| M3 | Solver bridge + Turnstile | done | |
| M4 | reCAPTCHA / hCaptcha / FunCaptcha / GeeTest | pending | |
| M5 | Production hardening | done | proxies, profiles, real input events, retries, multi-tab |
| M6 | **v0.1 release** | pending | PyPI, docs |
| M7 | Fingerprint consistency (Tier 3) | post-v0.1 | Client Hints + tz + screen + fonts coherent across layers |
| M8 | Real fingerprint pool (Tier 4) | post-v0.1 | bundled DB of real-user fingerprints, per-profile rotation |
| M9 | Deep WebGL/canvas/shader spoofing | post-v0.1 | substitute real GPU-rendered pixels so output matches claimed renderer |
| M10 | TLS JA3/JA4 fingerprint | post-v0.1 | mitm with curl_cffi/utls, or BoringSSL patch in M11 |
| M11 | Browser fork | post-v0.1 | Camoufox or ungoogled-chromium with C++ stealth patches |
| M12 | Tauri UI for manual mode | post-v0.1 | desktop app with tabs/address bar/settings |
| M3 | Solver bridge + Turnstile | pending |
| M4 | reCAPTCHA, hCaptcha, FunCaptcha, GeeTest | pending |
| M5 | Production hardening | pending |
| M6 | v0.1 release | pending |

## Development

Uses [uv](https://docs.astral.sh/uv/) for env + deps.

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy funbrowser
uv run pytest -v
```

## License

MIT. See `LICENSE`.
