"""Probe a stealth-fingerprint endpoint and print the verdict.

Defaults to bot.sannysoft.com (cheap, no captcha, returns DOM rows).
Pass a different URL on the CLI to probe e.g. browserscan.io.

    uv run python examples/stealth_check.py
    uv run python examples/stealth_check.py https://abrahamjuliot.github.io/creepjs/
"""

from __future__ import annotations

import asyncio
import sys

import funbrowser

DEFAULT_URL = "https://bot.sannysoft.com/"

PROBE_JS = """
({
  webdriver: navigator.webdriver,
  ua: navigator.userAgent,
  plugins: navigator.plugins.length,
  languages: navigator.languages,
  hasChrome: typeof window.chrome === 'object',
  hasChromeRuntime: typeof window.chrome?.runtime === 'object',
  webgl: (() => {
    try {
      const c = document.createElement('canvas');
      const gl = c.getContext('webgl');
      if (!gl) return null;
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      return {
        vendor: ext && gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
        renderer: ext && gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
      };
    } catch (e) { return { error: String(e) }; }
  })(),
})
"""


async def main(url: str) -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get(url)
        info = await tab.evaluate(PROBE_JS)
        for k, v in info.items():
            print(f"{k:18} = {v}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    asyncio.run(main(target))
