# FunBrowser

Undetect browser with built-in captcha solving via [funsolver.com](https://funsolver.com).

> Pre-alpha. Not yet released.

## Goals

- nodriver-grade stealth (and beyond) — runtime CDP patches today, forked browser later
- Captchas solve themselves — paste your funsolver.com API key and forget about reCAPTCHA / hCaptcha / Turnstile / FunCaptcha / GeeTest
- Python async SDK familiar to nodriver users
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

## Where we're going (after M3)

```python
browser = await funbrowser.start(api_key="fs_xxx", auto_solve=True)
tab = await browser.get("https://protected-site.com")
# captchas auto-solve in the background
await tab.click("button[type=submit]")
```

## Roadmap

See `CHANGELOG.md` for what's landed.

| | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Bootstrap | done | |
| M1 | CDP core + Tab API | done | raw CDP, no Selenium/Playwright |
| M2 | Stealth Tier 1 + 2 | done | basic markers + real GPU + canvas/audio noise |
| M3 | Solver bridge + Turnstile | pending | |
| M4 | reCAPTCHA / hCaptcha / FunCaptcha / GeeTest | pending | |
| M5 | Production hardening | pending | profiles, proxies, retries, multi-tab |
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
