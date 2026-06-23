"""Tests for the Profile helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from funbrowser import Profile


def test_path_rejects_unsafe_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Profile.path("../escape", root=tmp_path)
    with pytest.raises(ValueError):
        Profile.path("with spaces", root=tmp_path)
    with pytest.raises(ValueError):
        Profile.path("trailing/slash", root=tmp_path)


def test_path_accepts_safe_names(tmp_path: Path) -> None:
    assert Profile.path("alice", root=tmp_path) == tmp_path / "alice"
    assert Profile.path("user_01", root=tmp_path).name == "user_01"
    assert Profile.path("worker.42", root=tmp_path).name == "worker.42"
    assert Profile.path("kebab-case", root=tmp_path).name == "kebab-case"


def test_ensure_creates_directory(tmp_path: Path) -> None:
    p = Profile.ensure("alice", root=tmp_path)
    assert p.is_dir()
    # Idempotent
    p2 = Profile.ensure("alice", root=tmp_path)
    assert p2 == p


def test_exists(tmp_path: Path) -> None:
    assert not Profile.exists("ghost", root=tmp_path)
    Profile.ensure("ghost", root=tmp_path)
    assert Profile.exists("ghost", root=tmp_path)


def test_delete(tmp_path: Path) -> None:
    Profile.ensure("alice", root=tmp_path)
    assert Profile.delete("alice", root=tmp_path) is True
    assert not Profile.exists("alice", root=tmp_path)
    # Delete-missing is a noop, returns False.
    assert Profile.delete("alice", root=tmp_path) is False


def test_list(tmp_path: Path) -> None:
    assert Profile.list(root=tmp_path) == []
    Profile.ensure("alice", root=tmp_path)
    Profile.ensure("bob", root=tmp_path)
    Profile.ensure("carol", root=tmp_path)
    assert Profile.list(root=tmp_path) == ["alice", "bob", "carol"]


def test_root_default_uses_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FUNBROWSER_PROFILES", str(tmp_path / "via_env"))
    assert Profile.root() == tmp_path / "via_env"
