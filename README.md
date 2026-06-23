# FunBrowser

Undetect browser with built-in captcha solving via [funsolver.com](https://funsolver.com).

> Pre-alpha. Not yet released.

## Goals

- nodriver-grade stealth (and beyond) — runtime CDP patches today, forked browser later
- Captchas solve themselves — paste your funsolver.com API key and forget about reCAPTCHA / hCaptcha / Turnstile / FunCaptcha / GeeTest
- Python async SDK familiar to nodriver users
- Raw CDP over WebSocket — no Selenium, no Playwright (both leak)

## Quick taste (target API, not yet shipped)

```python
import funbrowser

browser = await funbrowser.start(
    api_key="fs_xxx",
    auto_solve=True,
)
tab = await browser.get("https://protected-site.com")
# captchas auto-solve in the background
await tab.find("button:has-text('Submit')").click()
```

## Roadmap to v0.1

See `CHANGELOG.md` for what's landed.

| | Milestone | Status |
|---|---|---|
| M0 | Bootstrap | in progress |
| M1 | CDP core + Tab API | pending |
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
