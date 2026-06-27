"""Profile cache template — pre-warm a snapshot, apply to fresh profiles.

Chrome keeps fetched HTTP responses and pre-compiled V8 bytecode under
``<user_data_dir>/Default/Cache/`` and ``<user_data_dir>/Default/Code
Cache/``. After visiting a site once, a fresh browser pointed at a copy
of those directories starts with the heavy static assets already on
disk — no network for cached CSS/JS/fonts/images, no V8 recompilation
for hot scripts.

Typical farm workflow::

    # 1. Warm a reference profile once.
    async with funbrowser.start(headless=True) as warmer:
        await warmer.get("https://target.com")
        await warmer.get("https://target.com/login")
        # ... touch whatever else you want pre-cached ...
    funbrowser.cache.save_template(
        warmer.user_data_dir, "templates/target-v1"
    )

    # 2. Spin every worker with the template pre-applied.
    async with funbrowser.start(cache_template="templates/target-v1") as br:
        # Cold-start asset fetches are served from disk instead of network.
        ...

The template is a directory snapshot — no patching, no live sharing
between concurrent browsers. Periodically re-warm to pick up new
asset hashes from your targets (sites that ship hashed bundle names
flush the cache when they redeploy).
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Subdirs under ``user_data_dir`` that contain cacheable artefacts worth
# carrying across profiles. Both are large wins:
#
# - ``Default/Cache``       — disk-cache v3 (HTTP responses by URL hash)
# - ``Default/Code Cache``  — V8 bytecode cache for JS / WASM
#
# ``GPUCache`` is intentionally excluded — it's shader binaries that are
# tied to the specific GPU + driver and bloat the template without much
# pay-off on a fresh profile.
CACHE_SUBPATHS: tuple[str, ...] = (
    "Default/Cache",
    "Default/Code Cache",
)


def save_template(
    user_data_dir: str | Path,
    template_dir: str | Path,
    *,
    overwrite: bool = True,
) -> int:
    """Snapshot a warmed profile's cache directories into a template.

    Pass the profile path of a browser you already drove through your
    target pages. Returns the number of cache subdirs actually copied.
    ``overwrite=True`` (default) wipes any existing template at
    ``template_dir``; pass ``overwrite=False`` to raise if it exists.
    """
    src_root = Path(user_data_dir)
    if not src_root.is_dir():
        raise FileNotFoundError(f"user_data_dir not found: {src_root}")
    dst_root = Path(template_dir)
    if dst_root.exists():
        if not overwrite:
            raise FileExistsError(f"{dst_root} already exists (pass overwrite=True to replace)")
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True, exist_ok=True)
    copied = 0
    for sub in CACHE_SUBPATHS:
        src = src_root / sub
        if not src.is_dir():
            continue
        dst = dst_root / sub
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        copied += 1
    return copied


def apply_template(
    template_dir: str | Path,
    user_data_dir: str | Path,
) -> int:
    """Copy a cache template into a fresh profile's directories.

    Returns the number of cache subdirs actually applied. Safe to call
    on a not-yet-existing ``user_data_dir`` — parent dirs are created
    as needed. Must be called **before** Chrome starts on that profile;
    Chrome locks the cache files exclusively at launch.
    """
    src_root = Path(template_dir)
    if not src_root.is_dir():
        raise FileNotFoundError(f"cache template not found: {src_root}")
    dst_root = Path(user_data_dir)
    dst_root.mkdir(parents=True, exist_ok=True)
    applied = 0
    for sub in CACHE_SUBPATHS:
        src = src_root / sub
        if not src.is_dir():
            continue
        dst = dst_root / sub
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        applied += 1
    return applied


def template_size_bytes(template_dir: str | Path) -> int:
    """Total disk footprint of a template — useful for picking a sane
    eviction threshold or just sanity-checking what you captured."""
    root = Path(template_dir)
    if not root.is_dir():
        return 0
    total = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total
