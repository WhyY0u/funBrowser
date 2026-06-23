"""Human-like input timing & motion.

When ``humanly=True`` (or a custom :class:`HumanBehavior` is passed),
mouse moves trace a randomised cubic-Bezier curve with ease-in-out timing
instead of teleporting, click ``mousePressed`` / ``mouseReleased`` pairs
hold for a random duration, typing dispatches each character with a random
delay, and targets are hit with a few pixels of jitter from the centre.

These are the timing and trajectory signals modern antibots score on top
of the JS-level fingerprint patches in :mod:`funbrowser.stealth`. The
defaults are tuned to read like a moderately-paced human user;
:data:`FAST` and :data:`CAREFUL` cover the obvious ends.
"""

from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tab import Tab


@dataclass(frozen=True, slots=True)
class HumanBehavior:
    # ── mouse motion ────────────────────────────────────────────────────
    move_steps_min: int = 18
    move_steps_max: int = 40
    move_duration_ms_min: float = 220.0
    move_duration_ms_max: float = 650.0
    curve_strength_px: float = 60.0
    jitter_px: float = 1.5

    # ── click ──────────────────────────────────────────────────────────
    pre_click_delay_ms_min: float = 60.0
    pre_click_delay_ms_max: float = 260.0
    click_hold_ms_min: float = 45.0
    click_hold_ms_max: float = 130.0
    target_jitter_px: float = 3.0

    # ── typing ─────────────────────────────────────────────────────────
    type_delay_ms_min: float = 65.0
    type_delay_ms_max: float = 195.0


DEFAULT = HumanBehavior()

FAST = HumanBehavior(
    move_steps_min=8,
    move_steps_max=16,
    move_duration_ms_min=80.0,
    move_duration_ms_max=220.0,
    curve_strength_px=30.0,
    pre_click_delay_ms_min=15.0,
    pre_click_delay_ms_max=80.0,
    click_hold_ms_min=20.0,
    click_hold_ms_max=60.0,
    type_delay_ms_min=25.0,
    type_delay_ms_max=85.0,
)

CAREFUL = HumanBehavior(
    move_steps_min=30,
    move_steps_max=70,
    move_duration_ms_min=450.0,
    move_duration_ms_max=1300.0,
    curve_strength_px=90.0,
    pre_click_delay_ms_min=220.0,
    pre_click_delay_ms_max=900.0,
    click_hold_ms_min=85.0,
    click_hold_ms_max=210.0,
    type_delay_ms_min=140.0,
    type_delay_ms_max=420.0,
)


def _ease_in_out(t: float) -> float:
    """Smoothstep — slow at endpoints, fast in the middle."""
    return 3 * t * t - 2 * t * t * t


def _cubic_bezier(
    t: float,
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> tuple[float, float]:
    u = 1.0 - t
    x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
    return x, y


async def move(tab: Tab, target_x: float, target_y: float) -> None:
    """Move the virtual cursor to ``(target_x, target_y)`` along a curve.

    Falls back to a single ``mouseMoved`` event when no humanly profile is
    active on the tab.
    """
    behaviour: HumanBehavior | None = tab._humanly
    if behaviour is None:
        await tab._send(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": target_x, "y": target_y},
        )
        tab._cursor = (target_x, target_y)
        return

    start = tab._cursor or (target_x, target_y)
    if start == (target_x, target_y):
        # Nothing to do for the first interaction with no recorded cursor.
        await tab._send(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": target_x, "y": target_y},
        )
        tab._cursor = (target_x, target_y)
        return

    dx = target_x - start[0]
    dy = target_y - start[1]
    curve = behaviour.curve_strength_px

    cp1 = (
        start[0] + dx * 0.3 + random.uniform(-curve, curve),
        start[1] + dy * 0.3 + random.uniform(-curve, curve),
    )
    cp2 = (
        start[0] + dx * 0.7 + random.uniform(-curve, curve),
        start[1] + dy * 0.7 + random.uniform(-curve, curve),
    )

    n_steps = random.randint(behaviour.move_steps_min, behaviour.move_steps_max)
    duration_s = (
        random.uniform(behaviour.move_duration_ms_min, behaviour.move_duration_ms_max) / 1000.0
    )
    per_step = duration_s / max(n_steps, 1)
    jitter = behaviour.jitter_px

    for i in range(1, n_steps + 1):
        eased = _ease_in_out(i / n_steps)
        x, y = _cubic_bezier(eased, start, cp1, cp2, (target_x, target_y))
        x += random.uniform(-jitter, jitter)
        y += random.uniform(-jitter, jitter)
        await tab._send(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": x, "y": y},
        )
        await asyncio.sleep(per_step)

    tab._cursor = (target_x, target_y)


def jitter_target(behaviour: HumanBehavior | None, x: float, y: float) -> tuple[float, float]:
    if behaviour is None:
        return x, y
    r = behaviour.target_jitter_px
    if r <= 0:
        return x, y
    return x + random.uniform(-r, r), y + random.uniform(-r, r)


async def pre_action_delay(behaviour: HumanBehavior | None) -> None:
    if behaviour is None:
        return
    delay = random.uniform(behaviour.pre_click_delay_ms_min, behaviour.pre_click_delay_ms_max)
    await asyncio.sleep(delay / 1000.0)


async def click_hold(behaviour: HumanBehavior | None) -> None:
    if behaviour is None:
        return
    delay = random.uniform(behaviour.click_hold_ms_min, behaviour.click_hold_ms_max)
    await asyncio.sleep(delay / 1000.0)


def type_delay(behaviour: HumanBehavior | None) -> float:
    if behaviour is None:
        return 0.0
    return random.uniform(behaviour.type_delay_ms_min, behaviour.type_delay_ms_max) / 1000.0


# Kept around in case future code wants to compute distance-aware step counts.
def _euclid(p: tuple[float, float], q: tuple[float, float]) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])
