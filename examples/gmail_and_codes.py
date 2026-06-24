"""End-to-end: log into a Google account, then grab a one-time code
from a separate inbox via IMAP.

Common flow when automating signups / logins:

1. Open the browser, navigate to the target site, kick off "sign in with Google".
2. Drive Google's accounts.google.com via :func:`funbrowser.helpers.google.login`.
3. Wait on the target's mailbox for the 6-digit verification code via
   :class:`funbrowser.IMAPMail`.
4. Type the code into the page and finish.

Run with::

    GMAIL_USER=alice@gmail.com \\
    GMAIL_APP_PASSWORD='abcd efgh ijkl mnop' \\
    GMAIL_PASSWORD='browser-login-password' \\
    uv run python examples/gmail_and_codes.py

Notes
-----

- The Gmail IMAP **app password** is different from the account password.
  Generate one at https://myaccount.google.com/apppasswords. The browser
  login on the other hand uses the actual account password.
- 2FA-enabled accounts: pass ``totp_secret=`` to
  :func:`helpers.google.login`. Without it, the helper returns
  ``{"ok": False, "challenge": "totp_missing"}`` and you can fall back to
  manual interaction.
- This whole flow benefits from running with ``humanly=True`` and a
  warmed-up ``user_data_dir`` profile. Fresh profiles trip Google's
  "Verify it's you" prompt aggressively.
"""

from __future__ import annotations

import asyncio
import os

import funbrowser
from funbrowser import IMAPMail, helpers, presets


async def main() -> None:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pwd = os.environ["GMAIL_PASSWORD"]
    gmail_app_pwd = os.environ["GMAIL_APP_PASSWORD"]

    async with funbrowser.start(
        headless=False,
        fingerprint=presets.windows_11_nvidia_rtx_4070(),
        humanly=True,
    ) as browser:
        # 1. Log into Google in the browser.
        print("→ logging into Google ...")
        result = await helpers.google.login(
            browser,
            email=gmail_user,
            password=gmail_pwd,
            # totp_secret="JBSWY3DPEHPK3PXP",  # uncomment for 2FA accounts
        )
        if not result["ok"]:
            print(f"  stuck at: {result['url']} — challenge={result['challenge']}")
            return
        print(f"  logged in: {result['url']}")

        # 2. Open the target site and trigger "send me a code".
        tab = await browser.get("https://example-target.com/login")
        # ... your selectors here ...
        # await tab.fill("input[type=email]", gmail_user)
        # await tab.click("button#send-code")

        # 3. Poll Gmail via IMAP for the verification code.
        print("→ waiting on Gmail for code ...")
        async with IMAPMail(
            host="imap.gmail.com",
            username=gmail_user,
            password=gmail_app_pwd,
        ) as mailbox:
            code = await mailbox.wait_for_code(
                sender_contains="example-target.com",
                subject_contains="verification",
                pattern=r"\b(\d{6})\b",
                timeout=120,
            )
        print(f"  got code: {code}")

        # 4. Type it into the target site and finish.
        # await tab.fill("input[name=otp]", code)
        # await tab.click("button[type=submit]")
        _ = tab  # silence unused — you'd fill the form here


if __name__ == "__main__":
    asyncio.run(main())
