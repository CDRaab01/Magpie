"""Parser replay over `ingest_events.raw_payload` (V1 finding F15; ROADMAP Wave 0 #7).

Every email the poller ever saw is kept whole, with the `parse_version` that read it — so a
parser fix is replayable over history and **a bad parse is recoverable, never permanent**
(CLAUDE.md §9). This module is the machinery that cashes that promise in.

The immediate customer: the 22 real Amex alerts that arrived *before* their account existed.
They parsed fine; `_match_account` found no account, so they were filed `unparsed` with no
transaction. Creating the account fixes the future, not the past. Replay retro-files the past.

Scope, deliberately narrow:

* Only `unparsed` events are replayed. A `created` event already has a transaction, and
  re-parsing it would mean *mutating* live financial history — a far larger blast radius that
  belongs behind its own review surface, not a bulk button. (`duplicate` never reaches the
  table: the poller skips those before writing a row.)
* Replay never double-counts. Two independent guards, because this writes money:
  1. an event that already has a transaction pointing at it is skipped outright (replay is
     idempotent — running it twice changes nothing the second time);
  2. an alert whose swipe the CSV backfill already posted is recorded as `duplicate` rather
     than filed, via the same "same swipe" tolerance reconciliation uses
     (`imports/pending_match.find_posted_duplicate`). The 22 Amex alerts sit inside the
     18-month Amex import, so this is the common case, not a corner one.

`dry_run` is the default at every layer above this one: it runs the *identical* code path and
rolls the transaction back, so the report a human reads is a report of what would really happen
— not of what a parallel "simulation" branch guessed would happen.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.imports.pending_match import PendingCandidate, find_posted_duplicate
from app.ingest.imap_client import message_parts
from app.ingest.parsers import UnparsedEmail, parse_email
from app.models.ingest_event import IngestEvent
from app.models.transaction import Transaction
from app.services.ingest_service import (
    build_transaction_for_event,
    make_llm_client,
    match_account,
    resolve_txn_date,
)

# What replay decided about one event. `outcome` mirrors INGEST_OUTCOMES; `reason` is operator
# prose — this tool's whole value is explaining why history did or didn't move.
REPLAY_ACTIONS = ("filed", "duplicate", "still_unparsed", "skipped")


@dataclass(frozen=True)
class ReplayEventResult:
    event_id: uuid.UUID
    message_id: str
    action: str
    reason: str
    amount_cents: int | None = None
    merchant: str | None = None
    txn_date: datetime.date | None = None


@dataclass(frozen=True)
class ReplaySummary:
    dry_run: bool
    examined: int
    filed: int
    duplicate: int
    still_unparsed: int
    skipped: int
    events: list[ReplayEventResult]


async def _already_filed(db: AsyncSession, event_id: uuid.UUID) -> bool:
    existing = await db.scalar(
        select(Transaction.id).where(Transaction.ingest_event_id == event_id).limit(1)
    )
    return existing is not None


async def _posted_candidates(
    db: AsyncSession, account_id: uuid.UUID, txn_date: datetime.date, window_days: int = 3
) -> list[PendingCandidate]:
    """Posted rows near this date on this account — the pool the CSV backfill would have filled.

    Bounded by the same window the matcher tolerates so a backfilled year never loads into
    Python (F14 discipline); `is_split` children are excluded because a split's parent already
    carries the swipe's full amount.
    """
    lo = txn_date - datetime.timedelta(days=window_days)
    hi = txn_date + datetime.timedelta(days=window_days)
    rows = await db.execute(
        select(Transaction.id, Transaction.amount, Transaction.date).where(
            Transaction.account_id == account_id,
            Transaction.status == "posted",
            Transaction.split_parent_id.is_(None),
            Transaction.date >= lo,
            Transaction.date <= hi,
        )
    )
    return [PendingCandidate(id=str(r.id), amount_cents=r.amount, date=r.date) for r in rows]


async def replay_unparsed_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    dry_run: bool = True,
    now: datetime.datetime | None = None,
    event_ids: list[uuid.UUID] | None = None,
) -> ReplaySummary:
    """Re-parse this user's `unparsed` ingest events with today's parsers and file what now fits.

    Returns a per-event report. When `dry_run`, every write is rolled back before returning —
    the report still describes exactly what the real run would do, because it *did* it.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    llm_client = make_llm_client()

    query = select(IngestEvent).where(
        IngestEvent.user_id == user_id, IngestEvent.outcome == "unparsed"
    )
    if event_ids is not None:
        query = query.where(IngestEvent.id.in_(event_ids))
    events = list((await db.execute(query.order_by(IngestEvent.received_at))).scalars().all())

    results: list[ReplayEventResult] = []

    for event in events:
        if await _already_filed(db, event.id):
            results.append(
                ReplayEventResult(
                    event_id=event.id,
                    message_id=event.message_id,
                    action="skipped",
                    reason="Already has a transaction — replay is idempotent",
                )
            )
            continue

        sender, subject, body = message_parts(event.raw_payload)
        try:
            parsed = parse_email(sender, subject, body)
        except UnparsedEmail as exc:
            results.append(
                ReplayEventResult(
                    event_id=event.id,
                    message_id=event.message_id,
                    action="still_unparsed",
                    reason=str(exc),
                )
            )
            continue

        account = await match_account(db, user_id, parsed.last4_hint)
        if account is None:
            hint = parsed.last4_hint or "none in email"
            results.append(
                ReplayEventResult(
                    event_id=event.id,
                    message_id=event.message_id,
                    action="still_unparsed",
                    reason=f"Parsed by {parsed.parser}, but no unique account matches last4 {hint}",
                    amount_cents=parsed.amount_cents,
                    merchant=parsed.merchant,
                )
            )
            continue

        txn_date = resolve_txn_date(parsed, event.received_at)

        # The parse itself is now known-good, so record the parser that read it either way — an
        # event that turns out to be a CSV duplicate is still no longer a parser mystery.
        event.parser = parsed.parser
        event.parse_version = parsed.parse_version
        event.account_id = account.id

        duplicate_of = find_posted_duplicate(
            parsed.amount_cents, txn_date, await _posted_candidates(db, account.id, txn_date)
        )
        if duplicate_of is not None:
            event.outcome = "duplicate"
            results.append(
                ReplayEventResult(
                    event_id=event.id,
                    message_id=event.message_id,
                    action="duplicate",
                    reason=f"Already reconciled — posted transaction {duplicate_of.id} is this swipe",
                    amount_cents=parsed.amount_cents,
                    merchant=parsed.merchant,
                    txn_date=txn_date,
                )
            )
            continue

        db.add(
            await build_transaction_for_event(
                db,
                user_id,
                account_id=account.id,
                parsed=parsed,
                txn_date=txn_date,
                event_id=event.id,
                now=now,
                llm_client=llm_client,
            )
        )
        event.outcome = "created"
        await db.flush()
        results.append(
            ReplayEventResult(
                event_id=event.id,
                message_id=event.message_id,
                action="filed",
                reason=f"Filed as a pending {parsed.kind} on {account.name}",
                amount_cents=parsed.amount_cents,
                merchant=parsed.merchant,
                txn_date=txn_date,
            )
        )

    if dry_run:
        await db.rollback()
    else:
        await db.commit()

    counts = {action: 0 for action in REPLAY_ACTIONS}
    for r in results:
        counts[r.action] += 1
    return ReplaySummary(
        dry_run=dry_run,
        examined=len(events),
        filed=counts["filed"],
        duplicate=counts["duplicate"],
        still_unparsed=counts["still_unparsed"],
        skipped=counts["skipped"],
        events=results,
    )
