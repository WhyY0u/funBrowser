"""Humanly-mode tests: Bezier mouse path, click hold, type delay, jitter."""

from __future__ import annotations

import pytest

import funbrowser
from funbrowser import HumanBehavior
from funbrowser._launcher import find_chrome
from funbrowser.humanly import FAST, _cubic_bezier, _ease_in_out, jitter_target

# ── pure-Python unit tests (no Chrome needed) ─────────────────────────────


def test_ease_in_out_endpoints() -> None:
    assert _ease_in_out(0.0) == pytest.approx(0.0)
    assert _ease_in_out(1.0) == pytest.approx(1.0)
    # Smoothstep is monotonic and ≈ 0.5 in the middle.
    assert _ease_in_out(0.5) == pytest.approx(0.5)


def test_cubic_bezier_endpoints() -> None:
    p0 = (0.0, 0.0)
    p1 = (10.0, 100.0)
    p2 = (90.0, 100.0)
    p3 = (100.0, 0.0)
    assert _cubic_bezier(0.0, p0, p1, p2, p3) == pytest.approx((0.0, 0.0))
    assert _cubic_bezier(1.0, p0, p1, p2, p3) == pytest.approx((100.0, 0.0))


def test_jitter_target_returns_within_radius() -> None:
    behaviour = HumanBehavior(target_jitter_px=5.0)
    samples = [jitter_target(behaviour, 100.0, 100.0) for _ in range(200)]
    for x, y in samples:
        assert 95.0 <= x <= 105.0
        assert 95.0 <= y <= 105.0


def test_jitter_target_off_when_no_behaviour() -> None:
    assert jitter_target(None, 100.0, 100.0) == (100.0, 100.0)


def test_presets_have_sane_ranges() -> None:
    for preset in (HumanBehavior(), FAST):
        assert preset.move_steps_min <= preset.move_steps_max
        assert preset.move_duration_ms_min <= preset.move_duration_ms_max
        assert preset.click_hold_ms_min <= preset.click_hold_ms_max
        assert preset.type_delay_ms_min <= preset.type_delay_ms_max


# ── end-to-end on Chrome ───────────────────────────────────────────────────

pytestmark_chrome = pytest.mark.skipif(
    find_chrome() is None,
    reason="No Chrome/Chromium installed",
)

PAGE = "data:text/html," + (
    "<html><body>"
    "<button id='b' style='position:absolute;left:300px;top:200px;width:100px;height:40px;'>"
    "click</button>"
    "<input id='inp' type='text' style='position:absolute;left:50px;top:50px;'>"
    "<script>"
    "window.__moves = 0;"
    "window.__press = null;"
    "window.__release = null;"
    "document.addEventListener('mousemove', () => window.__moves++);"
    "document.getElementById('b').addEventListener('mousedown',"
    "  () => window.__press = performance.now());"
    "document.getElementById('b').addEventListener('mouseup',"
    "  () => window.__release = performance.now());"
    "window.__lastKeys = [];"
    "document.getElementById('inp').addEventListener('input',"
    "  (e) => window.__lastKeys.push(performance.now()));"
    "</script>"
    "</body></html>"
)


@pytestmark_chrome
async def test_humanly_click_dispatches_multiple_mouse_moves() -> None:
    """Humanly path: dozens of mouseMoved events vs the single one without."""
    fast = FAST
    async with await funbrowser.start(headless=True, humanly=fast) as browser:
        tab = await browser.get(PAGE)
        # seed cursor at origin so the move from (0,0) to button definitely traces a path
        tab._cursor = (10.0, 10.0)
        await tab.click("#b")
        moves = await tab.evaluate("window.__moves")
        assert moves >= fast.move_steps_min, f"expected ≥{fast.move_steps_min} moves, got {moves}"


@pytestmark_chrome
async def test_non_humanly_click_is_one_move_one_press_one_release() -> None:
    async with await funbrowser.start(headless=True) as browser:
        tab = await browser.get(PAGE)
        await tab.click("#b")
        moves = await tab.evaluate("window.__moves")
        # Without humanly, a single mouseMoved is emitted before the click.
        assert moves == 1


@pytestmark_chrome
async def test_click_hold_takes_random_time_in_humanly_mode() -> None:
    async with await funbrowser.start(headless=True, humanly=FAST) as browser:
        tab = await browser.get(PAGE)
        await tab.click("#b")
        press = await tab.evaluate("window.__press")
        release = await tab.evaluate("window.__release")
        held = release - press
        assert held >= FAST.click_hold_ms_min - 5  # tiny grace for clock noise


@pytestmark_chrome
async def test_type_dispatches_chars_with_gaps_in_humanly_mode() -> None:
    async with await funbrowser.start(headless=True, humanly=FAST) as browser:
        tab = await browser.get(PAGE)
        await tab.type("#inp", "hello")
        ts = await tab.evaluate("JSON.stringify(window.__lastKeys)")
        import json

        keys = json.loads(ts)
        assert len(keys) == 5
        gaps = [keys[i] - keys[i - 1] for i in range(1, len(keys))]
        # Average gap should be ≥ min/2 (allow noise) when FAST profile is in
        # use; a non-humanly fall-through would give gaps near zero.
        assert max(gaps) >= FAST.type_delay_ms_min / 2


@pytestmark_chrome
async def test_start_humanly_true_uses_default_profile() -> None:
    async with await funbrowser.start(headless=True, humanly=True) as browser:
        assert browser.humanly is not None
        assert isinstance(browser.humanly, HumanBehavior)


@pytestmark_chrome
async def test_start_humanly_false_disables() -> None:
    async with await funbrowser.start(headless=True, humanly=False) as browser:
        assert browser.humanly is None


@pytestmark_chrome
async def test_cursor_tracked_across_clicks() -> None:
    async with await funbrowser.start(headless=True, humanly=FAST) as browser:
        tab = await browser.get(PAGE)
        tab._cursor = (0.0, 0.0)
        await tab.click("#b")
        first = tab._cursor
        assert first is not None
        # Cursor should land near the button centre (~350, 220) within jitter.
        assert 340.0 <= first[0] <= 360.0
        assert 210.0 <= first[1] <= 230.0
        # Another click from a different start point traces another path.
        await tab.click("#inp")
        assert tab._cursor != first
