"""Tests for the Chrome locator."""

from __future__ import annotations

from pathlib import Path

from funbrowser._launcher import _candidate_paths, find_chrome


def test_candidate_paths_nonempty() -> None:
    paths = _candidate_paths()
    assert len(paths) > 0
    assert all(isinstance(p, Path) for p in paths)


def test_find_chrome_returns_existing_file_or_none() -> None:
    result = find_chrome()
    assert result is None or result.is_file()
