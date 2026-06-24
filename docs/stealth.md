# Stealth layer

FunBrowser ships with stealth turned **on by default**. Turn it off with
`stealth=False` for tests or debugging.

## What's covered

Run the self-audit any time:

```bash
uv run python examples/detect_check.py
```

The audit verifies 25 individual probes across five groups. As of v0.1
all 25 pass on the default configuration.

### navigator.* surface (Tier 1)

| Probe | Patch source |
|---|---|
| `navigator.webdriver` is `undefined` | `webdriver.js` |
| UA + Client Hints contain "Chrome", not "HeadlessChrome" | `Network.setUserAgentOverride` |
| `navigator.plugins.length >= 3` | `plugins.js` |
| `navigator.languages` populated | `languages.js` |
| `navigator.platform` set | `platform.js` |
| `navigator.hardwareConcurrency > 0` | `hardware.js` |
| `navigator.deviceMemory` is a number | `hardware.js` |
| `navigator.maxTouchPoints` is an int | `hardware.js` |
| `window.chrome.runtime.OnInstalledReason` exists | `chrome_runtime.js` |
| `navigator.permissions.query` consistent with `Notification.permission` | `permissions.js` |

### iframe propagation

Every patch above also lands inside iframes because
`Page.addScriptToEvaluateOnNewDocument` covers child frames natively.

### Stealth-detection probes (the meta-layer)

These are the JS queries every serious antibot runs to catch
defineProperty-based stealth libraries.

| Probe | Defence |
|---|---|
| `Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver').get.toString()` returns `'function () { [native code] }'` | `_camouflage.js` — installs a wrapped `Function.prototype.toString` that returns the native-looking string for every getter we register |
| `Function.prototype.toString.toString()` itself is camouflaged | same — the wrapper registers itself |
| `window.__fb_m` (our internal helper) is not enumerable on `window` after script load | `_cleanup.js` deletes it after the patch chain runs |
| `e.stack` after `throw new Error()` doesn't mention puppeteer / playwright / cdp | we don't use Playwright or Puppeteer, and Chrome's stack frames don't reference them |

### GPU / canvas / audio

| Probe | Defence |
|---|---|
| WebGL renderer is **not** SwiftShader | `--use-gl=angle --use-angle=default --ignore-gpu-blocklist` launch flags |
| Two `toDataURL()` reads of the same canvas differ | `canvas_noise.js` adds 1-LSB noise on `getImageData` / `toDataURL` / `toBlob` |
| Two `getChannelData()` reads differ on an `OfflineAudioContext` | `audio_noise.js` adds sub-audible noise on `getChannelData` / `copyFromChannel` / `getFloatFrequencyData` |

### WebRTC IP leak

| Probe | Defence |
|---|---|
| `RTCPeerConnection.createOffer()` SDP contains no `a=candidate ... host` lines | `webrtc.js` strips host and srflx candidates from the SDP, plus `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` and `--disable-features=WebRtcHideLocalIpsWithMdns` launch flags |

## Per-tab fingerprint override

Pass a `Fingerprint` to swap any of: UA, Client Hints, platform,
hardware concurrency, device memory, touch points, screen dimensions,
device-pixel-ratio, languages, timezone, locale, WebGL vendor /
renderer.

```python
from funbrowser import Fingerprint, presets

# pre-rolled
fp = presets.windows_11_amd_radeon_6700_xt()

# preset + overrides
fp = presets.macos_apple_silicon_m3_pro().merge(
    Fingerprint(timezone="Asia/Tokyo", languages=("ja-JP", "ja", "en"))
)

# fully custom
fp = Fingerprint(
    user_agent="Mozilla/5.0 ... Chrome/131.0.0.0 ...",
    hardware_concurrency=16,
    device_memory=8,
    webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 ...)",
)

async with await funbrowser.start(fingerprint=fp) as browser: ...
```

### Caveat — WebGL renderer string vs rendered pixels

If you override `webgl_renderer` to "RTX 4090" but your actual GPU is
something else, the *strings* match but the *rendered output* will not.
Top-tier antibots compare the claimed renderer against a known
pixel-output database and flag the mismatch. Pixel-level rendering
spoofing is M9 (deep WebGL / canvas / shader work) and not in v0.1.

For typical antibots (Cloudflare standard, DataDome standard,
PerimeterX, Akamai mid) the string override is enough.

## What's not covered yet

- **TLS JA3/JA4 spoofing of Chrome's own traffic** — see
  [M10_M11_DESIGN.md](M10_M11_DESIGN.md). Script-level
  `ImpersonatedHTTPClient` ships and works.
- **C++ engine-layer patches** — Camoufox-style work is in the roadmap.
  Workaround for v0.1: the JS layer is comprehensive enough for typical
  use cases. If you need engine-level protection, wait for M11 or
  combine FunBrowser with Camoufox externally.

## Compared to common alternatives

| | FunBrowser | puppeteer-extra-stealth | undetected-chromedriver | Camoufox |
|---|---|---|---|---|
| Stealth Tier 1 | full | partial | partial | full |
| toString camouflage by default | **yes** | optional plugin | no | yes |
| Real GPU WebGL | yes | optional | optional | yes |
| Canvas + audio noise | yes | yes (plugin) | partial | yes |
| WebRTC SDP filter | yes | yes (plugin) | no | yes |
| C++-level patches | no (M11) | no | no | **yes** |
| TLS impersonation (script) | yes | no | no | no |
| Built-in captcha solver | **funsolver** | bring your own | bring your own | bring your own |
| Python async SDK | yes | Node | Python (sync) | both |
