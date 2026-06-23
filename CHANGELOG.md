# Changelog

All notable changes to FunBrowser will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Project bootstrap (M0): repo layout, `pyproject.toml` (uv + PEP 735 dependency groups), ruff + mypy + pytest configs, GitHub Actions CI matrix using `astral-sh/setup-uv`, MIT license.
- CDP core + Tab API (M1): raw CDP WebSocket transport with flat-session routing (no Playwright/Selenium), Chrome launcher that resolves the binary on Windows/macOS/Linux and parses the DevTools URL from `--remote-debugging-port=0` stderr, `Browser.start/get/new_tab/stop`, `Tab.goto/evaluate/query_selector/click/screenshot/close`, async context-manager support, `examples/basic.py`. Smoke + unit tests for CDP and launcher; integration test against real Chrome (auto-skipped when not installed).
