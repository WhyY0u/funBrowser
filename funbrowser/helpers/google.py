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
import json
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

    # ── account chooser (optional first page) ────────────────────────
    # If the browser profile has any previously-used Google account,
    # Google shows a "Choose an account" screen with that account + a
    # "Use another account" entry instead of the identifier input. We
    # detect by URL fragment + DOM marker and click through. JS click
    # is used: CDP-synthesised mouse events don't fire on Google's
    # chooser tile handlers.
    await asyncio.sleep(0.5)
    if "accountchooser" in tab.url.lower() or await tab.exists('[jsname="rwl3qc"]'):
        clicked = False
        for sel in (
            '[jsname="rwl3qc"]',
            '[data-button-type="addAccount"]',
            'div[role="link"][data-authuser="-1"]',
        ):
            if await _js_click(tab, sel):
                clicked = True
                break
        if not clicked:
            return {
                "ok": False,
                "url": tab.url,
                "challenge": "account-chooser-stuck",
            }
        await asyncio.sleep(1.5)

    # ── email ─────────────────────────────────────────────────────────
    # Google's email input is `<input type="text" id="identifierId"
    # name="identifier">` — NOT type=email. Selectors are listed by
    # likelihood: id first, then name, then aria-label.
    email_filled = False
    for sel in ("#identifierId", 'input[name="identifier"]', 'input[aria-label*="Email" i]'):
        try:
            await tab.fill(sel, email, timeout=8.0)
            email_filled = True
            break
        except Exception:
            continue
    if not email_filled:
        return {"ok": False, "url": tab.url, "challenge": "email-input-not-found"}
    await tab.click("#identifierNext")
    await asyncio.sleep(1.5)

    # ── password ──────────────────────────────────────────────────────
    # Password input is the standard `<input type="password" name="Passwd">`
    # inside a wrapping div, but type selector works fine across A/B variants.
    pwd_sel_candidates = (
        'input[type="password"]',
        'input[name="Passwd"]',
        'input[aria-label*="password" i]',
    )
    pwd_sel = None
    for sel in pwd_sel_candidates:
        try:
            await tab.find(sel, timeout=timeout / 4)
            pwd_sel = sel
            break
        except TimeoutError:
            continue
    if pwd_sel is None:
        return {"ok": False, "url": tab.url, "challenge": "password-page-never-appeared"}
    await asyncio.sleep(0.8)
    await tab.fill(pwd_sel, password, timeout=timeout)
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
        body_text = (await tab.evaluate("document.body.innerText", default="") or "").lower()
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

    # Active verification: if we ran out of time but didn't see a clear
    # success/failure signal, navigate to myaccount.google.com directly.
    # When logged in: lands on myaccount.google.com (no redirect).
    # When not logged in: Google bounces us to
    # accounts.google.com/ServiceLogin?... or /signin/... .
    verified = await _verify_logged_in(tab)
    if verified:
        return {"ok": True, "url": tab.url, "challenge": None}
    return {"ok": False, "url": tab.url, "challenge": last_challenge or "timeout"}


async def continue_signin(
    browser_or_tab: Browser | Tab,
    *,
    email: str,
    password: str,
    totp_secret: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Complete an in-progress "Sign in with Google" OAuth flow.

    Use this when a **third-party site** (Autodesk, Notion, Figma, any
    OAuth client) has already redirected the tab to ``accounts.google.com``
    after the user clicked "Sign in with Google". The helper drives
    whatever Google screen is currently visible — account chooser,
    email input, password input, 2FA — and returns when Google
    redirects back to the client app.

    Same return shape as :func:`login`:
    ``{"ok": bool, "url": str, "challenge": str | None}``. ``ok=True``
    means we left ``accounts.google.com`` (= the OAuth flow completed
    and the client got its callback). Doesn't navigate anywhere itself.

    ::

        tab = await browser.get("https://example.com")
        await tab.click("button.sign-in-with-google")
        # tab is now on accounts.google.com OAuth flow
        result = await helpers.google.continue_signin(
            tab, email="alice@gmail.com", password="...",
        )
    """
    tab = await _resolve_tab(browser_or_tab)
    await asyncio.sleep(0.8)

    if "accounts.google.com" not in tab.url.lower():
        return {
            "ok": False,
            "url": tab.url,
            "challenge": "not-on-google-signin-page",
        }

    # ── account chooser ──────────────────────────────────────────────
    # If a tile for our email is on screen, click it directly (Google
    # will go straight to the password page). Otherwise click "Use
    # another account" and fall through to the email input below.
    # JS click is used: CDP-synthesised mouse events don't fire on
    # Google's chooser tile handlers.
    if await tab.exists('[jsname="rwl3qc"]'):
        existing_tile = f"[data-identifier={json.dumps(email)}]"
        clicked_tile = await _js_click(tab, existing_tile)
        if not clicked_tile:
            clicked_tile = await _js_click(tab, '[jsname="rwl3qc"]')
        if not clicked_tile:
            return {
                "ok": False,
                "url": tab.url,
                "challenge": "account-chooser-stuck",
            }
        await asyncio.sleep(1.5)

    # ── email step (skipped if we clicked the existing tile) ─────────
    if await tab.exists("#identifierId") or await tab.exists('input[name="identifier"]'):
        email_filled = False
        for sel in (
            "#identifierId",
            'input[name="identifier"]',
            'input[aria-label*="Email" i]',
        ):
            try:
                await tab.fill(sel, email, timeout=8.0)
                email_filled = True
                break
            except Exception:
                continue
        if not email_filled:
            return {"ok": False, "url": tab.url, "challenge": "email-input-not-found"}
        try:
            await tab.click("#identifierNext", timeout=4.0)
        except Exception:
            pass
        await asyncio.sleep(1.5)

    # ── password step ────────────────────────────────────────────────
    pwd_sel = None
    for sel in (
        'input[type="password"]',
        'input[name="Passwd"]',
        'input[aria-label*="password" i]',
    ):
        try:
            await tab.find(sel, timeout=timeout / 4)
            pwd_sel = sel
            break
        except TimeoutError:
            continue
    if pwd_sel is None:
        # Possibly already redirected back to the client (silent SSO).
        if "accounts.google.com" not in tab.url.lower():
            return {"ok": True, "url": tab.url, "challenge": None}
        return {"ok": False, "url": tab.url, "challenge": "password-page-never-appeared"}
    await asyncio.sleep(0.8)
    await tab.fill(pwd_sel, password, timeout=timeout)
    try:
        await tab.click("#passwordNext", timeout=4.0)
    except Exception:
        pass

    # ── wait for redirect away from accounts.google.com ──────────────
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_challenge: str | None = None

    while loop.time() < deadline:
        await asyncio.sleep(1.0)
        url = tab.url
        if "accounts.google.com" not in url.lower():
            return {"ok": True, "url": url, "challenge": None}

        body_text = (await tab.evaluate("document.body.innerText", default="") or "").lower()
        for needle in _PASSWORD_REJECTED_FRAGMENTS:
            if needle in body_text:
                return {"ok": False, "url": url, "challenge": "wrong-password"}

        if any(p.search(url) for p in _CHALLENGE_PATTERNS):
            if totp_secret and _totp.available():
                if await _try_totp(tab, totp_secret):
                    last_challenge = "totp-submitted"
                    continue
                last_challenge = "totp-failed"
            else:
                last_challenge = "totp_missing"
            if "recovery" in url.lower() or "recovery" in body_text:
                return {"ok": False, "url": url, "challenge": "recovery"}
            if "tap" in body_text and "phone" in body_text:
                return {"ok": False, "url": url, "challenge": "phone-prompt"}

    return {"ok": False, "url": tab.url, "challenge": last_challenge or "timeout"}


async def _verify_logged_in(tab: Tab) -> bool:
    """Hard-check by navigating to myaccount.google.com.

    Returns True if we land on the dashboard, False if Google bounces
    us back to a sign-in URL.
    """
    try:
        await tab.goto("https://myaccount.google.com/", timeout=20.0)
    except Exception:
        return False
    await asyncio.sleep(1.0)
    final = tab.url.lower()
    if "myaccount.google.com" in final and "signin" not in final:
        return True
    return False


async def _resolve_tab(browser_or_tab: Browser | Tab) -> Tab:
    from ..browser import Browser as _B  # avoid circular import at module load

    if isinstance(browser_or_tab, _B):
        return await browser_or_tab.new_tab()
    return browser_or_tab  # already a Tab


async def _js_click(tab: Tab, selector: str) -> bool:
    """Trigger element.click() in the page's JS context.

    Google's account-chooser tiles are ``<div role=link>`` whose click
    handlers don't reliably fire under CDP-synthesised mouse events.
    Calling ``element.click()`` from JS dispatches a real click event
    inside the page's own runtime and goes through.
    """
    sel_json = json.dumps(selector)
    try:
        result = await tab.evaluate(
            f"(() => {{ const t = document.querySelector({sel_json}); "
            f"if (!t) return null; t.click(); return 'clicked'; }})()",
            default=None,
        )
    except Exception:
        return False
    return bool(result == "clicked")


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
