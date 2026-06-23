"""Fingerprint customization — swap the JS-visible identity the browser presents.

Use a preset (``presets.windows_11_nvidia_rtx_4070()``), build a custom
``Fingerprint(...)``, or merge a preset with overrides via ``Fingerprint.merge``.

Pass to ``funbrowser.start(fingerprint=...)`` — see ``examples/custom_fingerprint.py``.
"""

from __future__ import annotations

from . import presets
from .data import Fingerprint

__all__ = ["Fingerprint", "presets"]
