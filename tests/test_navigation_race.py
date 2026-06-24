"""Unit tests for the navigation-race detector in tab.py / element.py.

CDP returns a synthetic ``exceptionDetails`` when the execution context
is destroyed mid-evaluate (page started navigating). We must NOT treat
that as a real JS error — it just means "the JS never ran, try again
after navigation settles."
"""

from __future__ import annotations

from funbrowser.element import _is_navigation_race as _is_race_element
from funbrowser.tab import _is_navigation_race as _is_race_tab


def test_synthetic_uncaught_with_no_exception_object_is_race() -> None:
    details = {"text": "Uncaught", "exception": {}}
    assert _is_race_tab(details) is True
    assert _is_race_element(details) is True


def test_empty_text_with_no_exception_object_is_race() -> None:
    details = {"text": "", "exception": {}}
    assert _is_race_tab(details) is True
    assert _is_race_element(details) is True


def test_uncaught_with_no_exception_key_at_all_is_race() -> None:
    details = {"text": "Uncaught"}
    assert _is_race_tab(details) is True


def test_real_reference_error_is_not_a_race() -> None:
    details = {
        "text": "Uncaught ReferenceError: foo is not defined",
        "exception": {
            "type": "object",
            "subtype": "error",
            "className": "ReferenceError",
            "description": "ReferenceError: foo is not defined\n    at <anonymous>:1:1",
            "objectId": '{"injectedScriptId":2,"id":1}',
        },
    }
    assert _is_race_tab(details) is False
    assert _is_race_element(details) is False


def test_thrown_string_is_not_a_race() -> None:
    """`throw "boom"` — no class, no objectId, but a string value."""
    details = {
        "text": "Uncaught",
        "exception": {"type": "string", "value": "boom"},
    }
    assert _is_race_tab(details) is False


def test_thrown_zero_is_not_a_race() -> None:
    """Edge case: `throw 0` — value is 0 (falsy) but not None."""
    details = {
        "text": "Uncaught",
        "exception": {"type": "number", "value": 0},
    }
    assert _is_race_tab(details) is False


def test_description_only_is_not_a_race() -> None:
    """Some CDP versions only carry description."""
    details = {
        "text": "Uncaught",
        "exception": {"description": "TypeError: x is null"},
    }
    assert _is_race_tab(details) is False


def test_class_name_only_is_not_a_race() -> None:
    details = {
        "text": "Uncaught",
        "exception": {"className": "TypeError"},
    }
    assert _is_race_tab(details) is False


def test_arbitrary_text_with_empty_exception_is_not_race() -> None:
    """If text isn't "Uncaught" or empty, we trust it as a real error."""
    details = {"text": "Compilation error", "exception": {}}
    assert _is_race_tab(details) is False
