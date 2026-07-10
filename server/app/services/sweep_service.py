"""Sweep pass (CLAUDE.md §5/§10): latched ntfy alerts for silent-failure conditions. Built:
unparsed-email backlog, **missing-bill** (the 'a simulated missing bill pages the phone' exit,
CLAUDE.md Phase 6), **paycheck-late**, and **per-account freshness**. Latch state is persisted
(F11) via `alert_latch_service`, so a redeploy never re-pages an already-open condition. Not yet
built (same latched pattern): paycheck-*short* (band-based, better at ingestion). **Auth-hold
expiry is built** (2026-07-10) — the first sweep that mutates data rather than only alerting.
"""

import asyncio
import datetime
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.bill_statement import BillStatement
from app.imports.pending_match import PendingCandidate, find_posted_duplicate
from app.models.ingest_event import IngestEvent
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.rules.recurrence import InvalidCadence, expected_next_date
from app.services.alert_latch_service import latched_should_alert
from app.services.ntfy_client import HttpNtfyPublisher, NtfyPublisher
from app.time_util import owner_local_date

logger = logging.getLogger("magpie.sweeps")

MISSING_BILL_GRACE_DAYS = 3

# #34: deep links carried on each alert's ntfy `Click` header. The Android app registers the
# `magpie://` scheme and routes each host to the screen that lets the owner act on the alert.
# Keep these hosts in sync with the client's MagpieNavHost deep-link routing.
LINK_BILLS = "magpie://bills"
LINK_CASHFLOW = "magpie://cashflow"
LINK_ACCOUNTS = "magpie://accounts"
LINK_HOME = "magpie://home"


async def count_unparsed_events(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(IngestEvent)
        .where(IngestEvent.user_id == user_id, IngestEvent.outcome == "unparsed")
    )
    return result.scalar_one()


async def run_unparsed_backlog_sweep(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """Pages once when the unparsed backlog becomes nonzero (a silent parser break). The latch is
    persisted now (F11), so a redeploy with a still-nonzero backlog doesn't re-page."""
    count = await count_unparsed_events(db, user_id)
    if await latched_should_alert(db, user_id, "unparsed_backlog", count > 0, now):
        await publisher.publish(
            f"{count} email(s) couldn't be parsed and need a look.",
            title="Magpie: unparsed email backlog",
            click=LINK_HOME,
        )


async def run_missing_bill_sweep(
    db: AsyncSession,
    user_id: uuid.UUID,
    publisher: NtfyPublisher,
    *,
    now: datetime.datetime,
    grace_days: int = MISSING_BILL_GRACE_DAYS,
) -> None:
    """A `bill_statement` past its due date by `grace_days` with no matched payment pages the phone
    once (CLAUDE.md's Phase-6 exit criterion). 'Today' is owner-local (F18) so a due date isn't
    judged against a UTC wall clock. One latch per bill, so many overdue bills don't collapse into
    one alert."""
    cutoff = owner_local_date(now, settings.owner_timezone) - datetime.timedelta(days=grace_days)
    result = await db.execute(
        select(BillStatement)
        .join(Account, BillStatement.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            BillStatement.matched_transaction_id.is_(None),
            BillStatement.due_date < cutoff,
        )
    )
    for bill in result.scalars().all():
        if await latched_should_alert(db, user_id, f"missing_bill:{bill.id}", True, now):
            amount = f"${bill.amount_due / 100:,.2f}"
            await publisher.publish(
                f"{bill.biller}: {amount} was due {bill.due_date} and hasn't been paid.",
                title="Magpie: bill missing",
                click=LINK_BILLS,
            )


async def run_paycheck_late_sweep(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """A recurring-income rule whose next expected paycheck is overdue (past the cadence's
    expected date + slack, owner-local) pages once. When the paycheck lands, F6 advances the
    rule's `last_matched_at`, the expected date rolls forward, the condition goes false, and the
    latch clears — so a *later* miss is a fresh episode."""
    today = owner_local_date(now, settings.owner_timezone)
    result = await db.execute(
        select(Rule).where(
            Rule.user_id == user_id,
            Rule.type == "recurring_income",
            Rule.enabled.is_(True),
            Rule.last_matched_at.is_not(None),
        )
    )
    for rule in result.scalars().all():
        cadence = rule.cadence or {}
        try:
            expected = expected_next_date(rule.last_matched_at.date(), cadence)
        except InvalidCadence:
            continue  # a malformed cadence is a rule-editor problem, not a sweep alert
        slack = datetime.timedelta(days=cadence.get("slack_days", 0))
        late = today > expected + slack
        if await latched_should_alert(db, user_id, f"paycheck_late:{rule.id}", late, now):
            await publisher.publish(
                f"Expected income '{rule.matcher}' hasn't arrived — it was due around {expected}.",
                title="Magpie: paycheck late",
                click=LINK_CASHFLOW,
            )


async def run_account_freshness_sweep(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """An account that *had* email-alert activity but none in `account_freshness_days` may have
    had its bank alerts silently turned off (the alert-decay failure mode). Keys off
    `ingest_events` — an account with no prior activity has no baseline and is skipped, so a new
    or manual-only account never false-alarms."""
    threshold = now - datetime.timedelta(days=settings.account_freshness_days)
    accounts = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.active.is_(True))
    )
    for account in accounts.scalars().all():
        latest = await db.execute(
            select(func.max(IngestEvent.received_at)).where(IngestEvent.account_id == account.id)
        )
        latest_at = latest.scalar_one()
        stale = latest_at is not None and latest_at < threshold
        if await latched_should_alert(db, user_id, f"account_stale:{account.id}", stale, now):
            await publisher.publish(
                f"No new alerts from {account.name} ({account.institution}) in "
                f"{settings.account_freshness_days}+ days — its email alerts may have stopped.",
                title="Magpie: account stale",
                click=LINK_ACCOUNTS,
            )


async def run_auth_hold_expiry_sweep(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime.datetime,
    hold_days: int | None = None,
) -> int:
    """Expire pending auth holds that never posted (CLAUDE.md §2). Returns how many were dropped.

    The first sweep that *mutates* data rather than only alerting, so it is deliberately timid:

    * The row is **kept**, not deleted — `status="expired"` plus an audit note in `rule_note`.
      The raw email survives in `ingest_events` either way, so the drop is fully reconstructible.
      Expired rows are excluded from every money query via `COUNTABLE_STATUSES`.
    * A hold with a matching **posted** transaction is never expired: it was reconciled, and the
      "same swipe" question is answered by `find_posted_duplicate` — the same tolerance the CSV
      importer and the parser replay use, so all three agree on what a match is.
    * A **human-confirmed** row is never touched. If the owner said the pending charge is real,
      a sweep does not overrule them (the F3 principle, applied to the clock).
    * A row already paired into a `transfer_group` is never touched: its partner would be left
      dangling half a group.
    * **Card accounts only.** An auth hold is a card concept. A depository "pending" is a real,
      completed debit (US Bank's own alert says "your transaction is complete") that is pending
      only because the CSV has not imported it yet — expiring those would silently delete real
      ACH activity every time the owner went a week without a reconciliation import.

    No ntfy alert: an expiring $1 pre-auth is routine, and paging for routine is how alerting
    dies. The audit note is the record.
    """
    hold_days = settings.auth_hold_days if hold_days is None else hold_days
    cutoff = owner_local_date(now, settings.owner_timezone) - datetime.timedelta(days=hold_days)

    stale = (
        (
            await db.execute(
                select(Transaction)
                .join(Account, Transaction.account_id == Account.id)
                .where(
                    Account.user_id == user_id,
                    Account.type == "card",  # an auth hold is a card concept, never a debit
                    Transaction.status == "pending",
                    Transaction.date < cutoff,
                    Transaction.review_state != "confirmed",
                    Transaction.transfer_group.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    dropped = 0
    for txn in stale:
        window_lo = txn.date - datetime.timedelta(days=3)
        window_hi = txn.date + datetime.timedelta(days=hold_days)
        posted = (
            (
                await db.execute(
                    select(Transaction.id, Transaction.amount, Transaction.date).where(
                        Transaction.account_id == txn.account_id,
                        Transaction.status == "posted",
                        Transaction.split_parent_id.is_(None),
                        Transaction.date >= window_lo,
                        Transaction.date <= window_hi,
                    )
                )
            )
            .tuples()
            .all()
        )
        candidates = [PendingCandidate(str(i), a, d) for i, a, d in posted]
        if find_posted_duplicate(txn.amount, txn.date, candidates, window_days=hold_days):
            continue  # it posted after all; reconciliation owns this row, not the clock

        txn.status = "expired"
        txn.review_state = "auto"
        txn.rule_note = f"auth hold expired: no posted match within {hold_days} days"
        dropped += 1

    if dropped:
        logger.info("Expired %d auth hold(s) for user %s", dropped, user_id)
    return dropped


async def _resolve_sweep_user_id() -> uuid.UUID | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == settings.ingest_user_email))
        user = result.scalar_one_or_none()
        return user.id if user else None


async def sweep_loop() -> None:
    """Runs until cancelled — same "log and keep going" resilience as `app/ingest/poller.py`, and
    the same rationale: a paused sweep is invisible, and a silent stale condition is exactly what
    these sweeps exist to catch."""
    publisher = HttpNtfyPublisher(settings.ntfy_base_url, settings.ntfy_topic)
    while True:
        try:
            user_id = await _resolve_sweep_user_id()
            if user_id is None:
                logger.warning(
                    "Sweep skipped: no user found for ingest_user_email=%s",
                    settings.ingest_user_email,
                )
            else:
                now = datetime.datetime.now(datetime.timezone.utc)
                async with AsyncSessionLocal() as db:
                    await run_unparsed_backlog_sweep(db, user_id, publisher, now=now)
                    await run_missing_bill_sweep(db, user_id, publisher, now=now)
                    await run_paycheck_late_sweep(db, user_id, publisher, now=now)
                    await run_account_freshness_sweep(db, user_id, publisher, now=now)
                    await run_auth_hold_expiry_sweep(db, user_id, now=now)
                    await db.commit()  # persist the alert latches (F11) + any expired holds
        except Exception:
            logger.exception("Sweep failed")
        await asyncio.sleep(settings.sweep_interval_minutes * 60)
