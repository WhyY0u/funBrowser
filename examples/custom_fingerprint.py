"""Spoof the browser identity using a preset or a custom Fingerprint.

uv run python examples/custom_fingerprint.py
"""

from __future__ import annotations

import asyncio

import funbrowser
from funbrowser import Fingerprint, presets

PROBE_JS = """
({
  ua: navigator.userAgent,
  platform: navigator.platform,
  cores: navigator.hardwareConcurrency,
  memory: navigator.deviceMemory,
  langs: navigator.languages,
  screen: { w: screen.width, h: screen.height, dpr: window.devicePixelRatio },
  tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  webgl: (() => {
    const gl = document.createElement('canvas').getContext('webgl');
    const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
    return ext ? {
      vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
      renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
    } : null;
  })(),
})
"""


async def probe(label: str, fp: Fingerprint | None) -> None:
    print(f"\n--- {label} ---")
    async with await funbrowser.start(headless=True, fingerprint=fp) as browser:
        tab = await browser.get("https://example.com")
        info = await tab.evaluate(PROBE_JS)
        for k, v in info.items():
            print(f"  {k:9} = {v}")


async def main() -> None:
    # 1. Default — no fingerprint, real GPU, current OS
    await probe("Default (no fingerprint)", None)

    # 2. Preset — Windows + AMD
    await probe(
        "Preset: windows_11_amd_radeon_6700_xt",
        presets.windows_11_amd_radeon_6700_xt(),
    )

    # 3. Preset + custom override — base preset with Tokyo timezone + Japanese locale
    custom = presets.macos_apple_silicon_m3_pro().merge(
        Fingerprint(
            timezone="Asia/Tokyo",
            languages=("ja-JP", "ja", "en"),
            accept_language="ja-JP,ja;q=0.9,en;q=0.8",
        )
    )
    await probe("Preset (mac M3) + Tokyo overrides", custom)

    # 4. Fully custom
    await probe(
        "Fully custom",
        Fingerprint(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            platform="Windows",
            hardware_concurrency=16,
            device_memory=8,
            screen_width=1920,
            screen_height=1080,
            webgl_vendor="Google Inc. (NVIDIA)",
            webgl_renderer=("ANGLE (NVIDIA, NVIDIA GeForce RTX 3060, D3D11)"),
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
