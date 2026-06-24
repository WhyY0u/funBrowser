"""TOTP wrapper tests (uses pyotp from the dev group)."""

from __future__ import annotations

import pyotp

from funbrowser.helpers import totp


def test_available_when_pyotp_installed() -> None:
    assert totp.available() is True


def test_now_returns_six_digit_string() -> None:
    secret = "JBSWY3DPEHPK3PXP"
    code = totp.now(secret)
    assert len(code) == 6
    assert code.isdigit()


def test_now_matches_pyotp() -> None:
    secret = "JBSWY3DPEHPK3PXP"
    code_funbrowser = totp.now(secret)
    code_direct = pyotp.TOTP(secret).now()
    # Generated in the same TOTP window — must be equal
    assert code_funbrowser == code_direct


def test_now_strips_whitespace_and_case() -> None:
    secret_clean = "JBSWY3DPEHPK3PXP"
    secret_dirty = " jbswy3dpehp k3pxp "
    assert totp.now(secret_dirty) == totp.now(secret_clean)
