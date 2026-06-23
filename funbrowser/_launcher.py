"""Find and launch Chrome / Chromium with remote debugging enabled."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ._errors import BrowserLaunchError, BrowserNotFoundError

DEVTOOLS_RE = re.compile(rb"DevTools listening on (ws://\S+)")


@dataclass(frozen=True)
class LaunchedBrowser:
    process: asyncio.subprocess.Process
    ws_url: str
    user_data_dir: Path
    user_data_dir_is_tmp: bool


def _candidate_paths() -> list[Path]:
    if sys.platform == "win32":
        roots = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")),
        ]
        rels = [
            r"Google\Chrome\Application\chrome.exe",
            r"Chromium\Application\chrome.exe",
            r"Google\Chrome Beta\Application\chrome.exe",
            r"Google\Chrome Dev\Application\chrome.exe",
            r"BraveSoftware\Brave-Browser\Application\brave.exe",
            r"Microsoft\Edge\Application\msedge.exe",
        ]
        return [Path(r) / rel for r in roots if r for rel in rels]
    if sys.platform == "darwin":
        return [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    return [
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/snap/bin/chromium"),
    ]


def find_chrome() -> Path | None:
    """Return the first Chrome/Chromium-family binary found on this system."""
    env = os.environ.get("FUNBROWSER_CHROME")
    if env:
        p = Path(env)
        if p.is_file():
            return p
    for path in _candidate_paths():
        if path.is_file():
            return path
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _base_args(user_data_dir: Path, headless: bool, port: int) -> list[str]:
    args = [
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ]
    if headless:
        args.append("--headless=new")
    return args


async def launch_chrome(
    *,
    executable: Path | None = None,
    user_data_dir: Path | None = None,
    headless: bool = False,
    extra_args: Sequence[str] = (),
    port: int = 0,
    startup_timeout: float = 30.0,
) -> LaunchedBrowser:
    """Spawn Chrome with remote debugging and return its DevTools websocket URL."""
    exe = executable or find_chrome()
    if exe is None or not exe.is_file():
        raise BrowserNotFoundError(
            "No Chrome/Chromium binary located. Set the FUNBROWSER_CHROME env var "
            "or pass executable= explicitly."
        )

    tmp_profile = False
    if user_data_dir is None:
        user_data_dir = Path(tempfile.mkdtemp(prefix="funbrowser-profile-"))
        tmp_profile = True
    else:
        user_data_dir = Path(user_data_dir)
        user_data_dir.mkdir(parents=True, exist_ok=True)

    args = [str(exe), *_base_args(user_data_dir, headless, port), *extra_args]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    ws_url = await _read_devtools_url(proc, startup_timeout)
    return LaunchedBrowser(
        process=proc,
        ws_url=ws_url,
        user_data_dir=user_data_dir,
        user_data_dir_is_tmp=tmp_profile,
    )


async def _read_devtools_url(proc: asyncio.subprocess.Process, timeout: float) -> str:
    assert proc.stderr is not None
    try:
        async with asyncio.timeout(timeout):
            while True:
                line = await proc.stderr.readline()
                if not line:
                    code = await proc.wait()
                    raise BrowserLaunchError(
                        f"Chrome exited (rc={code}) before printing DevTools URL"
                    )
                m = DEVTOOLS_RE.search(line)
                if m:
                    return m.group(1).decode("ascii")
    except TimeoutError as exc:
        proc.kill()
        raise BrowserLaunchError("Timed out waiting for Chrome to print its DevTools URL") from exc
