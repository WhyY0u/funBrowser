"""Apply stealth patches to a Tab via CDP.

Two transport mechanisms:
- ``Network.setUserAgentOverride`` for UA + Client Hints metadata — must be
  applied BEFORE the first navigation so the very first request goes out
  with the spoofed identity.
- ``Page.addScriptToEvaluateOnNewDocument`` for JS patches — runs on every
  new document (top frame + iframes) before any page script. The same
  script also seeds ``window.__funbrowser_fp`` with the fingerprint values
  so individual patches can read whichever fields are set.
"""

from __future__ import annotations

import json
import sys
from importlib.resources import files
from typing import TYPE_CHECKING, Any

from ..fingerprint import Fingerprint
from ..fingerprint.presets import (
    CHROME_FULL_PLACEHOLDER,
    CHROME_MAJOR_PLACEHOLDER,
)

if TYPE_CHECKING:
    from ..tab import Tab

# Order matters — fingerprint globals + camouflage land first, cleanup last.
SCRIPTS = (
    "_camouflage.js",
    "webdriver.js",
    "chrome_runtime.js",
    "plugins.js",
    "languages.js",
    "permissions.js",
    "platform.js",
    "hardware.js",
    "screen_props.js",
    "webgl.js",
    "canvas_noise.js",
    "audio_noise.js",
    "webrtc.js",
    "_cleanup.js",
)


def _load_static_scripts() -> str:
    pkg = files("funbrowser.stealth.scripts")
    return "\n".join(pkg.joinpath(name).read_text(encoding="utf-8") for name in SCRIPTS)


_STATIC_SOURCE = _load_static_scripts()


def _platform_default() -> tuple[str, str, str]:
    if sys.platform == "win32":
        return ("Windows", "15.0.0", "x86")
    if sys.platform == "darwin":
        return ("macOS", "14.5.0", "arm")
    return ("Linux", "", "x86")


def _substitute(value: str | None, major: str, full: str) -> str | None:
    if value is None:
        return None
    return value.replace(CHROME_FULL_PLACEHOLDER, full).replace(CHROME_MAJOR_PLACEHOLDER, major)


def _resolve(
    fp: Fingerprint | None,
    raw_ua: str,
    chrome_full: str,
) -> dict[str, Any]:
    """Resolve a fingerprint against the live Chrome version into a plain dict."""
    chrome_major = chrome_full.split(".", 1)[0]
    default_platform, default_platform_version, default_arch = _platform_default()

    ua = _substitute((fp.user_agent if fp else None), chrome_major, chrome_full)
    if not ua:
        ua = raw_ua.replace("HeadlessChrome", "Chrome")

    if fp and fp.brands:
        brands = [
            {
                "brand": _substitute(b, chrome_major, chrome_full) or b,
                "version": _substitute(v, chrome_major, chrome_full) or v,
            }
            for b, v in fp.brands
        ]
    else:
        brands = [
            {"brand": "Chromium", "version": chrome_major},
            {"brand": "Google Chrome", "version": chrome_major},
            {"brand": "Not_A Brand", "version": "99"},
        ]

    platform = fp.platform if fp and fp.platform else default_platform
    platform_version = (
        fp.platform_version if fp and fp.platform_version is not None else default_platform_version
    )
    architecture = fp.architecture if fp and fp.architecture else default_arch
    bitness = fp.bitness if fp and fp.bitness else "64"
    mobile = bool(fp.mobile) if fp and fp.mobile is not None else False
    accept_language = fp.accept_language if fp and fp.accept_language else "en-US,en;q=0.9"

    return {
        "ua": ua,
        "accept_language": accept_language,
        "brands": brands,
        "platform": platform,
        "platform_version": platform_version,
        "architecture": architecture,
        "bitness": bitness,
        "mobile": mobile,
        "chrome_full": chrome_full,
    }


def _build_ua_override(resolved: dict[str, Any]) -> dict[str, Any]:
    return {
        "userAgent": resolved["ua"],
        "acceptLanguage": resolved["accept_language"],
        "platform": resolved["platform"],
        "userAgentMetadata": {
            "brands": resolved["brands"],
            "fullVersion": resolved["chrome_full"],
            "fullVersionList": [
                {"brand": b["brand"], "version": resolved["chrome_full"]}
                for b in resolved["brands"]
                if b["brand"] != "Not_A Brand"
            ]
            + [b for b in resolved["brands"] if b["brand"] == "Not_A Brand"],
            "platform": resolved["platform"],
            "platformVersion": resolved["platform_version"],
            "architecture": resolved["architecture"],
            "bitness": resolved["bitness"],
            "model": "",
            "mobile": resolved["mobile"],
            "wow64": False,
        },
    }


def _build_fp_globals(fp: Fingerprint | None, resolved: dict[str, Any]) -> dict[str, Any]:
    if fp is None:
        return {"platform": None}

    screen: dict[str, Any] = {}
    if fp.screen_width is not None:
        screen["width"] = fp.screen_width
    if fp.screen_height is not None:
        screen["height"] = fp.screen_height
    if fp.avail_width is not None:
        screen["availWidth"] = fp.avail_width
    if fp.avail_height is not None:
        screen["availHeight"] = fp.avail_height
    if fp.color_depth is not None:
        screen["colorDepth"] = fp.color_depth

    webgl: dict[str, Any] = {}
    if fp.webgl_vendor is not None:
        webgl["vendor"] = fp.webgl_vendor
    if fp.webgl_renderer is not None:
        webgl["renderer"] = fp.webgl_renderer

    payload: dict[str, Any] = {
        "platform": resolved["platform"],
        "architecture": resolved["architecture"],
        "languages": list(fp.languages) if fp.languages else None,
        "hardwareConcurrency": fp.hardware_concurrency,
        "deviceMemory": fp.device_memory,
        "maxTouchPoints": fp.max_touch_points,
        "devicePixelRatio": fp.device_pixel_ratio,
        "screen": screen or None,
        "webgl": webgl or None,
    }
    return {k: v for k, v in payload.items() if v is not None}


async def apply_stealth(tab: Tab, fingerprint: Fingerprint | None = None) -> None:
    """Apply stealth (Tier 1 + Tier 2) plus any fingerprint overrides."""
    version = await tab._cdp.send("Browser.getVersion")
    raw_ua = str(version.get("userAgent", ""))
    product = str(version.get("product", ""))
    chrome_full = product.split("/", 1)[-1] if "/" in product else "0.0.0.0"

    resolved = _resolve(fingerprint, raw_ua, chrome_full)
    await tab._send(
        "Network.setUserAgentOverride",
        _build_ua_override(resolved),
    )

    if fingerprint and fingerprint.timezone:
        await tab._send(
            "Emulation.setTimezoneOverride",
            {"timezoneId": fingerprint.timezone},
        )
    if fingerprint and fingerprint.locale:
        await tab._send(
            "Emulation.setLocaleOverride",
            {"locale": fingerprint.locale},
        )

    fp_globals = _build_fp_globals(fingerprint, resolved)
    fp_script = f"window.__funbrowser_fp = {json.dumps(fp_globals)};"

    await tab._send(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": fp_script + "\n" + _STATIC_SOURCE,
            "runImmediately": True,
        },
    )
