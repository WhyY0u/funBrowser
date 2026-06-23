"""Apply stealth patches to a Tab via CDP.

Two transport mechanisms:
- ``Network.setUserAgentOverride`` for UA + Client Hints metadata — must be
  applied BEFORE the first navigation so the very first request goes out
  with the spoofed identity.
- ``Page.addScriptToEvaluateOnNewDocument`` for JS patches — runs on every
  new document (top frame + iframes) before any page script.
"""

from __future__ import annotations

import sys
from importlib.resources import files
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..tab import Tab

SCRIPTS = (
    "webdriver.js",
    "chrome_runtime.js",
    "plugins.js",
    "languages.js",
    "permissions.js",
    "canvas_noise.js",
    "audio_noise.js",
)


def _load_scripts() -> str:
    pkg = files("funbrowser.stealth.scripts")
    parts = [pkg.joinpath(name).read_text(encoding="utf-8") for name in SCRIPTS]
    return "\n".join(parts)


_SCRIPT_SOURCE = _load_scripts()


def _platform_metadata() -> tuple[str, str, str]:
    if sys.platform == "win32":
        return ("Windows", "15.0.0", "x86")
    if sys.platform == "darwin":
        return ("macOS", "14.5.0", "arm")
    return ("Linux", "", "x86")


def _build_ua_override(ua: str, full_version: str) -> dict[str, Any]:
    major = full_version.split(".", 1)[0]
    platform, platform_version, arch = _platform_metadata()
    return {
        "userAgent": ua,
        "acceptLanguage": "en-US,en;q=0.9",
        "platform": platform,
        "userAgentMetadata": {
            "brands": [
                {"brand": "Chromium", "version": major},
                {"brand": "Google Chrome", "version": major},
                {"brand": "Not_A Brand", "version": "99"},
            ],
            "fullVersion": full_version,
            "fullVersionList": [
                {"brand": "Chromium", "version": full_version},
                {"brand": "Google Chrome", "version": full_version},
                {"brand": "Not_A Brand", "version": "99.0.0.0"},
            ],
            "platform": platform,
            "platformVersion": platform_version,
            "architecture": arch,
            "bitness": "64",
            "model": "",
            "mobile": False,
            "wow64": False,
        },
    }


async def apply_stealth(tab: Tab) -> None:
    """Apply Tier-1 + Tier-2 stealth to a freshly-attached Tab."""
    version = await tab._cdp.send("Browser.getVersion")
    raw_ua = str(version.get("userAgent", ""))
    product = str(version.get("product", ""))
    # 'HeadlessChrome/130.0.6723.69' -> '130.0.6723.69'
    full_version = product.split("/", 1)[-1] if "/" in product else "0.0.0.0"
    clean_ua = raw_ua.replace("HeadlessChrome", "Chrome")

    await tab._send(
        "Network.setUserAgentOverride",
        _build_ua_override(clean_ua, full_version),
    )
    await tab._send(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": _SCRIPT_SOURCE, "runImmediately": True},
    )
