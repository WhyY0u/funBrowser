"""The Fingerprint dataclass — every field optional; ``None`` means "don't override"."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, fields
from typing import Any


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """A snapshot of overridable browser-identity values.

    Every field is optional. ``None`` means "leave whatever Chrome reports
    natively". Use :func:`merge` to layer overrides on top of a preset.
    """

    # ── User-Agent + Client Hints ────────────────────────────────────────
    user_agent: str | None = None
    accept_language: str | None = None
    platform: str | None = None  # "Windows" / "macOS" / "Linux" / "Android"
    platform_version: str | None = None  # "15.0.0" etc. for Sec-CH-UA-Platform-Version
    architecture: str | None = None  # "x86" / "arm"
    bitness: str | None = None  # "64" / "32"
    mobile: bool | None = None
    brands: tuple[tuple[str, str], ...] | None = None  # ((brand, version), ...)

    # ── navigator.* ──────────────────────────────────────────────────────
    languages: tuple[str, ...] | None = None
    hardware_concurrency: int | None = None  # logical CPU cores
    device_memory: float | None = None  # GB, Chrome reports {0.25,0.5,1,2,4,8}
    max_touch_points: int | None = None

    # ── screen / window ──────────────────────────────────────────────────
    screen_width: int | None = None
    screen_height: int | None = None
    avail_width: int | None = None
    avail_height: int | None = None
    color_depth: int | None = None
    device_pixel_ratio: float | None = None

    # ── locale / time ────────────────────────────────────────────────────
    timezone: str | None = None  # IANA, e.g. "America/New_York"
    locale: str | None = None  # e.g. "en-US"

    # ── WebGL ───────────────────────────────────────────────────────────
    # Important: spoofing these without also faking the rendered pixel
    # output (M9) can flag you with top-tier antibots. Default (None) keeps
    # the real GPU value, which is usually what you want.
    webgl_vendor: str | None = None
    webgl_renderer: str | None = None

    # ── meta ────────────────────────────────────────────────────────────
    # Free-form label for debugging / logging. Never sent to the browser.
    label: str = ""

    # Tags useful for filtering presets programmatically.
    tags: tuple[str, ...] = field(default_factory=tuple)

    def merge(self, other: Fingerprint) -> Fingerprint:
        """Return a new Fingerprint with ``other``'s non-None fields layered on."""
        overrides: dict[str, Any] = {}
        for f in fields(other):
            value = getattr(other, f.name)
            if f.name in ("label", "tags"):
                if value:
                    overrides[f.name] = value
                continue
            if value is not None:
                overrides[f.name] = value
        return dataclasses.replace(self, **overrides)

    def has_webgl_override(self) -> bool:
        return self.webgl_vendor is not None or self.webgl_renderer is not None
