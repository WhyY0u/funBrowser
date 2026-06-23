"""Unit + integration tests for fingerprint customization."""

from __future__ import annotations

import pytest

import funbrowser
from funbrowser import Fingerprint, presets
from funbrowser._launcher import find_chrome

# Robust WebGL renderer probe — falls back to gl.RENDERER when the
# WEBGL_debug_renderer_info extension is unavailable (headless Linux CI),
# returns null when WebGL itself is missing.
WEBGL_RENDERER_JS = """
(() => {
  const gl = document.createElement('canvas').getContext('webgl');
  if (!gl) return null;
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  if (ext) return gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
  return gl.getParameter(gl.RENDERER);
})()
"""


def test_all_presets_have_required_fields() -> None:
    for fp in presets.ALL:
        assert fp.user_agent is not None
        assert fp.platform in ("Windows", "macOS", "Linux", "Android")
        assert fp.languages and len(fp.languages) > 0
        assert fp.hardware_concurrency is not None
        assert fp.screen_width is not None
        assert fp.screen_height is not None
        assert fp.webgl_vendor is not None
        assert fp.webgl_renderer is not None
        assert fp.label
        assert fp.tags


def test_by_label_lookup() -> None:
    target = presets.windows_11_nvidia_rtx_4070()
    found = presets.by_label(target.label)
    assert found.label == target.label


def test_by_label_unknown_raises() -> None:
    with pytest.raises(KeyError):
        presets.by_label("not a real preset")


def test_filter_by_tag() -> None:
    windows = presets.filter_by_tag("windows")
    assert len(windows) >= 3
    assert all("windows" in fp.tags for fp in windows)
    macos = presets.filter_by_tag("macos")
    assert all("macos" in fp.tags for fp in macos)


def test_merge_overlays_non_none_fields() -> None:
    base = presets.windows_11_nvidia_rtx_4070()
    overrides = Fingerprint(
        hardware_concurrency=64,
        timezone="Europe/London",
        languages=("de-DE", "de"),
    )
    merged = base.merge(overrides)
    assert merged.hardware_concurrency == 64
    assert merged.timezone == "Europe/London"
    assert merged.languages == ("de-DE", "de")
    # Untouched fields preserved
    assert merged.webgl_renderer == base.webgl_renderer
    assert merged.screen_width == base.screen_width
    assert merged.platform == base.platform


def test_has_webgl_override() -> None:
    assert presets.windows_11_nvidia_rtx_4070().has_webgl_override()
    assert not Fingerprint().has_webgl_override()


# ── End-to-end on real Chrome ────────────────────────────────────────────


pytestmark_integration = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


@pytestmark_integration
async def test_preset_overrides_navigator_properties() -> None:
    fp = presets.windows_11_amd_radeon_6700_xt()
    async with await funbrowser.start(headless=True, fingerprint=fp) as browser:
        tab = await browser.get("https://example.com")
        ua = await tab.evaluate("navigator.userAgent")
        assert "Windows NT 10.0" in ua
        cores = await tab.evaluate("navigator.hardwareConcurrency")
        assert cores == 24
        platform = await tab.evaluate("navigator.platform")
        assert platform == "Win32"
        langs = await tab.evaluate("JSON.stringify(navigator.languages)")
        assert "en-US" in langs


@pytestmark_integration
async def test_preset_overrides_webgl_renderer() -> None:
    fp = presets.windows_11_amd_radeon_6700_xt()
    async with await funbrowser.start(headless=True, fingerprint=fp) as browser:
        tab = await browser.get("https://example.com")
        renderer = await tab.evaluate(WEBGL_RENDERER_JS)
        if renderer is None:
            pytest.skip("WebGL unavailable in this environment")
        assert "AMD" in renderer
        assert "RX 6700" in renderer


@pytestmark_integration
async def test_preset_overrides_screen_dimensions() -> None:
    fp = presets.macos_apple_silicon_m3_pro()
    async with await funbrowser.start(headless=True, fingerprint=fp) as browser:
        tab = await browser.get("https://example.com")
        width = await tab.evaluate("screen.width")
        height = await tab.evaluate("screen.height")
        dpr = await tab.evaluate("window.devicePixelRatio")
        assert width == 1728
        assert height == 1117
        assert dpr == 2.0


@pytestmark_integration
async def test_custom_fingerprint_with_timezone_override() -> None:
    fp = Fingerprint(
        timezone="Asia/Tokyo",
        languages=("ja-JP", "ja", "en"),
    )
    async with await funbrowser.start(headless=True, fingerprint=fp) as browser:
        tab = await browser.get("https://example.com")
        tz = await tab.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
        assert tz == "Asia/Tokyo"
        langs = await tab.evaluate("JSON.stringify(navigator.languages)")
        assert "ja-JP" in langs


@pytestmark_integration
async def test_no_fingerprint_keeps_default_behavior() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get("https://example.com")
        ua = await tab.evaluate("navigator.userAgent")
        # default mode still strips HeadlessChrome
        assert "HeadlessChrome" not in ua
        renderer = await tab.evaluate(WEBGL_RENDERER_JS)
        # On environments with WebGL we expect a real renderer string;
        # CI without GPU may have WebGL disabled entirely, which is fine.
        if renderer is not None:
            assert isinstance(renderer, str)
            assert len(renderer) > 0
