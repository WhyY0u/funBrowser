"""Stealth — runtime patches that hide CDP/headless tells from antibot scripts.

Scope (M2): Tier 1 (basic markers) + Tier 2 (real GPU + canvas/audio noise).
Tier 3 (full consistency), Tier 4 (real fingerprint pool), and deep
WebGL/shader spoofing are post-v0.1 milestones — see README roadmap.
"""

from __future__ import annotations

from .flags import stealth_flags
from .patches import apply_stealth

__all__ = ["apply_stealth", "stealth_flags"]
