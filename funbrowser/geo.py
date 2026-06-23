"""Infer timezone / locale / accept-language from a proxy's exit IP.

When a Browser is started with a proxy and ``geo_autoconfigure=True``
(the default), we route a short ``ip-api.com`` lookup through the proxy
to get the exit IP's country and timezone, then fill any
:class:`Fingerprint` fields the caller didn't set explicitly.

Calling site keeps full control: explicit ``timezone`` / ``locale`` on
the caller-supplied Fingerprint always win over the geo guess.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from .proxy import Proxy

logger = logging.getLogger(__name__)

# Country code → primary BCP-47 locale. Covers the cases proxy providers
# routinely hand out; unknown countries fall back to country_code.lower() +
# '-' + country_code.upper() in resolve_locale().
_LOCALE: dict[str, str] = {
    "US": "en-US",
    "CA": "en-CA",
    "GB": "en-GB",
    "AU": "en-AU",
    "IE": "en-IE",
    "NZ": "en-NZ",
    "DE": "de-DE",
    "AT": "de-AT",
    "CH": "de-CH",
    "FR": "fr-FR",
    "BE": "fr-BE",
    "IT": "it-IT",
    "ES": "es-ES",
    "MX": "es-MX",
    "AR": "es-AR",
    "BR": "pt-BR",
    "PT": "pt-PT",
    "NL": "nl-NL",
    "SE": "sv-SE",
    "NO": "nb-NO",
    "DK": "da-DK",
    "FI": "fi-FI",
    "PL": "pl-PL",
    "CZ": "cs-CZ",
    "RU": "ru-RU",
    "UA": "uk-UA",
    "KZ": "ru-KZ",
    "BY": "be-BY",
    "TR": "tr-TR",
    "JP": "ja-JP",
    "KR": "ko-KR",
    "CN": "zh-CN",
    "TW": "zh-TW",
    "HK": "zh-HK",
    "IN": "en-IN",
    "ID": "id-ID",
    "TH": "th-TH",
    "VN": "vi-VN",
    "IL": "he-IL",
    "AE": "ar-AE",
    "SA": "ar-SA",
    "EG": "ar-EG",
}


@dataclass(frozen=True, slots=True)
class GeoInfo:
    """Geolocation hints derived from a proxy's exit IP."""

    ip: str
    country_code: str
    country: str
    region: str
    city: str
    timezone: str
    locale: str
    accept_language: str


def resolve_locale(country_code: str) -> str:
    cc = country_code.upper()
    if cc in _LOCALE:
        return _LOCALE[cc]
    return f"{cc.lower()}-{cc}"


def make_accept_language(locale: str) -> str:
    """Build an Accept-Language header value: the locale + its base + 'en'."""
    base = locale.split("-", 1)[0]
    parts = [locale]
    if base != locale:
        parts.append(f"{base};q=0.9")
    if base != "en":
        parts.append("en;q=0.8")
    return ",".join(parts)


async def lookup_proxy_geo(proxy: Proxy, *, timeout: float = 5.0) -> GeoInfo | None:
    """Fetch geo information for the proxy's exit IP via ip-api.com.

    Returns ``None`` on any failure (proxy down, ip-api rate-limited, etc.).
    Never raises — the call site treats a missing result as "skip".
    """
    try:
        proxy_url = proxy.url()
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            r = await client.get(
                "http://ip-api.com/json/",
                params={"fields": "status,country,countryCode,region,city,timezone,query"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        logger.debug("geo lookup failed", exc_info=True)
        return None

    if data.get("status") != "success":
        return None

    cc = str(data.get("countryCode") or "")
    if not cc:
        return None
    locale = resolve_locale(cc)
    return GeoInfo(
        ip=str(data.get("query") or ""),
        country_code=cc,
        country=str(data.get("country") or ""),
        region=str(data.get("region") or ""),
        city=str(data.get("city") or ""),
        timezone=str(data.get("timezone") or ""),
        locale=locale,
        accept_language=make_accept_language(locale),
    )
