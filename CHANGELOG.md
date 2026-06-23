# Changelog

All notable changes to FunBrowser will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Project bootstrap (M0): repo layout, `pyproject.toml` (uv + PEP 735 dependency groups), ruff + mypy + pytest configs, GitHub Actions CI matrix using `astral-sh/setup-uv`, MIT license.
- CDP core + Tab API (M1): raw CDP WebSocket transport with flat-session routing (no Playwright/Selenium), Chrome launcher that resolves the binary on Windows/macOS/Linux and parses the DevTools URL from `--remote-debugging-port=0` stderr, `Browser.start/get/new_tab/stop`, `Tab.goto/evaluate/query_selector/click/screenshot/close`, async context-manager support, `examples/basic.py`. Smoke + unit tests for CDP and launcher; integration test against real Chrome (auto-skipped when not installed).
- Stealth Tier 1 + Tier 2 (M2): `funbrowser.stealth` subpackage with launch flags + JS patches applied via `Network.setUserAgentOverride` and `Page.addScriptToEvaluateOnNewDocument`. Strips "HeadlessChrome" from UA + Client Hints, makes `navigator.webdriver` undefined, populates `chrome.runtime`/`plugins`/`languages`, fixes `permissions.query` ↔ `Notification.permission` mismatch, adds 1-LSB noise to canvas readouts (`getImageData`/`toDataURL`/`toBlob`) and sub-audible noise to audio (`AudioBuffer.getChannelData`, `AnalyserNode.getFloatFrequencyData`). Real GPU via `--use-gl=angle --use-angle=default` so WebGL fingerprint reflects actual hardware instead of SwiftShader. `examples/stealth_check.py` probes a URL and prints the verdict. Toggleable per browser with `stealth=False`. 10 new tests, all green.
