"""Smoke test — verifies package imports and exposes __version__."""

import funbrowser


def test_package_imports() -> None:
    assert funbrowser.__version__
    assert isinstance(funbrowser.__version__, str)
