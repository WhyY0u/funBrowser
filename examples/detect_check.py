"""Self-audit: run every fingerprint / antidetect probe the testers use.

Prints a PASS/FAIL line for each of ~25 checks plus a final summary.
Honest about what's covered (JS-layer + GPU + WebRTC + timing) and what
isn't (TLS JA3/JA4 — that's M10).

    uv run python examples/detect_check.py
"""

from __future__ import annotations

import asyncio
import sys

import funbrowser

CHECKS_JS = """
(async () => {
  const out = {};

  // ── navigator basics ─────────────────────────────────────────────────
  out.webdriver_undefined = navigator.webdriver === undefined;
  out.ua_no_headless = !navigator.userAgent.includes('HeadlessChrome');
  out.ua_no_phantomjs = !navigator.userAgent.toLowerCase().includes('phantom');
  out.plugins_populated = navigator.plugins.length >= 3;
  out.languages_populated = Array.isArray(navigator.languages) && navigator.languages.length > 0;
  out.platform_string_set = typeof navigator.platform === 'string' && navigator.platform.length > 0;
  out.hwconcurrency_positive = navigator.hardwareConcurrency > 0;
  out.devicememory_present = typeof navigator.deviceMemory === 'number';
  out.maxtouchpoints_int = Number.isInteger(navigator.maxTouchPoints);

  // ── chrome / iframe / window ────────────────────────────────────────
  out.window_chrome = typeof window.chrome === 'object' && window.chrome !== null;
  out.chrome_runtime = !!(window.chrome && window.chrome.runtime);
  out.chrome_runtime_oninstalled = !!(window.chrome?.runtime?.OnInstalledReason);

  // ── permissions.query consistency ───────────────────────────────────
  try {
    const p = await navigator.permissions.query({name: 'notifications'});
    out.permissions_consistent = p.state !== 'denied' || Notification.permission === 'denied';
  } catch (e) { out.permissions_consistent = false; }

  // ── toString camouflage (the classic stealth-detection probe) ───────
  out.webdriver_get_native = (() => {
    const d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
    return d?.get?.toString()?.includes('[native code]') ?? false;
  })();
  out.fn_tostring_native = Function.prototype.toString.toString().includes('[native code]');
  out.fb_marker_hidden = typeof window.__fb_m === 'undefined';

  // ── WebGL ───────────────────────────────────────────────────────────
  const gl = document.createElement('canvas').getContext('webgl');
  if (gl) {
    out.webgl_available = true;
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = ext
      ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
      : gl.getParameter(gl.RENDERER);
    out.webgl_not_swiftshader = !/SwiftShader|software/i.test(String(renderer));
    out.webgl_renderer = String(renderer);
  } else {
    out.webgl_available = false;
    out.webgl_not_swiftshader = false;
  }

  // ── canvas noise (two reads of the same canvas should differ) ──────
  try {
    const c = document.createElement('canvas'); c.width = 100; c.height = 60;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#abc'; ctx.fillRect(0, 0, 100, 60);
    ctx.fillStyle = '#000'; ctx.font = '14px serif';
    ctx.fillText('funbrowser', 4, 30);
    out.canvas_noisy = c.toDataURL() !== c.toDataURL();
  } catch (e) { out.canvas_noisy = false; }

  // ── audio noise ─────────────────────────────────────────────────────
  try {
    const ac = new OfflineAudioContext(1, 4096, 44100);
    const buf = ac.createBuffer(1, 4096, 44100);
    const a = Array.from(buf.getChannelData(0)).slice(0, 16).join(',');
    const b = Array.from(buf.getChannelData(0)).slice(0, 16).join(',');
    out.audio_noisy = a !== b;
  } catch (e) { out.audio_noisy = false; }

  // ── WebRTC: createOffer SDP must not have host candidates ───────────
  try {
    const pc = new RTCPeerConnection({iceServers: []});
    pc.createDataChannel('x');
    const offer = await pc.createOffer();
    pc.close();
    out.webrtc_no_host_candidate = !/\\sa=candidate:.*\\shost\\s/i.test(offer.sdp || '');
  } catch (e) { out.webrtc_no_host_candidate = true; }

  // ── error stack should not leak puppeteer/playwright markers ────────
  try { throw new Error(); } catch (e) {
    const stack = e.stack || '';
    out.stack_no_puppeteer = !/puppeteer|playwright|cdp/i.test(stack);
  }

  // ── iframe stealth propagation ──────────────────────────────────────
  await new Promise((resolve) => {
    const f = document.createElement('iframe');
    f.src = 'about:blank';
    f.onload = () => {
      const w = f.contentWindow;
      out.iframe_no_webdriver = w.navigator.webdriver === undefined;
      out.iframe_has_chrome_runtime = !!(w.chrome && w.chrome.runtime);
      out.iframe_plugins_populated = w.navigator.plugins.length >= 3;
      resolve();
    };
    document.body.appendChild(f);
  });

  return out;
})()
"""


COVERED = """
[+] Covered by FunBrowser:
  - JS-layer fingerprint (UA, navigator.*, chrome.runtime, plugins, languages)
  - WebGL on real GPU (not SwiftShader)
  - Canvas + Audio noise injection
  - WebRTC IP leak block (flags + JS SDP filter)
  - toString '[native code]' camouflage on patched getters
  - Permissions.query / Notification.permission consistency
  - Screen / DPR / hardwareConcurrency / deviceMemory / maxTouchPoints
  - Timezone + locale auto-coupled to proxy exit IP (geo_autoconfigure)
  - iframe stealth propagation
  - Humanly mode (Bezier mouse, click hold, typing rhythm)
"""

NOT_COVERED = """
[-] NOT covered yet (known limitations):
  - TLS JA3/JA4 fingerprint  -> Chrome's TLS handshake still reads as Chrome
                               (only matters vs DataDome / Kasada / Akamai
                               top-tier; M10 on roadmap)
  - Pixel-perfect WebGL spoofing  -> if you override webgl_renderer to lie
                                     about the GPU, the rendered output stays
                                     real (M9 on roadmap)
  - Real-user fingerprint pool  -> currently using internally-consistent
                                   presets; not pulled from a database of
                                   actual human fingerprints (M8)
  - Battery / Bluetooth / USB / Web Authn API consistency  -> could be
                                                              probed in
                                                              dedicated suites
"""


async def main() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        result = await tab.evaluate(CHECKS_JS)

    print()
    print("FunBrowser self-audit")
    print("=" * 60)

    grouped = {
        "navigator.* basics": [
            "webdriver_undefined",
            "ua_no_headless",
            "ua_no_phantomjs",
            "plugins_populated",
            "languages_populated",
            "platform_string_set",
            "hwconcurrency_positive",
            "devicememory_present",
            "maxtouchpoints_int",
        ],
        "chrome runtime + iframe": [
            "window_chrome",
            "chrome_runtime",
            "chrome_runtime_oninstalled",
            "iframe_no_webdriver",
            "iframe_has_chrome_runtime",
            "iframe_plugins_populated",
        ],
        "stealth-detection probes": [
            "webdriver_get_native",
            "fn_tostring_native",
            "fb_marker_hidden",
            "permissions_consistent",
            "stack_no_puppeteer",
        ],
        "WebGL / canvas / audio": [
            "webgl_available",
            "webgl_not_swiftshader",
            "canvas_noisy",
            "audio_noisy",
        ],
        "WebRTC IP leak": [
            "webrtc_no_host_candidate",
        ],
    }

    total = 0
    passed = 0
    for group_name, keys in grouped.items():
        print(f"\n[{group_name}]")
        for k in keys:
            v = result.get(k)
            ok = v is True
            total += 1
            if ok:
                passed += 1
            tag = "PASS" if ok else "FAIL"
            print(f"  {tag}  {k}")

    print()
    print(f"renderer:  {result.get('webgl_renderer', '?')}")
    print()
    print(f"score:     {passed}/{total}  ({passed * 100 // total}%)")
    print(COVERED)
    print(NOT_COVERED)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
