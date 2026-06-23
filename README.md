# FunBrowser

Undetect browser with built-in captcha solving via [funsolver.com](https://funsolver.com).

> Pre-alpha. Not yet released.

## Goals

- nodriver-grade stealth (and beyond) — runtime CDP patches today, forked browser later
- Captchas solve themselves — paste your funsolver.com API key and forget about reCAPTCHA / hCaptcha / Turnstile / FunCaptcha / GeeTest
- Python async SDK familiar to nodriver users
- Raw CDP over WebSocket — no Selenium, no Playwright (both leak)

## Today (M1 shipped)

```python
import asyncio
import funbrowser

async def main():
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        print(await tab.evaluate("document.title"))  # Example Domain
        (await tab.screenshot()) and None

asyncio.run(main())
```

## Where we're going (after M3)

```python
browser = await funbrowser.start(api_key="fs_xxx", auto_solve=True)
tab = await browser.get("https://protected-site.com")
# captchas auto-solve in the background
await tab.click("button[type=submit]")
```

## Roadmap to v0.1

See `CHANGELOG.md` for what's landed.

| | Milestone | Status |
|---|---|---|
| M0 | Bootstrap | done |
| M1 | CDP core + Tab API | done |
| M2 | Stealth runtime patches | pending |
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
