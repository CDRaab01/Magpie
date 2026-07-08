"""Orchestrates one ingestion poll (CLAUDE.md Phase 4): fetch -> dedupe -> parse -> resolve
account -> create a pending transaction, or fall back to an "unparsed" ingest_event.

Pending->posted reconciliation (F4) lives on the *import* side, not here: when the monthly CSV
imports a swipe that this poll already captured as pending, `import_service.py` promotes the
pending row to posted rather than creating a second row (see `app/imports/pending_match.py`).
This module's only job is to file the fresh pending swipe.
"""

import datetime
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingest.imap_client import ImapFetcher
from app.ingest.parsers import UnparsedEmail, parse_email
from app.models.account import Account
from app.models.ingest_event import IngestEvent
from app.models.transaction import Transaction
from app.rules.merchant_match import normalize_merchant
from app.services.ai.llm_client import LmStudioClient
from app.services.rule_service import evaluate_transaction


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
    accounts = result.scalars().all()
    # F16: two accounts can legitimately share a last4 (a card and a checking account, or two
    # cards). An ambiguous match is not a crash — `scalar_one_or_none()` would raise and abort
    # the whole poll batch. Degrade to "no match" so the event lands in the unparsed operator
    # view instead, and the rest of the batch still processes.
    return accounts[0] if len(accounts) == 1 else None


async def run_ingest_poll(
    db: AsyncSession,
    user_id: uuid.UUID,
    fetcher: ImapFetcher,
    *,
    now: datetime.datetime | None = None,
) -> IngestPollSummary:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    fetched = fetcher.fetch_recent()
    created = duplicate = unparsed = 0
    llm_client = (
        LmStudioClient(settings.llm_base_url, settings.llm_model) if settings.llm_base_url else None
    )

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

        txn_date = parsed.event_date or item.received_at.date()
        evaluation = await evaluate_transaction(
            db,
            user_id,
            account_id=account.id,
            amount_cents=parsed.amount_cents,
            txn_date=txn_date,
            merchant_raw=parsed.merchant,
            default_kind=parsed.kind,
            now=now,
            llm_client=llm_client,
        )
        db.add(
            Transaction(
                account_id=account.id,
                amount=parsed.amount_cents,
                date=txn_date,
                status="pending",
                merchant_raw=parsed.merchant,
                merchant_norm=normalize_merchant(parsed.merchant) if parsed.merchant else None,
                kind=evaluation.kind,
                review_state=evaluation.review_state,
                category_id=evaluation.category_id,
                matched_rule_id=evaluation.matched_rule_id,
                rule_note=evaluation.rule_note,
                ai_suggested_category_id=evaluation.ai_suggested_category_id,
                transfer_group=evaluation.transfer_group,
                source="email",
                ingest_event_id=event.id,
            )
        )
        await db.flush()
        created += 1

    await db.commit()
    return IngestPollSummary(
        fetched=len(fetched), created=created, duplicate=duplicate, unparsed=unparsed
    )
