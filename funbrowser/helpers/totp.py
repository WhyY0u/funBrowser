"""TOTP code generation (RFC 6238).

Wraps :mod:`pyotp`. Install with ``pip install funbrowser[automation]``.
"""

from __future__ import annotations

try:
    import pyotp as _pyotp
except ImportError:  # pragma: no cover
    _pyotp = None  # type: ignore[assignment]


def available() -> bool:
    """True if ``pip install funbrowser[automation]`` was run."""
    return _pyotp is not None


def now(secret: str) -> str:
    """Current 6-digit TOTP code for ``secret`` (base32-encoded).

    ``secret`` is the same string the authenticator app accepts when
    you scan a QR code or paste the manual key. Whitespace and case
    are ignored.
    """
    if _pyotp is None:
        raise ImportError("TOTP requires `pip install funbrowser[automation]` (adds pyotp).")
    code: str = _pyotp.TOTP(secret.replace(" ", "").upper()).now()
    return code
