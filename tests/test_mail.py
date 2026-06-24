"""IMAPMail tests with a stubbed imaplib backend."""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
from typing import Any

import pytest

import funbrowser.mail as mail_mod
from funbrowser.mail import IMAPMail, _extract_body


def _mk_raw_email(
    *,
    from_addr: str,
    subject: str,
    body: str,
    date: str | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["Subject"] = subject
    if date is not None:
        msg["Date"] = date
    msg.set_content(body)
    return msg.as_bytes()


class FakeIMAP:
    """Stubs the subset of imaplib.IMAP4_SSL that IMAPMail uses."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.messages: dict[str, bytes] = {}
        self.next_uid = 1
        self.actions: list[str] = []

    def add_email(self, **kw: Any) -> str:
        uid = str(self.next_uid)
        self.next_uid += 1
        self.messages[uid] = _mk_raw_email(**kw)
        return uid

    def login(self, user: str, pwd: str) -> tuple[str, list[bytes]]:
        self.actions.append(f"login:{user}")
        return ("OK", [b"Logged in"])

    def select(self, mailbox: str) -> tuple[str, list[bytes]]:
        self.actions.append(f"select:{mailbox}")
        return ("OK", [b""])

    def uid(self, cmd: str, *args: str) -> tuple[str, list[Any]]:
        cmd = cmd.upper()
        if cmd == "SEARCH":
            uids = " ".join(sorted(self.messages.keys(), key=int)).encode()
            return ("OK", [uids])
        if cmd == "FETCH":
            uid = args[0]
            raw = self.messages.get(uid, b"")
            return ("OK", [(b"x", raw)])
        return ("BAD", [])

    def close(self) -> None:
        self.actions.append("close")

    def logout(self) -> tuple[str, list[bytes]]:
        self.actions.append("logout")
        return ("BYE", [])


@pytest.fixture
def fake_imap(monkeypatch: pytest.MonkeyPatch) -> FakeIMAP:
    instance = FakeIMAP()

    def _factory(*args: Any, **kwargs: Any) -> FakeIMAP:
        return instance

    monkeypatch.setattr(mail_mod.imaplib, "IMAP4_SSL", _factory)
    monkeypatch.setattr(mail_mod.imaplib, "IMAP4", _factory)
    return instance


# ── pure helpers ────────────────────────────────────────────────────


def test_extract_body_text() -> None:
    msg = EmailMessage()
    msg.set_content("Your code is 123456.")
    assert "123456" in _extract_body(msg)


def test_extract_body_html_fallback() -> None:
    msg = EmailMessage()
    msg.add_alternative("<p>Your code is <b>987654</b>.</p>", subtype="html")
    body = _extract_body(msg)
    assert "987654" in body
    assert "<b>" not in body


# ── async wait_for_code ────────────────────────────────────────────


async def test_wait_for_code_extracts_first_capture_group(
    fake_imap: FakeIMAP,
) -> None:
    async with IMAPMail("imap.example.com", "alice", "pw") as m:
        # Inject a new message after a short delay.
        async def add() -> None:
            await asyncio.sleep(0.1)
            fake_imap.add_email(
                from_addr="noreply@target.com",
                subject="Your verification code",
                body="Hi! Your code is 654321. Don't share.",
            )

        asyncio.get_event_loop().create_task(add())
        code = await m.wait_for_code(
            sender_contains="target.com",
            pattern=r"\b(\d{6})\b",
            timeout=5,
            poll_interval=0.1,
        )
        assert code == "654321"


async def test_wait_for_code_filters_by_sender(fake_imap: FakeIMAP) -> None:
    # Pre-existing message from wrong sender — should be ignored as
    # "already seen" on connect.
    fake_imap.add_email(
        from_addr="other@wrong.com",
        subject="Code 111111",
        body="111111",
    )

    async with IMAPMail("imap.example.com", "alice", "pw") as m:

        async def add() -> None:
            await asyncio.sleep(0.1)
            fake_imap.add_email(
                from_addr="noreply@target.com",
                subject="Your code",
                body="222222",
            )

        asyncio.get_event_loop().create_task(add())
        code = await m.wait_for_code(
            sender_contains="target.com",
            pattern=r"\b(\d{6})\b",
            timeout=5,
            poll_interval=0.1,
        )
        assert code == "222222"


async def test_wait_for_code_timeout(fake_imap: FakeIMAP) -> None:
    async with IMAPMail("imap.example.com", "alice", "pw") as m:
        with pytest.raises(TimeoutError):
            await m.wait_for_code(
                sender_contains="target.com",
                pattern=r"\b(\d{6})\b",
                timeout=0.3,
                poll_interval=0.05,
            )


async def test_list_recent_returns_messages(fake_imap: FakeIMAP) -> None:
    fake_imap.add_email(from_addr="a@x.com", subject="One", body="hi")
    fake_imap.add_email(from_addr="b@x.com", subject="Two", body="hi 2")
    async with IMAPMail("imap.example.com", "alice", "pw") as m:
        recent = await m.list_recent(limit=10)
        assert len(recent) == 2
        # newest first
        assert recent[0].subject == "Two"
        assert recent[1].subject == "One"
