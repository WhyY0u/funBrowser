"""Persistent browser profiles.

A profile is a directory Chrome uses for cookies, localStorage, IndexedDB,
extensions, history, and login state. Two sessions sharing the same
profile directory share that state; two sessions with different directories
are isolated.

Lifecycle:
- ``Profile.ensure("alice")`` returns the path under ``./funbrowser_profiles/alice``,
  creating it if missing.
- Pass the path to ``funbrowser.start(user_data_dir=...)``.
- ``Profile.delete("alice")`` wipes the directory (use to log out / reset).
- ``Profile.list()`` enumerates profiles under the default root.

Only one Chrome instance per profile directory can run at a time — Chrome
holds a lock on the dir. Spawn a second instance against the same profile
and Chrome will exit early.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _default_root() -> Path:
    env = os.environ.get("FUNBROWSER_PROFILES")
    if env:
        return Path(env)
    return Path.cwd() / "funbrowser_profiles"


class Profile:
    @staticmethod
    def root() -> Path:
        return _default_root()

    @staticmethod
    def path(name: str, *, root: Path | None = None) -> Path:
        if not _SAFE_NAME.match(name):
            raise ValueError(f"profile name {name!r} must match {_SAFE_NAME.pattern!r}")
        return (root or _default_root()) / name

    @staticmethod
    def ensure(name: str, *, root: Path | None = None) -> Path:
        """Return the profile path, creating the directory if needed."""
        p = Profile.path(name, root=root)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @staticmethod
    def exists(name: str, *, root: Path | None = None) -> bool:
        return Profile.path(name, root=root).is_dir()

    @staticmethod
    def delete(name: str, *, root: Path | None = None) -> bool:
        """Remove the profile directory. Returns True if it existed."""
        p = Profile.path(name, root=root)
        if not p.exists():
            return False
        shutil.rmtree(p, ignore_errors=True)
        return True

    @staticmethod
    def clear_tabs(name: str, *, root: Path | None = None) -> Path:
        """Remove tab/session restore state without touching auth.

        Chrome stores **two separate things** under a profile:

        - Auth state: ``Cookies``, ``Local Storage/``, ``Session Storage/``,
          ``IndexedDB/`` — these are what keeps you logged in.
        - Tab/session restore: ``Current Tabs``, ``Last Tabs``,
          ``Current Session``, ``Last Session``, ``Sessions/`` — these
          are what makes Chrome reopen the 47 tabs you had last time.

        :func:`Profile.reset` nukes everything. This method nukes only
        the second category, so when you relaunch you get a single
        new-tab page but you're still logged in everywhere. Also
        rewrites ``Default/Preferences`` so Chrome won't show the
        "Restore tabs?" prompt from a not-cleanly-closed session and
        won't restore-on-startup.

        Chrome must not be running against this directory when you call
        this — kill the browser first.
        """
        p = Profile.path(name, root=root)
        if not p.exists():
            return p
        default = p / "Default"
        if not default.is_dir():
            return p

        # Session-restore files / dirs Chrome rebuilds on next launch.
        for rel in (
            "Current Tabs",
            "Last Tabs",
            "Current Session",
            "Last Session",
            "Sessions",
        ):
            target = default / rel
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass

        # Patch Preferences so Chrome (a) doesn't show "Restore?" bubble
        # from a SIGKILL'd previous session and (b) opens NTP on launch
        # instead of restoring tabs.
        prefs_file = default / "Preferences"
        if prefs_file.is_file():
            try:
                prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prefs = None
            if isinstance(prefs, dict):
                profile_prefs = prefs.setdefault("profile", {})
                if isinstance(profile_prefs, dict):
                    profile_prefs["exit_type"] = "Normal"
                    profile_prefs["exited_cleanly"] = True
                session_prefs = prefs.setdefault("session", {})
                if isinstance(session_prefs, dict):
                    session_prefs["restore_on_startup"] = 5  # NTP
                try:
                    prefs_file.write_text(json.dumps(prefs), encoding="utf-8")
                except OSError:
                    pass
        return p

    @staticmethod
    def reset(name: str, *, root: Path | None = None) -> Path:
        """Wipe and recreate the profile, returning the fresh path.

        Equivalent to ``delete`` then ``ensure`` — use when you want a
        clean session under the same name (no leftover cookies, no
        remembered Google account on the chooser, no service workers).
        Chrome must not be running against this directory when you call
        this — kill the browser first.

        ::

            async with funbrowser.start(
                user_data_dir=Profile.reset("alice"),
            ) as browser:
                ...  # logs in from a clean slate
        """
        Profile.delete(name, root=root)
        return Profile.ensure(name, root=root)

    @staticmethod
    def list(*, root: Path | None = None) -> list[str]:
        r = root or _default_root()
        if not r.is_dir():
            return []
        return sorted(p.name for p in r.iterdir() if p.is_dir())
