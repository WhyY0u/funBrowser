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
    def list(*, root: Path | None = None) -> list[str]:
        r = root or _default_root()
        if not r.is_dir():
            return []
        return sorted(p.name for p in r.iterdir() if p.is_dir())
