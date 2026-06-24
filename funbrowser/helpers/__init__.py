"""Ready-to-use helpers for common automation flows.

These bundle a sequence of stealth + humanly + form-filling steps that
would otherwise be ~30 lines of boilerplate per site. They're
**best-effort**: third-party UIs change without notice, so treat each
helper as a recipe and pin to a working FunBrowser version if you build
infrastructure on top.

What ships:

- :mod:`funbrowser.helpers.google` — Google account login via
  accounts.google.com, with optional TOTP
- :mod:`funbrowser.helpers.totp` — generate the 6-digit TOTP code from
  a base32 secret (needs ``pip install funbrowser[automation]``)
"""

from __future__ import annotations
