# Changelog

All notable changes to FunBrowser will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-06-24

First public release. Everything below `Added` is what made the cut.

### Highlights

- **Stealth**: 25/25 standard antidetect probes pass (UA, navigator.*,
  chrome.runtime, plugins, languages, permissions, real-GPU WebGL,
  canvas + audio noise, WebRTC IP leak block, toString camouflage,
  iframe propagation).
- **Captcha auto-solve**: Cloudflare Turnstile, reCAPTCHA v2 / v3
  (+ Enterprise), hCaptcha, FunCaptcha / Arkose, GeeTest v3 + v4 —
  all via `funsolver.com`.
- **Fingerprint customisation**: 17 presets (Windows × NVIDIA / Intel /
  AMD, macOS × Apple Silicon / Intel, Linux, 4 Android mobile) plus
  arbitrary `Fingerprint(...)`. Proxy ↔ geo auto-coupling fills
  timezone / locale / accept_language from the exit IP.
- **Humanly mode**: Bezier-curve mouse paths with ease-in-out timing,
  randomised click hold, per-keystroke typing rhythm, sub-pixel target
  jitter.
- **Proxies**: every format under the sun — `host:port`,
  `user:pass@host:port`, `host:port:user:pass`, `socks5://...`.
  HTTP/HTTPS auth via CDP.
- **Pools**:
  - `BrowserPool` — full Chrome per slot, max isolation
  - `ContextPool` — one Chrome + N isolated contexts, ~7-10x less RAM
- **`mini=True`** mode — Chrome flags that cut ~50% RAM per browser.
- **Web Panel** (`pip install funbrowser[panel]`) — black-and-white
  dashboard with pool stats, FunSolver balance, browser fleet, per-row
  goto + screenshot, activity log merging panel actions + per-browser
  captcha solves, quick actions, and an inline async script runner.
- **TLS impersonation** (`pip install funbrowser[tls]`) —
  `ImpersonatedHTTPClient` lets script-side HTTP calls use real
  browser JA3/JA4 (23 profiles: chrome99..chrome133a, safari15..18,
  firefox133/135).
- **DX Tier S**: `ElementHandle`, `tab.find(selector, timeout)`,
  `tab.type / fill / text / attribute / click / hover`, real
  `Input.dispatchMouseEvent` with auto-wait baked in,
  `tab.block_urls`, `browser.cookies / set_cookies / clear_cookies`.

### Out of scope for v0.1 — see roadmap

- **M10b**: production-grade mitm proxy for spoofing Chrome's own TLS
  (alpha scaffold ships in `funbrowser.tls.mitm`, HTTP/2 + WebSocket
  bridging TODO — sized at 3-5 days of work)
- **M11**: C++-level patches via Camoufox integration or own Chromium
  fork (1-2 weeks for Camoufox, months for fork)
- **M7-M9**: Tier 3+ fingerprint work (cross-layer consistency, real
  user fingerprint pool, pixel-level WebGL spoofing)

### Counts at release

- 173 tests, all green
- ruff + mypy strict clean
- 17 commits on `main` from M0 → release

## [0.1.1] - 2026-06-24

### Added

- `Browser.save_cookies(path)` / `load_cookies(path, clear_first=False)` —
  one-line JSON file persistence for cookies. Returns the count.
- `BrowserContext.save_cookies(path)` / `load_cookies(path)` — same shape,
  context-scoped (no leakage between contexts).
- `Tab.local_storage()` returns a `dict[str, str]` snapshot of the current
  origin's `window.localStorage`.
- `Tab.set_local_storage(items, clear_first=False)` bulk-applies entries
  on the current origin.
- `Browser.export_state(path)` / `import_state(path, navigate=True,
  clear_first=False)` — full session snapshot (cookies + per-open-tab
  localStorage). `navigate=True` (default) re-opens a tab on each saved
  origin so localStorage can be restored (Chrome refuses to set
  localStorage for an unloaded origin). Returns
  `{"cookies": N, "origins": M}`.

### Tests

- 5 new round-trip tests in `tests/test_state_persist.py`:
  save→file→assert, save→load→fresh-browser, localStorage snapshot,
  full export→import with localStorage restoration, context-scoped
  save/load isolation.

### Example

- `examples/save_session.py` walks save + restore in two browser processes.

## [0.1.25] - 2026-06-26

### Added

- **`tab.route(url_pattern, handler)` — Playwright-style request
  interception.** The handler receives a `Route` and decides the
  request's fate via one of:
  - `route.continue_(*, url=None, method=None, headers=None, post_data=None)`
    — pass through, optionally rewriting any field
  - `route.abort(error_reason="Failed")` — cancel with a CDP error
    (`BlockedByClient`, `ConnectionReset`, etc.)
  - `route.fulfill(*, status=200, body=b"", headers=None, content_type=None)`
    — return a synthetic response without hitting the network. Mock
    SDK endpoints, replay solver tokens, short-circuit trackers.

  Routes are stackable (call `route()` many times — they fire in
  registration order; first to resolve wins) and compose cleanly with
  `block_urls` (blocks run first). The returned unsubscribe callable
  removes that single route. `block_urls` internals were refactored
  to share a single `Fetch.enable` with `route()` — API unchanged.

- **`tab.on_request(handler)` / `tab.wait_for_request(url_or_predicate)`
  and `funbrowser.Request`** — symmetric counterparts to the response
  observation API added in v0.1.24. `Request` carries `.url`,
  `.method`, `.headers`, `.post_data`, `.resource_type`, and
  `.is_navigation`. Wraps `Network.requestWillBeSent`. Pure
  observation — for intercept, use `route()`.

  Together with the v0.1.24 response API, this covers the
  DataDome-solver shape (snoop a specific XHR, read body, feed it to
  a solver) plus mock-and-replay flows (intercept the SDK's token
  endpoint, fulfill with a pre-computed token) without dropping to
  raw CDP or injecting a JS shim.

## [0.1.24] - 2026-06-26

### Added

- **HTTP response interception on `Tab`.** Two new methods plus a
  `Response` value type cover the puppeteer-style
  `page.on('response')` / `page.waitForResponse(...)` use case:
  - `await tab.on_response(handler) -> unsubscribe` — fires for every
    `Network.responseReceived` event. Handler receives a `Response`;
    both sync and async handlers are accepted.
  - `await tab.wait_for_response(url_or_predicate, *, timeout=30.0)`
    — async wait for the first matching response. Accepts a URL
    substring or a `(Response) -> bool` predicate.
  - `funbrowser.Response` — `.url`, `.status`, `.headers`, plus lazy
    `await .body()` / `.text()` / `.json()` (body cached after first
    call). Chrome buffers bodies for a limited window after the
    request completes; read them promptly inside the handler. The
    error message points the user at this if the buffer evicts.

  Enables flows like the DataDome solver pattern (snoop a specific
  XHR, extract the SDK payload, feed it to a solver) without dropping
  to raw CDP. `Network.enable` is called lazily on first use, so tabs
  that don't observe responses pay nothing.

## [0.1.23] - 2026-06-26

### Added

- **`nano=True`** mode on `funbrowser.start(...)` — an opt-in extra
  layer on top of `mini=True` that pushes a single browser instance to
  its practical floor on Windows. Measured **458 MB RSS / 7 processes**
  vs 511 MB / 9 (`mini=True`) vs 603 MB / 11 (default). Adds three
  Chrome flags: `--in-process-gpu` (~-40 MB, collapses the GPU process
  into the browser process; real-GPU WebGL fingerprint still works),
  `--renderer-process-limit=1` (~-20 MB, all tabs share one renderer
  — disables site isolation, fine for the 1-browser-per-account farm
  pattern), plus an extended `--disable-features=` that turns off the
  rest of Chrome's phone-home surface (Translate, MediaRouter, Privacy
  Sandbox / Topics, optimisation hints, autofill server, certificate
  transparency component updater). `nano=True` implies `mini=True`.

## [0.1.22] - 2026-06-26

### Fixed

- **`funbrowser.helpers.google.login` + `continue_signin` — password
  fill and `#passwordNext` click now go through page-context JS.**
  Google's password input is React-controlled, so CDP `Input.insertText`
  bypasses the internal value tracker and the framework reverts the
  change. The fill now uses the native `HTMLInputElement.prototype.value`
  setter + dispatches `input` / `change`. `#passwordNext` is clicked
  via `element.click()` in page JS for the same reason as the chooser
  tiles. CDP fill/click remain as automatic fallbacks. Verified live
  against a real account.

## [0.1.21] - 2026-06-26

### Fixed

- **`funbrowser.helpers.google.continue_signin` — FedCM / inline OAuth
  flows weren't supported.** The helper used to fail fast when the tab
  URL wasn't on `accounts.google.com`, but some "Sign in with Google"
  integrations (Autodesk and others) render Google's sign-in DOM
  directly inside the client page — URL stays on the client site the
  whole time. The page-detection check now combines URL + DOM markers
  (identifier input, password input, chooser tile, consent button) and
  works on both flows transparently. The wait-for-done loop uses the
  same combined check instead of waiting for a URL change.

### Added

- **`continue_signin` now clicks through the OAuth consent screen.**
  After password entry, Google's "<App> wants to access your info"
  page is auto-confirmed via the Continue button (`[jsname="uRHG6"]`).
  Pass `allow_consent=False` to opt out and leave the consent decision
  to the user.

## [0.1.20] - 2026-06-26

### Fixed

- **`funbrowser.helpers.google.continue_signin` + `login` — account
  chooser tiles weren't clicking.** Google's "Choose an account" tiles
  are `<div role="link">` whose click handlers don't fire on
  CDP-synthesised mouse events. The chooser flow now uses
  `element.click()` via `tab.evaluate(...)` for these tiles, which
  dispatches inside the page's own JS runtime and goes through reliably.
  No API change.

## [0.1.19] - 2026-06-26

### Added

- **`funbrowser.helpers.google.continue_signin(tab_or_browser, *, email,
  password, totp_secret=None, timeout=60)`** — completes an in-progress
  "Sign in with Google" OAuth flow on a third-party site. Walks
  whichever Google screen is currently visible (account chooser, email,
  password, 2FA) and returns when Google redirects back to the client
  app. Use after clicking a third-party site's "Sign in with Google"
  button — unlike `login()`, this does NOT navigate to
  accounts.google.com itself. Same return shape as `login()`.
  Detects existing accounts: clicks the `[data-identifier=<email>]`
  tile if present (skipping the email step), otherwise clicks "Use
  another account".
- **`Tab.evaluate(expression, *, default=...)`** — pass a `default`
  value to swallow real JS exceptions (not just navigation races) and
  return that default instead of raising `RuntimeError`. Without
  `default`, real JS errors still raise so bugs in your expression are
  visible. Fix for the "`document.body.innerText` while page is loading
  → null deref → crash" pattern:
  `await tab.evaluate("document.body.innerText", default="")`.
- **`Browser.get_tabs()`** — method alias for the `tabs` property,
  because some users instinctively reach for a method.

### Internal

- `helpers.google.login` and `helpers.google.continue_signin` now use
  `default=""` on their innerText polls — no more spurious crashes when
  the polling loop races a Google redirect mid-load.

## [0.1.18] - 2026-06-24

### Added

- **`Browser.switch_tab(tab | int | str)`** — bring a tab to the
  foreground of the browser window via `Target.activateTarget`.
  Accepts an existing `Tab` handle, an index into `browser.tabs`
  (negatives count from the end), or a URL substring (first match
  wins). Tabs are always independently drivable — this is for the UI
  side when running headful.
- **`Profile.reset(name)`** — wipe + recreate a profile under the same
  name. Returns the fresh path. Use when you want a clean session
  (no leftover cookies, no Google-account chooser entry, no service
  workers) without changing the profile name.
- **`Profile.clear_tabs(name)`** — drop only Chrome's session-restore
  state (`Current Tabs`, `Last Tabs`, `Current Session`,
  `Last Session`, `Sessions/`) and patch `Preferences` so Chrome
  opens NTP instead of restoring 50 old tabs. Keeps `Cookies`,
  `Local Storage`, `Session Storage`, `IndexedDB` — auth survives.
  Use between launches when a long-lived profile keeps reopening
  every URL you've ever visited.

### Tests

- 1 integration test for `switch_tab` (all 4 call shapes + LookupError).
- 5 unit tests for `Profile.reset` / `Profile.clear_tabs` covering
  auth-side preservation, session-side wipe, Preferences rewrite, and
  no-op behavior on missing or broken profiles.

## [0.1.17] - 2026-06-24

### Fixed

- **Navigation-race false positive in `Tab.evaluate` / `Tab.query`.** CDP
  returns a synthetic `exceptionDetails` with `text="Uncaught"` and no
  real exception object when the execution context is destroyed
  mid-evaluate (page started navigating). Previously this raised
  `RuntimeError("JS exception: Uncaught")`. Now `_is_navigation_race`
  detects the shape (no `objectId` / `className` / `description` /
  `value`) and returns `None` / `[]` instead. Real JS errors still raise
  as before. Unblocks the polling pattern in `helpers.google.login()`.
- **Google login: account-chooser page handled.** When the Chrome
  profile has any previously-used Google account, Google shows a
  "Choose an account" screen with that account + a "Use another
  account" entry instead of the identifier input. The helper now
  detects this (URL contains `accountchooser` or `[jsname="rwl3qc"]`
  present) and clicks through to the email input.

### Tests

- 9 new unit tests in `tests/test_navigation_race.py` covering the
  detector across real JS errors, thrown strings, thrown 0, synthetic
  Uncaught, etc. 197 tests total.

## [0.1.16] - 2026-06-24

### Fixed

- `funbrowser.helpers.google` now imported automatically — was missing
  `from . import google, totp` in `helpers/__init__.py`, so
  `funbrowser.helpers.google.login(...)` raised `AttributeError`.
- Google email-input selector corrected: the real field is
  `<input type="text" id="identifierId" name="identifier">`, not
  `type="email"`. Helper now tries `#identifierId` → `input[name="identifier"]`
  → aria-label fallback.
- Password-page selectors now also try `name="Passwd"` and an aria-label
  fallback, not just `type="password"`.
- Login success is now actively verified by navigating to
  `myaccount.google.com` after the wait loop: if Google keeps us on the
  dashboard we return `ok=True`; if it bounces to `/signin` we return
  `ok=False`. Previously we only watched the URL passively during the
  poll window and could miss a successful login that took longer than
  the timeout to reflect in the URL.

## [0.1.15] - 2026-06-24

### Added — automation helpers

- **`funbrowser.IMAPMail`** — async IMAP client (stdlib `imaplib` wrapped in
  `asyncio.to_thread`). `await mailbox.wait_for_code(sender_contains=...,
  subject_contains=..., pattern=r"\b(\d{6})\b", timeout=120)` polls the
  mailbox for *new* messages matching the filters and returns the first
  regex capture group — the canonical "wait for the 6-digit verification
  code" loop, no third-party dep. Also `list_recent(limit=...)` and
  `fetch(uid)` for full message dumps. Multipart bodies are flattened to
  plain text (text/plain preferred, text/html stripped as fallback).
  Works with Gmail / iCloud (app-password required), Outlook, FastMail,
  any standard IMAP host. Connect via `async with`.
- **`funbrowser.MailMessage`** — dataclass returned by `list_recent` /
  `fetch`: `uid, sender, subject, body, date`.
- **`funbrowser.helpers.google.login(browser_or_tab, *, email, password,
  totp_secret=None, timeout=60)`** — best-effort sign-in flow against
  `accounts.google.com`. Returns `{"ok": bool, "url": str,
  "challenge": str | None}`. Handles email/password screens; if
  `totp_secret` provided and `[automation]` extra is installed, types the
  current TOTP on the 2FA screen. Disclaimed as fragile (Google rotates
  selectors and risk-checks aggressively) — the return dict reports
  where the flow stalled so callers can intervene.
- **`funbrowser.helpers.totp.now(secret)`** — thin wrapper over `pyotp`;
  strips whitespace + uppercases the secret. `helpers.totp.available()`
  reports whether the `[automation]` extra is installed.

### Optional extra

- **`pip install funbrowser[automation]`** adds `pyotp>=2.9` for TOTP code
  generation. IMAP itself needs no extra (stdlib).

### Tests

- 10 new tests: 6 in `tests/test_mail.py` (stubbed IMAP backend covering
  body extraction, capture-group code parsing, sender-filter, timeout,
  list_recent ordering), 4 in `tests/test_helpers_totp.py` (pyotp
  matching, whitespace-strip, 6-digit shape). 188 tests total.

### Example

- `examples/gmail_and_codes.py` — Google login → IMAPMail code wait
  → fill on target site.

## [Unreleased]

### Added
- Project bootstrap (M0): repo layout, `pyproject.toml` (uv + PEP 735 dependency groups), ruff + mypy + pytest configs, GitHub Actions CI matrix using `astral-sh/setup-uv`, MIT license.
- CDP core + Tab API (M1): raw CDP WebSocket transport with flat-session routing (no Playwright/Selenium), Chrome launcher that resolves the binary on Windows/macOS/Linux and parses the DevTools URL from `--remote-debugging-port=0` stderr, `Browser.start/get/new_tab/stop`, `Tab.goto/evaluate/query_selector/click/screenshot/close`, async context-manager support, `examples/basic.py`. Smoke + unit tests for CDP and launcher; integration test against real Chrome (auto-skipped when not installed).
- Stealth Tier 1 + Tier 2 (M2): `funbrowser.stealth` subpackage with launch flags + JS patches applied via `Network.setUserAgentOverride` and `Page.addScriptToEvaluateOnNewDocument`. Strips "HeadlessChrome" from UA + Client Hints, makes `navigator.webdriver` undefined, populates `chrome.runtime`/`plugins`/`languages`, fixes `permissions.query` ↔ `Notification.permission` mismatch, adds 1-LSB noise to canvas readouts (`getImageData`/`toDataURL`/`toBlob`) and sub-audible noise to audio (`AudioBuffer.getChannelData`, `AnalyserNode.getFloatFrequencyData`). Real GPU via `--use-gl=angle --use-angle=default` so WebGL fingerprint reflects actual hardware instead of SwiftShader. `examples/stealth_check.py` probes a URL and prints the verdict. Toggleable per browser with `stealth=False`. 10 new tests, all green.
- Solver bridge + Cloudflare Turnstile (M3): `funbrowser.solver` subpackage with `FunSolverClient` (async httpx, 2captcha-style createTask/getTaskResult flow, balance check) and a CDP bridge that registers `Runtime.addBinding` for `window.__funbrowser_solve`, dispatches binding payloads to the funsolver client, and pushes results back via `Runtime.evaluate`. `Browser.start(api_key=..., auto_solve=True)` opt-in; `solver_base_url` override available. Turnstile detector + bootstrap inject through `Page.addScriptToEvaluateOnNewDocument` so the same flow works for both API-driven sessions and manual browsing. `examples/auto_solve.py` end-to-end demo. 7 new tests (5 unit on FunSolverClient with httpx.MockTransport + 2 integration that the solver globals install on a real Tab).
- Fingerprint customization (M2.5): new `funbrowser.fingerprint` subpackage with a `Fingerprint` dataclass (every field optional — `None` means "use Chrome's native value") and 7 ready-made presets (`windows_11_nvidia_rtx_4070`, `windows_10_intel_uhd_630`, `windows_11_amd_radeon_6700_xt`, `windows_10_laptop_low_end`, `macos_apple_silicon_m3_pro`, `macos_intel_iris`, `linux_intel_uhd`). `Browser.start(fingerprint=...)` plumbs the values into: `Network.setUserAgentOverride` (UA + Client Hints brands/platform/version/arch/bitness), `Emulation.setTimezoneOverride`, `Emulation.setLocaleOverride`, plus JS getters for `navigator.platform / hardwareConcurrency / deviceMemory / maxTouchPoints / languages`, `screen.width / height / availWidth / availHeight / colorDepth`, `window.devicePixelRatio`, and `WebGLRenderingContext.getParameter` vendor/renderer (with a docstring warning about the rendered-pixel-mismatch trap). `Fingerprint.merge(other)` layers overrides on a preset. `presets.by_label()` / `presets.filter_by_tag()` for lookup. `examples/custom_fingerprint.py` walks default / preset / preset+merge / fully-custom modes. 11 new tests (5 unit on presets + merge + 6 integration overriding navigator / WebGL / screen / timezone on real Chrome).
- Proxies + profiles (M5a): `funbrowser.proxy` module with a `Proxy` dataclass and a permissive `parse(...)` function that swallows every common format proxy providers ship — `scheme://user:pass@host:port`, `user:pass@host:port`, `host:port@user:pass`, `host:port:user:pass`, `user:pass:host:port`, `host:port:user`, plain `host:port` — auto-detecting layout by which segment carries a valid TCP port. HTTP/HTTPS auth is plumbed into Chrome via per-tab CDP `Fetch.enable` + `Fetch.continueWithAuth`; SOCKS auth surfaces a warning since Chrome doesn't expose it (front with a local HTTP proxy upstream). `funbrowser.start(proxy=...)` accepts either a string or a `Proxy`. New `funbrowser.Profile` helper (`Profile.ensure(name)`, `.exists`, `.delete`, `.list`) for persistent `user_data_dir`s under `./funbrowser_profiles/` (or `FUNBROWSER_PROFILES` env). 28 new tests (22 parser unit, 5 profile unit, 3 proxy integration on real Chrome).
- Production hardening cont. (M5b): `Tab.click` now generates real `Input.dispatchMouseEvent` `mouseMoved` + `mousePressed` + `mouseReleased` triplets at the element's bounding-box centre (with auto-scrollIntoView), so pages that gate on `event.isTrusted` accept the click. `Tab.goto(..., retries=N)` re-issues the navigation on `TimeoutError` up to N times. Multi-tab fan-out stress test verifies 8 concurrent `browser.get()` calls return correctly. Iframe stealth verified end-to-end — `Page.addScriptToEvaluateOnNewDocument` covers child frames, so `navigator.webdriver`, `chrome.runtime`, and `navigator.plugins` are patched inside iframes too. 6 new tests, 85 total.
- DX Tier S (M5.5): the "every-script" API ergonomics lift. New `funbrowser.ElementHandle` with chainable `click / focus / type / fill / hover / text / value / attribute / html / is_visible / bounding_box / query / query_all` — backed by stable CDP objectIds so the handle survives DOM mutations. `Tab.query(selector)` returns `ElementHandle | None` (no wait), `Tab.query_all(selector)` returns a list, `Tab.find(selector, timeout)` / `Tab.wait_for(selector, timeout)` poll until the element appears (`TimeoutError` otherwise), `Tab.exists(selector)` is a fast bool check (replaces the old `query_selector`). Auto-wait baked into `Tab.click / type / fill / hover / text / attribute / get_value` — single `await tab.fill("#email", "...")` instead of querySelector+wait+evaluate boilerplate. `Tab.type` uses `Input.insertText` (more reliable than synthesised keyDown/keyUp). `ElementHandle.click` briefly retries on a zero-size box so elements toggling from `display:none` "just work". New `Tab.block_urls(patterns)` / `Tab.unblock_urls()` via `Fetch.failRequest` with `BlockedByClient` — handy for cutting ad/tracker bandwidth. New `Browser.cookies / set_cookies / clear_cookies` via `Storage.*`. 12 new tests, 97 total. `examples/dx_tier_s.py` tours the API.
- Humanly mode (M5.5+): opt-in input timing & motion that reads like a real user. `funbrowser.HumanBehavior` dataclass with `funbrowser.humanly.DEFAULT` / `FAST` / `CAREFUL` presets. `funbrowser.start(humanly=True | False | HumanBehavior(...))`: mouse moves now trace a randomised cubic-Bezier curve with ease-in-out timing (15–70 intermediate `mouseMoved` events depending on profile) instead of teleporting; clicks hold for a random duration between `mousePressed` and `mouseReleased`; target hits include sub-pixel jitter from the centre; typing dispatches each character with a profile-random delay. `Tab` now tracks `_cursor` across operations so the next move starts from the last known position. 12 new tests (5 pure-Python on the math + 7 integration on real Chrome verifying mouseMoved count, click hold time, per-keystroke gaps, cursor tracking). `examples/humanly.py` walks all four profiles side-by-side (Instant / FAST / DEFAULT / CAREFUL) and prints `mouseMoved` event counts and wall-clock times. 109 tests total.
- Mobile presets + expanded catalog (M5.5+++): preset catalog grows from 7 to 17. Added 4 Android mobile presets (`android_pixel_8`, `android_galaxy_s23`, `android_pixel_6a`, `android_budget_galaxy_a52`) — each with realistic UA (built via new `_ua_android()` helper), `mobile=True`, `architecture="arm"`, `max_touch_points=5`, mobile screen sizes / DPR, and real Mali / Adreno WebGL strings. Added 5 more desktop presets (`windows_11_nvidia_rtx_4090`, `windows_11_nvidia_rtx_3070`, `windows_11_amd_rx_7900_xtx`, `windows_10_nvidia_gtx_1060`, `macos_apple_silicon_m2`, `linux_nvidia_desktop`). New tag coverage: `mobile`, `budget`, `arm`, `4k`, `ultrawide`, `mid-high`, `older`. No code-path changes — the existing JS + CDP pipeline already handles every Fingerprint field consistently. 4 new tests (catalog size, mobile correctness, desktop correctness, tag filter), 124 total.
- BrowserPool (M5.6): new `funbrowser.BrowserPool(size=N, **browser_kwargs)` — fleet of up to N concurrent Browser instances, created lazily on first use and kept alive between tasks. `pool.acquire()` is an async-context-manager (checkout/checkin); `pool.run(fn)` and `pool.run_all([fn1, fn2, ...])` dispatch callables across the pool, returning results. `proxies=[...]` distributes the list round-robin by browser creation order — combined with `geo_autoconfigure=True` (default) you get a fleet pinned to a different exit IP + timezone + locale per slot. `pool.stop()` (or `async with` exit) tears every browser down. Properties: `pool.size / .created / .idle / .busy / .browsers`. 9 tests (size validation, lazy spawn, browser reuse, concurrent fan-out, run, stop, proxy round-robin x3 different scenarios). 133 tests total. `examples/pool.py` fans 8 URLs across 3 browsers.
- Web Panel (M5.7): new `funbrowser.Panel(pool, host="127.0.0.1", port=8765)` — local aiohttp-based dashboard for a `BrowserPool`. Optional extra: `pip install funbrowser[panel]`. Single-page HTML+JS UI embedded in `panel.py`, no build step, no external assets — polls `/api/state` every 1.5s. Routes: `GET /` (HTML), `GET /api/state` (pool stats + browser list with proxy/geo/fingerprint/tabs), `POST /api/browser/{idx}/goto` (navigate a specific browser), `GET /api/browser/{idx}/screenshot` (PNG snapshot of the browser's first tab). `Panel` supports `async with` lifecycle; `panel.url / .host / .port` properties. 6 tests covering every endpoint. 139 tests total. `examples/panel.py` runs a 3-browser pool with the panel attached on `http://127.0.0.1:8765`.
- Anti-leak hardening (M5.5++): closes three concrete stealth gaps. (1) WebRTC IP leak — added launch flags `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` and `--disable-features=WebRtcHideLocalIpsWithMdns`, plus a JS-level `RTCPeerConnection` prototype wrap that strips `host` / `srflx` candidates from the SDP returned by `createOffer` / `createAnswer` / `setLocalDescription`. With these, the real IP no longer leaks through ICE even when the page actively probes WebRTC. (2) toString camouflage — installed `Function.prototype.toString` proxy that returns `'function name() { [native code] }'` for every getter our stealth pipeline registers (the proxy itself is registered so `Function.prototype.toString.toString()` also looks native). Closes the classic stealth-detection test: `Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver').get.toString()` now reports `'function () { [native code] }'`. (3) Geo auto-coupling — new `funbrowser.geo` module with `lookup_proxy_geo(proxy)` that routes an `ip-api.com` request through the proxy and returns `GeoInfo(timezone, country_code, locale, accept_language, ...)`. `funbrowser.start(geo_autoconfigure=True)` (default on) fills any `Fingerprint` field the caller didn't explicitly set with the geo-inferred values, so a US proxy gets a US timezone + `en-US` locale + matching Accept-Language automatically. Pass `geo_autoconfigure=False` to disable. 11 new tests (5 unit on locale/header helpers, 4 Chrome integration on toString camouflage + WebRTC SDP filtering + marker not exposed, 2 unit on geo lookup happy/failure via httpx.MockTransport). 120 tests total.
