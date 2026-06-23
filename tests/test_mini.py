"""Mini mode + flag merger tests."""

from __future__ import annotations

import pytest

import funbrowser
from funbrowser._flags import merge_flags, mini_flags
from funbrowser._launcher import find_chrome
from funbrowser.stealth import stealth_flags


def test_mini_flags_disable_extensions_and_audio() -> None:
    flags = mini_flags()
    assert "--mute-audio" in flags
    assert "--disable-extensions" in flags
    assert "--disable-renderer-backgrounding" in flags
    assert any("--js-flags=" in f for f in flags)


def test_merge_flags_unions_disable_features() -> None:
    a = ["--disable-features=Foo,Bar", "--other"]
    b = ["--disable-features=Bar,Baz"]
    merged = merge_flags(a, b)
    # Exactly one --disable-features in the output
    df = [f for f in merged if f.startswith("--disable-features=")]
    assert len(df) == 1
    values = df[0].removeprefix("--disable-features=").split(",")
    assert set(values) == {"Foo", "Bar", "Baz"}
    assert "--other" in merged


def test_merge_flags_unions_enable_features() -> None:
    merged = merge_flags(
        ["--enable-features=A,B", "--keep"],
        ["--enable-features=B,C"],
    )
    ef = [f for f in merged if f.startswith("--enable-features=")]
    assert len(ef) == 1
    values = ef[0].removeprefix("--enable-features=").split(",")
    assert set(values) == {"A", "B", "C"}


def test_merge_flags_deduplicates_plain_flags() -> None:
    merged = merge_flags(["--mute-audio", "--keep"], ["--mute-audio", "--other"])
    assert merged.count("--mute-audio") == 1
    assert "--keep" in merged
    assert "--other" in merged


def test_mini_and_stealth_coexist_with_single_disable_features() -> None:
    merged = merge_flags(stealth_flags(), mini_flags())
    df = [f for f in merged if f.startswith("--disable-features=")]
    assert len(df) == 1, "stealth + mini must produce a single --disable-features"
    values = set(df[0].removeprefix("--disable-features=").split(","))
    # both inputs' feature toggles survived
    assert "AutomationControlled" in values  # from stealth
    assert "IsolateOrigins" in values  # from mini
    # stealth's GPU flag must still be present — mini does not strip it
    assert "--use-gl=angle" in merged


# ── integration on Chrome ────────────────────────────────────────────────


pytestmark_chrome = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)


@pytestmark_chrome
async def test_mini_browser_launches_and_navigates() -> None:
    async with await funbrowser.start(headless=True, mini=True) as browser:
        tab = await browser.get("https://example.com")
        title = await tab.evaluate("document.title")
        assert title == "Example Domain"


@pytestmark_chrome
async def test_mini_keeps_stealth_basics_intact() -> None:
    async with await funbrowser.start(headless=True, mini=True) as browser:
        tab = await browser.get("https://example.com")
        ua = await tab.evaluate("navigator.userAgent")
        assert "HeadlessChrome" not in ua, "stealth still applies under mini"
        wd = await tab.evaluate("navigator.webdriver")
        assert wd is None
