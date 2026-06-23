"""Concrete Fingerprint presets covering common desktop and mobile configurations.

The brand list embedded in each preset uses ``CHROME_MAJOR_PLACEHOLDER`` for
the Chrome major version — it's substituted by ``apply_stealth`` at attach
time using the actual installed Chrome's version, so the UA-CH brands stay
consistent with reality even when Chrome auto-updates.

If you need a fingerprint not covered here, build a :class:`Fingerprint`
directly or :meth:`Fingerprint.merge` a preset with your overrides.
"""

from __future__ import annotations

from .data import Fingerprint

CHROME_MAJOR_PLACEHOLDER = "{CHROME_MAJOR}"
CHROME_FULL_PLACEHOLDER = "{CHROME_FULL}"


def _ua_windows(chrome: str = CHROME_FULL_PLACEHOLDER) -> str:
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome} Safari/537.36"
    )


def _ua_macos(chrome: str = CHROME_FULL_PLACEHOLDER) -> str:
    # Chrome on macOS freezes the OS bit at 10_15_7 since 100.0 for anti-fp.
    return (
        f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome} Safari/537.36"
    )


def _ua_linux(chrome: str = CHROME_FULL_PLACEHOLDER) -> str:
    return (
        f"Mozilla/5.0 (X11; Linux x86_64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome} Safari/537.36"
    )


def _ua_android(model: str, android_version: str, chrome: str = CHROME_FULL_PLACEHOLDER) -> str:
    return (
        f"Mozilla/5.0 (Linux; Android {android_version}; {model}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome} "
        f"Mobile Safari/537.36"
    )


_DEFAULT_BRANDS: tuple[tuple[str, str], ...] = (
    ("Chromium", CHROME_MAJOR_PLACEHOLDER),
    ("Google Chrome", CHROME_MAJOR_PLACEHOLDER),
    ("Not_A Brand", "99"),
)


# ── Windows ──────────────────────────────────────────────────────────────


def windows_11_nvidia_rtx_4070() -> Fingerprint:
    return Fingerprint(
        label="Windows 11 / NVIDIA RTX 4070 / 16C32T / 32GB",
        tags=("windows", "nvidia", "high-end", "desktop"),
        user_agent=_ua_windows(),
        accept_language="en-US,en;q=0.9",
        platform="Windows",
        platform_version="15.0.0",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=32,
        device_memory=8,
        max_touch_points=0,
        screen_width=2560,
        screen_height=1440,
        avail_width=2560,
        avail_height=1392,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer=(
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 (0x00002786) Direct3D11 vs_5_0 ps_5_0, D3D11)"
        ),
    )


def windows_10_intel_uhd_630() -> Fingerprint:
    return Fingerprint(
        label="Windows 10 / Intel UHD 630 / 8C16T / 16GB",
        tags=("windows", "intel", "mid", "desktop"),
        user_agent=_ua_windows(),
        accept_language="en-US,en;q=0.9",
        platform="Windows",
        platform_version="10.0.0",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=16,
        device_memory=8,
        max_touch_points=0,
        screen_width=1920,
        screen_height=1080,
        avail_width=1920,
        avail_height=1040,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer=(
            "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E9B) Direct3D11 vs_5_0 ps_5_0, D3D11)"
        ),
    )


def windows_11_amd_radeon_6700_xt() -> Fingerprint:
    return Fingerprint(
        label="Windows 11 / AMD Radeon RX 6700 XT / 12C24T / 32GB",
        tags=("windows", "amd", "high-end", "desktop"),
        user_agent=_ua_windows(),
        accept_language="en-US,en;q=0.9",
        platform="Windows",
        platform_version="15.0.0",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=24,
        device_memory=8,
        max_touch_points=0,
        screen_width=2560,
        screen_height=1440,
        avail_width=2560,
        avail_height=1392,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="Google Inc. (AMD)",
        webgl_renderer=("ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    )


def windows_10_laptop_low_end() -> Fingerprint:
    return Fingerprint(
        label="Windows 10 / Intel HD 4400 / 4C / 8GB / 1366x768",
        tags=("windows", "intel", "low-end", "laptop"),
        user_agent=_ua_windows(),
        accept_language="en-US,en;q=0.9",
        platform="Windows",
        platform_version="10.0.0",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=4,
        device_memory=8,
        max_touch_points=0,
        screen_width=1366,
        screen_height=768,
        avail_width=1366,
        avail_height=728,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer=("ANGLE (Intel, Intel(R) HD Graphics 4400 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    )


# ── macOS ────────────────────────────────────────────────────────────────


def macos_apple_silicon_m3_pro() -> Fingerprint:
    return Fingerprint(
        label="macOS Sonoma / Apple M3 Pro / 12C / 36GB / 1728x1117",
        tags=("macos", "apple-silicon", "high-end", "laptop"),
        user_agent=_ua_macos(),
        accept_language="en-US,en;q=0.9",
        platform="macOS",
        platform_version="14.6.0",
        architecture="arm",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=12,
        device_memory=8,
        max_touch_points=0,
        screen_width=1728,
        screen_height=1117,
        avail_width=1728,
        avail_height=1079,
        color_depth=30,
        device_pixel_ratio=2.0,
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Pro, Unspecified Version)",
    )


def macos_intel_iris() -> Fingerprint:
    return Fingerprint(
        label="macOS Big Sur / Intel Iris Plus 645 / 8C / 16GB / 1440x900",
        tags=("macos", "intel", "mid", "laptop"),
        user_agent=_ua_macos(),
        accept_language="en-US,en;q=0.9",
        platform="macOS",
        platform_version="11.7.10",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=8,
        device_memory=8,
        max_touch_points=0,
        screen_width=1440,
        screen_height=900,
        avail_width=1440,
        avail_height=875,
        color_depth=24,
        device_pixel_ratio=2.0,
        webgl_vendor="Google Inc. (Intel Inc.)",
        webgl_renderer="ANGLE (Intel Inc., Intel(R) Iris(TM) Plus Graphics 645, OpenGL 4.1)",
    )


# ── Windows (extra) ──────────────────────────────────────────────────────


def windows_11_nvidia_rtx_4090() -> Fingerprint:
    return Fingerprint(
        label="Windows 11 / NVIDIA RTX 4090 / 24C32T / 64GB / 3840x2160",
        tags=("windows", "nvidia", "high-end", "desktop", "4k"),
        user_agent=_ua_windows(),
        accept_language="en-US,en;q=0.9",
        platform="Windows",
        platform_version="15.0.0",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=32,
        device_memory=8,
        max_touch_points=0,
        screen_width=3840,
        screen_height=2160,
        avail_width=3840,
        avail_height=2112,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer=(
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 (0x00002684) Direct3D11 vs_5_0 ps_5_0, D3D11)"
        ),
    )


def windows_11_nvidia_rtx_3070() -> Fingerprint:
    return Fingerprint(
        label="Windows 11 / NVIDIA RTX 3070 / 12C20T / 32GB / 2560x1440",
        tags=("windows", "nvidia", "mid-high", "desktop"),
        user_agent=_ua_windows(),
        accept_language="en-US,en;q=0.9",
        platform="Windows",
        platform_version="15.0.0",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=20,
        device_memory=8,
        max_touch_points=0,
        screen_width=2560,
        screen_height=1440,
        avail_width=2560,
        avail_height=1392,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer=(
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 (0x00002484) Direct3D11 vs_5_0 ps_5_0, D3D11)"
        ),
    )


def windows_11_amd_rx_7900_xtx() -> Fingerprint:
    return Fingerprint(
        label="Windows 11 / AMD RX 7900 XTX / 16C32T / 64GB / 3440x1440",
        tags=("windows", "amd", "high-end", "desktop", "ultrawide"),
        user_agent=_ua_windows(),
        accept_language="en-US,en;q=0.9",
        platform="Windows",
        platform_version="15.0.0",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=32,
        device_memory=8,
        max_touch_points=0,
        screen_width=3440,
        screen_height=1440,
        avail_width=3440,
        avail_height=1392,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="Google Inc. (AMD)",
        webgl_renderer=("ANGLE (AMD, AMD Radeon RX 7900 XTX Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    )


def windows_10_nvidia_gtx_1060() -> Fingerprint:
    return Fingerprint(
        label="Windows 10 / NVIDIA GTX 1060 / 8C16T / 16GB / 1920x1080",
        tags=("windows", "nvidia", "mid", "desktop", "older"),
        user_agent=_ua_windows(),
        accept_language="en-US,en;q=0.9",
        platform="Windows",
        platform_version="10.0.0",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=16,
        device_memory=8,
        max_touch_points=0,
        screen_width=1920,
        screen_height=1080,
        avail_width=1920,
        avail_height=1040,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer=(
            "ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB "
            "(0x00001C03) Direct3D11 vs_5_0 ps_5_0, D3D11)"
        ),
    )


# ── macOS (extra) ────────────────────────────────────────────────────────


def macos_apple_silicon_m2() -> Fingerprint:
    return Fingerprint(
        label="macOS Ventura / Apple M2 / 8C / 16GB / 1512x982",
        tags=("macos", "apple-silicon", "mid", "laptop"),
        user_agent=_ua_macos(),
        accept_language="en-US,en;q=0.9",
        platform="macOS",
        platform_version="13.6.0",
        architecture="arm",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=8,
        device_memory=8,
        max_touch_points=0,
        screen_width=1512,
        screen_height=982,
        avail_width=1512,
        avail_height=944,
        color_depth=30,
        device_pixel_ratio=2.0,
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
    )


# ── Linux (extra) ────────────────────────────────────────────────────────


def linux_nvidia_desktop() -> Fingerprint:
    return Fingerprint(
        label="Linux / NVIDIA RTX 3060 / 12C24T / 32GB / 2560x1440",
        tags=("linux", "nvidia", "high-end", "desktop"),
        user_agent=_ua_linux(),
        accept_language="en-US,en;q=0.9",
        platform="Linux",
        platform_version="",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=24,
        device_memory=8,
        max_touch_points=0,
        screen_width=2560,
        screen_height=1440,
        avail_width=2560,
        avail_height=1413,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="NVIDIA Corporation",
        webgl_renderer="NVIDIA GeForce RTX 3060/PCIe/SSE2",
    )


# ── Android Mobile ───────────────────────────────────────────────────────


def android_pixel_8() -> Fingerprint:
    """Google Pixel 8 / Android 14 / Tensor G3 / Mali-G715."""
    return Fingerprint(
        label="Android 14 / Pixel 8 / Tensor G3 / Mali-G715 / 412x915",
        tags=("android", "mobile", "high-end", "google", "arm"),
        user_agent=_ua_android("Pixel 8", "14"),
        accept_language="en-US,en;q=0.9",
        platform="Android",
        platform_version="14.0.0",
        architecture="arm",
        bitness="64",
        mobile=True,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=9,
        device_memory=8,
        max_touch_points=5,
        screen_width=412,
        screen_height=915,
        avail_width=412,
        avail_height=915,
        color_depth=24,
        device_pixel_ratio=2.625,
        webgl_vendor="ARM",
        webgl_renderer="Mali-G715-Immortalis MC10 r43p0",
    )


def android_galaxy_s23() -> Fingerprint:
    """Samsung Galaxy S23 / Android 14 / Snapdragon 8 Gen 2 / Adreno 740."""
    return Fingerprint(
        label="Android 14 / Galaxy S23 / Snapdragon 8 Gen 2 / Adreno 740 / 360x780",
        tags=("android", "mobile", "high-end", "samsung", "arm"),
        user_agent=_ua_android("SM-S911B", "14"),
        accept_language="en-US,en;q=0.9",
        platform="Android",
        platform_version="14.0.0",
        architecture="arm",
        bitness="64",
        mobile=True,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=8,
        device_memory=8,
        max_touch_points=5,
        screen_width=360,
        screen_height=780,
        avail_width=360,
        avail_height=780,
        color_depth=24,
        device_pixel_ratio=3.0,
        webgl_vendor="Qualcomm",
        webgl_renderer="Adreno (TM) 740",
    )


def android_pixel_6a() -> Fingerprint:
    """Google Pixel 6a / Android 13 / Tensor / Mali-G78."""
    return Fingerprint(
        label="Android 13 / Pixel 6a / Tensor / Mali-G78 / 412x892",
        tags=("android", "mobile", "mid", "google", "arm"),
        user_agent=_ua_android("Pixel 6a", "13"),
        accept_language="en-US,en;q=0.9",
        platform="Android",
        platform_version="13.0.0",
        architecture="arm",
        bitness="64",
        mobile=True,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=8,
        device_memory=8,
        max_touch_points=5,
        screen_width=412,
        screen_height=892,
        avail_width=412,
        avail_height=892,
        color_depth=24,
        device_pixel_ratio=2.625,
        webgl_vendor="ARM",
        webgl_renderer="Mali-G78 MP20",
    )


def android_budget_galaxy_a52() -> Fingerprint:
    """Samsung Galaxy A52 / Android 13 / Snapdragon 720G / Adreno 618."""
    return Fingerprint(
        label="Android 13 / Galaxy A52 / Snapdragon 720G / Adreno 618 / 360x780",
        tags=("android", "mobile", "budget", "low-end", "samsung", "arm"),
        user_agent=_ua_android("SM-A525F", "13"),
        accept_language="en-US,en;q=0.9",
        platform="Android",
        platform_version="13.0.0",
        architecture="arm",
        bitness="64",
        mobile=True,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=8,
        device_memory=4,
        max_touch_points=5,
        screen_width=360,
        screen_height=780,
        avail_width=360,
        avail_height=780,
        color_depth=24,
        device_pixel_ratio=2.625,
        webgl_vendor="Qualcomm",
        webgl_renderer="Adreno (TM) 618",
    )


# ── Linux ────────────────────────────────────────────────────────────────


def linux_intel_uhd() -> Fingerprint:
    return Fingerprint(
        label="Linux / Mesa Intel UHD / 8C / 16GB / 1920x1080",
        tags=("linux", "intel", "mid", "desktop"),
        user_agent=_ua_linux(),
        accept_language="en-US,en;q=0.9",
        platform="Linux",
        platform_version="",
        architecture="x86",
        bitness="64",
        mobile=False,
        brands=_DEFAULT_BRANDS,
        languages=("en-US", "en"),
        hardware_concurrency=8,
        device_memory=8,
        max_touch_points=0,
        screen_width=1920,
        screen_height=1080,
        avail_width=1920,
        avail_height=1053,
        color_depth=24,
        device_pixel_ratio=1.0,
        webgl_vendor="Mesa",
        webgl_renderer="Mesa Intel(R) UHD Graphics (CFL GT2)",
    )


# ── Index ────────────────────────────────────────────────────────────────


ALL: tuple[Fingerprint, ...] = (
    # Desktop — Windows
    windows_11_nvidia_rtx_4090(),
    windows_11_nvidia_rtx_4070(),
    windows_11_nvidia_rtx_3070(),
    windows_11_amd_rx_7900_xtx(),
    windows_11_amd_radeon_6700_xt(),
    windows_10_intel_uhd_630(),
    windows_10_nvidia_gtx_1060(),
    windows_10_laptop_low_end(),
    # Desktop — macOS
    macos_apple_silicon_m3_pro(),
    macos_apple_silicon_m2(),
    macos_intel_iris(),
    # Desktop — Linux
    linux_nvidia_desktop(),
    linux_intel_uhd(),
    # Mobile — Android
    android_pixel_8(),
    android_galaxy_s23(),
    android_pixel_6a(),
    android_budget_galaxy_a52(),
)


def by_label(label: str) -> Fingerprint:
    for fp in ALL:
        if fp.label == label:
            return fp
    raise KeyError(f"No preset with label {label!r}. Available: {[p.label for p in ALL]}")


def filter_by_tag(tag: str) -> tuple[Fingerprint, ...]:
    return tuple(fp for fp in ALL if tag in fp.tags)
