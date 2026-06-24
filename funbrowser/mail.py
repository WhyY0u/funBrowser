"""Async IMAP helper for fetching verification codes from email.

Stdlib-only — no extra dependency. Use it inline with automation:

    async with IMAPMail("imap.gmail.com", "alice@gmail.com", APP_PASSWORD) as m:
        code = await m.wait_for_code(
            sender_contains="example.com",
            pattern=r"\\b(\\d{6})\\b",
            timeout=120,
        )

Works against any IMAP host (Gmail, iCloud, Outlook, Yandex, ...). For
Gmail / iCloud you need an **app-specific password**, not the main
account password.
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import logging
import re
import time
from dataclasses import dataclass
from email.message import Message
from email.utils import parseaddr
from types import TracebackType
from typing import Any, Self

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MailMessage:
    uid: str
    from_addr: str
    subject: str
    body: str
    received_ts: float


class IMAPMail:
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        *,
        port: int = 993,
        use_ssl: bool = True,
        mailbox: str = "INBOX",
    ) -> None:
        self._host = host
        self._user = user
        self._password = password
        self._port = port
        self._use_ssl = use_ssl
        self._mailbox = mailbox
        self._conn: imaplib.IMAP4 | None = None

    async def connect(self) -> None:
        def _do() -> imaplib.IMAP4:
            if self._use_ssl:
                conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(self._host, self._port)
            else:
                conn = imaplib.IMAP4(self._host, self._port)
            conn.login(self._user, self._password)
            conn.select(self._mailbox)
            return conn

        self._conn = await asyncio.to_thread(_do)

    async def disconnect(self) -> None:
        if self._conn is None:
            return
        conn = self._conn
        self._conn = None

        def _do() -> None:
            try:
                conn.close()
            except Exception:
                pass
            try:
                conn.logout()
            except Exception:
                pass

        await asyncio.to_thread(_do)

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.disconnect()

    async def list_recent(self, *, limit: int = 20) -> list[MailMessage]:
        """Most-recent N messages in the selected mailbox, newest first."""
        uids = await self._search_uids()
        if not uids:
            return []
        uids = uids[-limit:][::-1]
        out: list[MailMessage] = []
        for uid in uids:
            msg = await self._fetch_message(uid)
            if msg is not None:
                out.append(msg)
        return out

    async def wait_for_code(
        self,
        *,
        pattern: str = r"\b(\d{4,8})\b",
        sender_contains: str | None = None,
        subject_contains: str | None = None,
        body_contains: str | None = None,
        since_ts: float | None = None,
        timeout: float = 60.0,
        poll_interval: float = 3.0,
    ) -> str:
        """Poll for a new matching message and extract a code.

        Returns the **first capture group** of ``pattern`` (or the whole
        match if the regex has none).

        Filters are AND-ed together. ``since_ts`` is the cutoff for
        "new" — defaults to now, so we only look at mail arriving after
        the wait_for_code call starts. Pass a specific timestamp if you
        kicked off the verification flow before connecting.

        Raises :class:`TimeoutError` if no matching message arrives in
        ``timeout`` seconds.
        """
        if self._conn is None:
            raise RuntimeError("IMAPMail not connected; use `async with`")
        regex = re.compile(pattern)
        loop = asyncio.get_running_loop()
        start = loop.time()
        deadline = start + timeout
        cutoff = since_ts if since_ts is not None else time.time()
        seen: set[str] = set()

        # Prime: ignore everything currently in the mailbox; only react to
        # NEW arrivals after this call. Matches the typical flow ("click
        # 'send code' on the site, then wait").
        seen.update(await self._search_uids())

        while loop.time() < deadline:
            uids = await self._search_uids()
            for uid in uids:
                if uid in seen:
                    continue
                msg = await self._fetch_message(uid)
                seen.add(uid)
                if msg is None:
                    continue
                if msg.received_ts and msg.received_ts < cutoff - 60:
                    # older than our window; ignore
                    continue
                if sender_contains and sender_contains.lower() not in msg.from_addr.lower():
                    continue
                if subject_contains and subject_contains.lower() not in msg.subject.lower():
                    continue
                if body_contains and body_contains.lower() not in msg.body.lower():
                    continue
                m = regex.search(msg.body) or regex.search(msg.subject)
                if m:
                    return m.group(1) if m.groups() else m.group(0)
            await asyncio.sleep(poll_interval)

        raise TimeoutError(
            f"no matching email arrived in {timeout}s "
            f"(filters: sender={sender_contains!r}, subject={subject_contains!r})"
        )

    # ── internal IMAP wrappers ────────────────────────────────────────

    async def _search_uids(self) -> list[str]:
        if self._conn is None:
            return []
        conn = self._conn

        def _do() -> list[str]:
            typ, data = conn.uid("SEARCH", "ALL")
            if typ != "OK" or not data or not data[0]:
                return []
            return [u.decode() for u in data[0].split()]

        return await asyncio.to_thread(_do)

    async def _fetch_message(self, uid: str) -> MailMessage | None:
        if self._conn is None:
            return None
        conn = self._conn

        def _do() -> MailMessage | None:
            typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not data or not data[0]:
                return None
            raw = data[0][1] if isinstance(data[0], tuple) else data[0]
            if isinstance(raw, str):
                raw_bytes = raw.encode("utf-8", errors="replace")
            else:
                raw_bytes = raw
            msg: Message = email.message_from_bytes(raw_bytes)
            return _to_mail_message(uid, msg)

        return await asyncio.to_thread(_do)


def _to_mail_message(uid: str, msg: Message) -> MailMessage:
    _, addr = parseaddr(msg.get("From", ""))
    subject = _decode_header(msg.get("Subject", ""))
    body = _extract_body(msg)
    received_ts = 0.0
    date_hdr = msg.get("Date")
    if date_hdr:
        try:
            parsed = email.utils.parsedate_tz(date_hdr)
            if parsed is not None:
                received_ts = float(email.utils.mktime_tz(parsed))
        except Exception:
            pass
    return MailMessage(
        uid=uid,
        from_addr=addr,
        subject=subject,
        body=body,
        received_ts=received_ts,
    )


def _decode_header(raw: str) -> str:
    try:
        parts = email.header.decode_header(raw)
    except Exception:
        return raw
    out: list[str] = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _extract_body(msg: Message) -> str:
    """Best-effort plain-text body extraction. Walks multipart, picks
    text/plain first, falls back to stripping tags from text/html."""
    text_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get_content_disposition() == "attachment":
                continue
            payload: Any = part.get_payload(decode=True)
            if not isinstance(payload, bytes | bytearray | memoryview):
                continue
            payload_bytes = bytes(payload)
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload_bytes.decode(charset, errors="replace")
            except LookupError:
                decoded = payload_bytes.decode("utf-8", errors="replace")
            if ctype == "text/plain":
                text_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(decoded)
    else:
        payload_raw: Any = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        if isinstance(payload_raw, bytes | bytearray | memoryview):
            data = bytes(payload_raw)
            try:
                text_parts.append(data.decode(charset, errors="replace"))
            except LookupError:
                text_parts.append(data.decode("utf-8", errors="replace"))
        elif isinstance(payload_raw, str):
            text_parts.append(payload_raw)

    if text_parts:
        return "\n".join(text_parts)
    if html_parts:
        return _strip_tags("\n".join(html_parts))
    return ""


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    return _TAG_RE.sub(" ", html)
