"""Orchestrates one ingestion poll (CLAUDE.md Phase 4): fetch -> dedupe -> parse -> resolve
account -> create a pending transaction, or fall back to an "unparsed" ingest_event.

Deliberately does NOT yet implement pending->posted matching against CSV truth (the CSV
importer, Phase 3, still creates its own rows independent of what email ingestion filed) —
that's a distinct, separately-scoped increment touching `import_service.py`'s matching logic,
not something to fold in silently here. Documented as a fast-follow in ARCHITECTURE.md.
"""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.imap_client import ImapFetcher
from app.ingest.parsers import UnparsedEmail, parse_email
from app.models.account import Account
from app.models.ingest_event import IngestEvent
from app.models.transaction import Transaction


@dataclass(frozen=True)
class IngestPollSummary:
    fetched: int
    created: int
    duplicate: int
    unparsed: int


async def _match_account(
    db: AsyncSession, user_id: uuid.UUID, last4_hint: str | None
) -> Account | None:
    if last4_hint is None:
        return None
    result = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.last4 == last4_hint)
    )
    return result.scalar_one_or_none()


async def run_ingest_poll(
    db: AsyncSession, user_id: uuid.UUID, fetcher: ImapFetcher
) -> IngestPollSummary:
    fetched = fetcher.fetch_recent()
    created = duplicate = unparsed = 0

    for item in fetched:
        existing = await db.execute(
            select(IngestEvent).where(IngestEvent.message_id == item.message_id)
        )
        if existing.scalar_one_or_none() is not None:
            duplicate += 1
            continue

        payload_hash = hashlib.sha256(item.raw.encode()).hexdigest()

        try:
            parsed = parse_email(item.sender, item.subject, item.body)
        except UnparsedEmail:
            db.add(
                IngestEvent(
                    user_id=user_id,
                    account_id=None,
                    message_id=item.message_id,
                    received_at=item.received_at,
                    parser=item.sender,
                    parse_version="0",
                    payload_hash=payload_hash,
                    outcome="unparsed",
                    raw_payload=item.raw,
                )
            )
            unparsed += 1
            continue

        account = await _match_account(db, user_id, parsed.last4_hint)

        event = IngestEvent(
            user_id=user_id,
            account_id=account.id if account else None,
            message_id=item.message_id,
            received_at=item.received_at,
            parser=parsed.parser,
            parse_version=parsed.parse_version,
            payload_hash=payload_hash,
            # A parsed-but-unmatched-account email still can't safely become a transaction —
            # same operator-visible bucket as a template we don't recognize at all.
            outcome="created" if account else "unparsed",
            raw_payload=item.raw,
        )
        db.add(event)
        await db.flush()

        if account is None:
            unparsed += 1
            continue

        db.add(
            Transaction(
                account_id=account.id,
                amount=parsed.amount_cents,
                date=parsed.event_date or item.received_at.date(),
                status="pending",
                merchant_raw=parsed.merchant,
                kind=parsed.kind,
                review_state="needs_review",
                source="email",
                ingest_event_id=event.id,
            )
        )
        created += 1

    await db.commit()
    return IngestPollSummary(
        fetched=len(fetched), created=created, duplicate=duplicate, unparsed=unparsed
    )
