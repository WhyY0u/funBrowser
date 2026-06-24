"""Best-effort Google account login.

This is fragile by nature: Google updates the sign-in flow regularly,
and their risk engine flags automated logins aggressively. To maximise
the chance of a clean login:

- Use a residential / mobile proxy in the account's home country
- Pass a realistic ``fingerprint=`` preset to ``funbrowser.start``
- Run with ``humanly=True`` so typing and mouse movement read as human
- Use a persistent ``user_data_dir=`` profile that has prior browsing
  history — fresh profiles trigger "Verify it's you" much more often
- For 2FA-enabled accounts, pass the TOTP secret via ``totp_secret``

Even with all of the above, expect some accounts to hit a manual
challenge ("verify with your phone", "we noticed a new sign-in"). The
return dict reports the URL where the flow stalled so you can intervene.

Example::

    from funbrowser import start, presets, helpers

    async with start(
        headless=False,
        proxy="user:pass@us-residential:port",
        fingerprint=presets.windows_11_amd_radeon_6700_xt(),
        humanly=True,
    ) as browser:
        result = await helpers.google.login(
            browser,
            email="alice@gmail.com",
            password="...",
            totp_secret="JBSWY3DPEHPK3PXP",  # optional
        )
        if not result["ok"]:
            print("stuck at:", result["url"], "— challenge:", result["challenge"])
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from . import totp as _totp

if TYPE_CHECKING:
    from ..browser import Browser
    from ..tab import Tab

logger = logging.getLogger(__name__)


_SUCCESS_HOSTS = (
    "myaccount.google.com",
    "accounts.google.com/signin/oauth/v2/consentsummary",
)
_PASSWORD_REJECTED_FRAGMENTS = (
    "wrong password",
    "couldn't sign you in",
    "the password is incorrect",
)
_CHALLENGE_PATTERNS = (
    re.compile(r"challenge|verify|gws_signin/challenge", re.IGNORECASE),
    re.compile(r"selectchallenge|signin/v\d+/challenge"),
)


async def login(
    browser_or_tab: Browser | Tab,
    *,
    email: str,
    password: str,
    totp_secret: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Log into a Google account via accounts.google.com.

    Returns ``{"ok": bool, "url": str, "challenge": str | None}``.

    ``ok=True`` means we ended up on a logged-in Google URL. ``ok=False``
    with ``challenge="totp_missing"`` means Google asked for a 2FA code
    but no ``totp_secret`` was provided. ``challenge="recovery"`` means
    Google wants a recovery email or phone — outside this helper.
    """
    # Resolve to a Tab to drive.
    tab = await _resolve_tab(browser_or_tab)

    await tab.goto(
        "https://accounts.google.com/signin/v2/identifier?service=accountsettings",
        timeout=timeout,
    )

    # ── email ─────────────────────────────────────────────────────────
    try:
        await tab.fill('input[type="email"]', email, timeout=timeout)
    except Exception as exc:
        return {"ok": False, "url": tab.url, "challenge": f"email-input: {exc}"}
    await tab.click("#identifierNext")
    await asyncio.sleep(1.5)

    # ── password ──────────────────────────────────────────────────────
    try:
        await tab.find('input[type="password"]', timeout=timeout)
    except TimeoutError:
        return {"ok": False, "url": tab.url, "challenge": "password-page-never-appeared"}
    await asyncio.sleep(0.8)
    await tab.fill('input[type="password"]', password, timeout=timeout)
    await tab.click("#passwordNext")

    # ── wait for success or challenge ─────────────────────────────────
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_challenge: str | None = None

    while loop.time() < deadline:
        await asyncio.sleep(1.2)
        url = tab.url
        if any(h in url for h in _SUCCESS_HOSTS):
            return {"ok": True, "url": url, "challenge": None}

        # Try to detect text-based rejection.
        body_text = (await tab.evaluate("document.body.innerText || ''") or "").lower()
        for needle in _PASSWORD_REJECTED_FRAGMENTS:
            if needle in body_text:
                return {"ok": False, "url": url, "challenge": "wrong-password"}

        if any(p.search(url) for p in _CHALLENGE_PATTERNS):
            # Try the TOTP fast-path first.
            if totp_secret and _totp.available():
                if await _try_totp(tab, totp_secret):
                    last_challenge = "totp-submitted"
                    continue
                last_challenge = "totp-failed"
            else:
                last_challenge = "totp_missing"
            # Other challenges (recovery, "tap on your phone", security key)
            # are beyond what this helper handles cleanly.
            if "recovery" in url.lower() or "recovery" in body_text:
                return {"ok": False, "url": url, "challenge": "recovery"}
            if "tap" in body_text and "phone" in body_text:
                return {"ok": False, "url": url, "challenge": "phone-prompt"}

    return {"ok": False, "url": tab.url, "challenge": last_challenge or "timeout"}


async def _resolve_tab(browser_or_tab: Browser | Tab) -> Tab:
    from ..browser import Browser as _B  # avoid circular import at module load

    if isinstance(browser_or_tab, _B):
        return await browser_or_tab.new_tab()
    return browser_or_tab  # already a Tab


async def _try_totp(tab: Tab, secret: str) -> bool:
    """Type the current TOTP into the visible 2FA input. Returns True on submit."""
    try:
        code = _totp.now(secret)
    except ImportError:
        return False

    # Google's 2FA input has rotated through several selectors over the years.
    candidates = (
        'input[type="tel"]',
        'input[name="totpPin"]',
        "input#totpPin",
        'input[aria-label*="code" i]',
    )
    for sel in candidates:
        try:
            await tab.fill(sel, code, timeout=4.0)
            # "Next" button candidates
            for next_sel in (
                "#totpNext",
                'button[type="button"]:has-text("Next")',
                'div[role="button"]:has-text("Next")',
            ):
                try:
                    await tab.click(next_sel, timeout=2.0)
                    return True
                except Exception:
                    continue
            # Couldn't find Next — send Enter via JS as a fallback.
            await tab.evaluate(
                "document.activeElement && document.activeElement.form && "
                "document.activeElement.form.requestSubmit && "
                "document.activeElement.form.requestSubmit();"
            )
            return True
        except Exception:
            continue
    return False
