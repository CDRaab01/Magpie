"""Sweep pass (CLAUDE.md §5/§10): latched ntfy alerts for silent-failure conditions. Built:
unparsed-email backlog and **missing-bill** (the 'a simulated missing bill pages the phone' exit,
CLAUDE.md Phase 6). Latch state is persisted (F11) via `alert_latch_service`, so a redeploy never
re-pages an already-open condition. Not yet built (same latched pattern, follow-ups): paycheck
late/short, per-account freshness, auth-hold expiry.
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
from app.models.user import User
from app.services.alert_latch_service import latched_should_alert
from app.services.ntfy_client import HttpNtfyPublisher, NtfyPublisher
from app.time_util import owner_local_date

logger = logging.getLogger("magpie.sweeps")

MISSING_BILL_GRACE_DAYS = 3


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
                    await db.commit()  # persist the alert latches (F11)
        except Exception:
            logger.exception("Sweep failed")
        await asyncio.sleep(settings.sweep_interval_minutes * 60)
