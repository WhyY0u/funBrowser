# L2 (TLS) + L3 (Engine) — design + status

Status of the two deepest stealth layers as of this commit.

## L2: TLS fingerprint

### M10a — `funbrowser.tls.ImpersonatedHTTPClient` — DONE

Script-level HTTP that picks the wire JA3/JA4 from real-browser profiles.
Uses `curl_cffi` under the hood. **Verified live**: hitting `tls.peet.ws`
returns three distinct JA4s for `chrome131` / `safari17_0` / `firefox133`.

```python
from funbrowser.tls import ImpersonatedHTTPClient

async with ImpersonatedHTTPClient(profile="chrome131") as c:
    r = await c.get("https://target.com/api/whatever")
```

Closes the gap for **script-side HTTP calls** during automation:
hit a site's API directly with the same TLS the browser tab is using.
Cookies can be carried from `Browser.cookies()` via `client.set_cookies()`.

### M10b — Mitm proxy for Chrome's own traffic — ALPHA

The harder problem: when Chrome itself talks to a site, the handshake is
real Chrome's. Most of the time that's actually correct ("Chrome looks
like Chrome"). The exceptions:

- Spoofing across OS (running on Linux but claiming to be Windows Chrome
  via UA → the TLS still says Linux Chrome)
- Spoofing Chrome version (Chrome 130 claiming to be Chrome 131 / a
  build Cloudflare hasn't flagged)
- Some Playwright/Puppeteer bundled chromium that has a different cipher
  list

**What ships now** (`funbrowser.tls.mitm.MitmProxy`):
- Root CA generation + persistence (works, 5/5 tests green)
- Per-host leaf cert minting signed by the CA (works)
- SPKI hash exposure for Chrome `--ignore-certificate-errors-spki-list=`
  (works — no OS keychain install needed)
- TCP server accepting HTTP CONNECT (works)
- Inline TLS termination + reissue via curl_cffi (works for HTTP/1.1
  GET/POST against typical APIs)

**What's still TODO for production-grade:**
- HTTP/1.1 keep-alive across multiple requests in one CONNECT tunnel
  (currently one request per CONNECT — slow but correct)
- HTTP/2 multiplexing — curl_cffi negotiates it, but bridging Chrome's
  HTTP/2 frames to curl_cffi's HTTP/2 needs frame-level parsing
- WebSocket upgrade — passes through Chrome's TLS, fails on curl_cffi
  side because the upstream connection is request/response oriented
- HTTP/3 (QUIC) — curl_cffi does not support it
- Streaming response bodies (currently buffers entire response)
- Cert revocation / rotation if root CA expires

**Realistic estimate** to lift the alpha to production: **3-5 days** of
focused work by an engineer comfortable with TLS state machines and
mitmproxy internals. The architecture is in place; the missing pieces
are HTTP/2 + WebSocket bridging.

The current implementation is shipped so callers with simple use cases
(API scraping where Chrome's TLS would otherwise be flagged) can already
benefit, while the WS/HTTP-2 gaps are documented and called out.

## L3: Engine-layer (C++ patches)

### M11a — Backend abstraction — design only

Two real paths to deeper stealth than JS injection can provide:

#### Path A: Camoufox backend (recommended)

Camoufox = pre-patched Firefox fork with C++-level anti-fingerprint
patches. Active maintenance, MPL license, prebuilt binaries.

What needs to happen:

1. **Backend abstraction**: introduce `BrowserBackend` ABC with two
   implementations:
   - `ChromeBackend` (current Browser code, renamed)
   - `CamoufoxBackend` (new)
2. **Protocol bridge**: Camoufox uses Playwright protocol over a
   WebSocket, not CDP. Either:
   - Add `playwright` as optional dep and use it to control Camoufox
   - Or implement a thin Playwright client (similar effort to our CDP
     client)
3. **Feature parity**: Tab API, ElementHandle, click, type, fill,
   screenshot — all the SDK surface — re-mapped to Playwright calls
4. **Solver bridge**: re-implement `Page.addScriptToEvaluateOnNewDocument`
   equivalent for Playwright (it has `page.add_init_script`)
5. **Stealth scripts**: most of `funbrowser/stealth/scripts/*.js` would
   become redundant (Camoufox patches them at C++ level), but the
   solver detector scripts still need injection
6. **Fingerprint**: Camoufox has its own fingerprint API; map our
   `Fingerprint` → Camoufox config
7. **Pool + Panel**: backend-agnostic by construction

**Realistic estimate**: **1-2 weeks** of focused work. The biggest item
is the Playwright protocol bridge if we keep `playwright` out of deps;
about 4 days if we accept `playwright` as a (heavy) optional dep.

#### Path B: Fork ungoogled-chromium with our own patches

Months of work:
- 50+ GB source checkout
- Per-platform build matrix (Win/macOS/Linux, ~2-4h per build)
- Patches on Blink (navigator, Runtime), Skia (canvas), BoringSSL (TLS),
  WebGL/ANGLE
- Track upstream releases every 2-3 weeks
- CI for binary distribution

Not recommended unless the team scales up. Path A is the
single-developer-sized version.

### Status: design only, no implementation yet

`Browser.start(backend="camoufox")` would raise `NotImplementedError`.
The backend abstraction itself is intentionally not introduced today
because it would be a no-op refactor (one impl) — better to wait until
the Camoufox impl actually lands to avoid churn.

## What an honest comparison looks like

| Layer | Best-case stealth | FunBrowser today |
|---|---|---|
| L1 (JS) | C++-patched browser | ✅ Full JS coverage (M2 + M2.5 + M5.5++) |
| L2 (TLS) | Native browser TLS | ⚠️ Script-level done (M10a). Browser-traffic alpha (M10b). Production-grade TLS spoofing across the board is **multi-day work**. |
| L3 (Engine) | C++ patches in browser | ❌ Not started. Camoufox integration is **1-2 weeks**, own fork is **months**. |

For the typical antibot encounter (Cloudflare standard, DataDome standard,
PerimeterX, Akamai mid) the L1 work in this repo passes. Topbots
(Cloudflare Enterprise, DataDome heavy, Kasada, Akamai Premier) need
L2 + L3 to reliably defeat. We've shipped the foundation for L2 and
documented the L3 path.
