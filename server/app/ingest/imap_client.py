"""The IMAP fetch seam (CLAUDE.md §9 — one of the four injected dependencies alongside the
clock, the LLM client, and the ntfy publisher). Nothing in `app/ingest/` may open a socket
directly; everything goes through `ImapFetcher`, so tests run against `FakeImapFetcher` and
production wires up `RealImapFetcher`.

Read-only by construction (CLAUDE.md §8 item 4): `RealImapFetcher` only ever issues
`BODY.PEEK[]` fetches, never plain `BODY[]` — the former does not set the IMAP `\\Seen` flag,
so polling never mutates the mailbox. Because flags are never touched, "already processed" is
tracked entirely by our own `ingest_events.message_id` dedupe, not by IMAP read-state — each
poll re-scans a rolling window (`since_days`) and lets dedupe skip what it's already seen.
"""

import email
import imaplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Protocol


@dataclass(frozen=True)
class FetchedEmail:
    message_id: str
    sender: str
    subject: str
    body: str
    raw: str
    received_at: datetime


class ImapFetcher(Protocol):
    def fetch_recent(self) -> list[FetchedEmail]: ...


class FakeImapFetcher:
    """Test double — returns whatever's handed to it, no network involved."""

    def __init__(self, emails: list[FetchedEmail]):
        self._emails = emails

    def fetch_recent(self) -> list[FetchedEmail]:
        return list(self._emails)


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _plaintext_body(msg: email.message.Message) -> str:
    """Prefer a text/plain part; fall back to a crude HTML-tag strip if only text/html exists
    — real Amex/US Bank alert emails observed in Phase -1 vary between the two."""
    if msg.is_multipart():
        html_fallback = None
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                return part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
            if content_type == "text/html" and html_fallback is None:
                html_fallback = part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
        if html_fallback is not None:
            return _strip_html(html_fallback)
        return ""
    payload = msg.get_payload(decode=True)
    text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return _strip_html(text) if msg.get_content_type() == "text/html" else text


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class RealImapFetcher:
    def __init__(
        self, host: str, port: int, user: str, password: str, label: str, since_days: int = 3
    ):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._label = label
        self._since_days = since_days

    def fetch_recent(self) -> list[FetchedEmail]:
        conn = imaplib.IMAP4_SSL(self._host, self._port)
        try:
            conn.login(self._user, self._password)
            conn.select(f'"{self._label}"', readonly=True)
            since = (datetime.now(timezone.utc) - timedelta(days=self._since_days)).strftime(
                "%d-%b-%Y"
            )
            status, data = conn.search(None, f"(SINCE {since})")
            if status != "OK" or not data or not data[0]:
                return []
            results = []
            for num in data[0].split():
                # BODY.PEEK[] — never sets \Seen (the read-only invariant, CLAUDE.md §8).
                status, msg_data = conn.fetch(num, "(BODY.PEEK[])")
                if status != "OK" or not msg_data or msg_data[0] is None:
                    continue
                raw_bytes = msg_data[0][1]
                raw_text = raw_bytes.decode("utf-8", errors="replace")
                msg = email.message_from_bytes(raw_bytes)
                message_id = msg.get("Message-ID", "").strip()
                if not message_id:
                    continue
                date_header = msg.get("Date")
                received_at = (
                    parsedate_to_datetime(date_header)
                    if date_header
                    else datetime.now(timezone.utc)
                )
                results.append(
                    FetchedEmail(
                        message_id=message_id,
                        sender=email.utils.parseaddr(msg.get("From", ""))[1],
                        subject=_decode(msg.get("Subject")),
                        body=_plaintext_body(msg),
                        raw=raw_text,
                        received_at=received_at,
                    )
                )
            return results
        finally:
            try:
                conn.close()
            except imaplib.IMAP4.error:
                pass
            conn.logout()
