"""TLS fingerprint impersonation.

Two surfaces:

- :class:`funbrowser.tls.ImpersonatedHTTPClient` — script-level HTTP client.
  Hits APIs directly from your Python code with a real-browser JA3/JA4
  fingerprint (chrome131, safari17, firefox133, …). Useful when you want
  to call an endpoint from script logic with the same TLS signature
  Cloudflare expects from a Chrome user, without going through the
  browser at all.

- ``Browser.start(tls_impersonate="chrome131")`` — proxies Chrome's own
  HTTPS traffic through a local mitm that re-encrypts upstream with
  curl_cffi's spoofed TLS. Closes the gap for sites that probe the
  browser's TLS handshake. **Alpha** — see :mod:`funbrowser.tls.mitm`
  for current limitations.

Install with ``pip install funbrowser[tls]``.
"""

from __future__ import annotations

from .http import SUPPORTED_PROFILES, ImpersonatedHTTPClient, available

__all__ = ["SUPPORTED_PROFILES", "ImpersonatedHTTPClient", "available"]
