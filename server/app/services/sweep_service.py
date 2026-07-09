"""Sweep pass (CLAUDE.md §5/§10): latched ntfy alerts for silent-failure conditions. Built:
unparsed-email backlog, **missing-bill** (the 'a simulated missing bill pages the phone' exit,
CLAUDE.md Phase 6), **paycheck-late**, and **per-account freshness**. Latch state is persisted
(F11) via `alert_latch_service`, so a redeploy never re-pages an already-open condition. Not yet
built (same latched pattern): paycheck-*short* (band-based, better at ingestion) and auth-hold
expiry (a data-mutation sweep).
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
from app.models.ingest_event import IngestEvent
from app.models.rule import Rule
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
                    await db.commit()  # persist the alert latches (F11)
        except Exception:
            logger.exception("Sweep failed")
        await asyncio.sleep(settings.sweep_interval_minutes * 60)
