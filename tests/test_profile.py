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


def test_reset_wipes_and_recreates(tmp_path: Path) -> None:
    p = Profile.ensure("alice", root=tmp_path)
    (p / "cookies.db").write_bytes(b"leftover")
    (p / "subdir").mkdir()
    (p / "subdir" / "nested").write_text("more")
    assert (p / "cookies.db").exists()

    fresh = Profile.reset("alice", root=tmp_path)
    assert fresh == p
    assert fresh.is_dir()
    assert list(fresh.iterdir()) == []  # truly empty


def test_reset_works_on_nonexistent_profile(tmp_path: Path) -> None:
    # Should behave like ensure when nothing was there.
    fresh = Profile.reset("ghost", root=tmp_path)
    assert fresh.is_dir()
    assert list(fresh.iterdir()) == []


def test_clear_tabs_drops_session_files_keeps_auth(tmp_path: Path) -> None:
    import json as _json

    p = Profile.ensure("alice", root=tmp_path)
    default = p / "Default"
    default.mkdir()

    # Auth-side files we MUST keep.
    (default / "Cookies").write_bytes(b"cookies-db")
    (default / "Local Storage").mkdir()
    (default / "Local Storage" / "leveldb").mkdir()
    (default / "Local Storage" / "leveldb" / "MANIFEST").write_bytes(b"x")
    (default / "Session Storage").mkdir()
    (default / "Session Storage" / "MANIFEST").write_bytes(b"x")
    (default / "IndexedDB").mkdir()
    (default / "IndexedDB" / "site.db").write_bytes(b"x")

    # Tab-restore-side files we MUST drop.
    (default / "Current Tabs").write_bytes(b"old")
    (default / "Last Tabs").write_bytes(b"old")
    (default / "Current Session").write_bytes(b"old")
    (default / "Last Session").write_bytes(b"old")
    (default / "Sessions").mkdir()
    (default / "Sessions" / "Session_123").write_bytes(b"old")

    # Preferences that say "restore last session" and were not cleanly exited.
    prefs = {
        "profile": {"exit_type": "Crashed", "exited_cleanly": False},
        "session": {"restore_on_startup": 1},
        "other_pref": "kept",
    }
    (default / "Preferences").write_text(_json.dumps(prefs), encoding="utf-8")

    Profile.clear_tabs("alice", root=tmp_path)

    # auth side intact
    assert (default / "Cookies").exists()
    assert (default / "Local Storage" / "leveldb" / "MANIFEST").exists()
    assert (default / "Session Storage" / "MANIFEST").exists()
    assert (default / "IndexedDB" / "site.db").exists()

    # tab side gone
    assert not (default / "Current Tabs").exists()
    assert not (default / "Last Tabs").exists()
    assert not (default / "Current Session").exists()
    assert not (default / "Last Session").exists()
    assert not (default / "Sessions").exists()

    # preferences rewritten
    new_prefs = _json.loads((default / "Preferences").read_text(encoding="utf-8"))
    assert new_prefs["profile"]["exit_type"] == "Normal"
    assert new_prefs["profile"]["exited_cleanly"] is True
    assert new_prefs["session"]["restore_on_startup"] == 5
    assert new_prefs["other_pref"] == "kept"  # unrelated keys preserved


def test_clear_tabs_is_noop_on_missing_profile(tmp_path: Path) -> None:
    # Should not crash if the profile (or its Default/ subdir) doesn't exist.
    Profile.clear_tabs("ghost", root=tmp_path)
    Profile.ensure("ghost-no-default", root=tmp_path)
    Profile.clear_tabs("ghost-no-default", root=tmp_path)


def test_clear_tabs_handles_broken_preferences(tmp_path: Path) -> None:
    p = Profile.ensure("alice", root=tmp_path)
    default = p / "Default"
    default.mkdir()
    (default / "Preferences").write_text("not-json{{{", encoding="utf-8")
    # Should not raise.
    Profile.clear_tabs("alice", root=tmp_path)
