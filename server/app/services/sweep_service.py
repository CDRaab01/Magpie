"""One sweep pass (CLAUDE.md §5/§10): checks the unparsed-email backlog and publishes a
latched ntfy alert if it just became nonzero. The other named sweeps (auth-hold expiry,
per-account freshness, missing-bill, paycheck deviation) are deliberately not built this
pass — this is the first, simplest, highest-value one: it protects the whole ingestion
pipeline's integrity, the same "silent parser rot is the worst failure mode" principle
`app/ingest/` was built around.
"""

import asyncio
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.ingest_event import IngestEvent
from app.models.user import User
from app.rules.alerts import should_alert
from app.services.ntfy_client import HttpNtfyPublisher, NtfyPublisher

logger = logging.getLogger("magpie.sweeps")


async def count_unparsed_events(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(IngestEvent)
        .where(IngestEvent.user_id == user_id, IngestEvent.outcome == "unparsed")
    )
    return result.scalar_one()


async def run_unparsed_backlog_sweep(
    db: AsyncSession,
    user_id: uuid.UUID,
    publisher: NtfyPublisher,
    *,
    previously_true: bool,
) -> bool:
    """Returns the new `previously_true` for the caller to carry into the next sweep."""
    count = await count_unparsed_events(db, user_id)
    currently_true = count > 0
    if should_alert(currently_true, previously_true):
        await publisher.publish(
            f"{count} email(s) couldn't be parsed and need a look.",
            title="Magpie: unparsed email backlog",
        )
    return currently_true


async def _resolve_sweep_user_id() -> uuid.UUID | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == settings.ingest_user_email))
        user = result.scalar_one_or_none()
        return user.id if user else None


async def sweep_loop() -> None:
    """Runs until cancelled — same "log and keep going" resilience as `app/ingest/poller.py`'s
    poll_loop, and the same rationale: a paused sweep is invisible and a stale unparsed
    backlog is exactly the silent-failure mode this sweep exists to catch."""
    publisher = HttpNtfyPublisher(settings.ntfy_base_url, settings.ntfy_topic)
    previously_true = False
    while True:
        try:
            user_id = await _resolve_sweep_user_id()
            if user_id is None:
                logger.warning(
                    "Sweep skipped: no user found for ingest_user_email=%s",
                    settings.ingest_user_email,
                )
            else:
                async with AsyncSessionLocal() as db:
                    previously_true = await run_unparsed_backlog_sweep(
                        db, user_id, publisher, previously_true=previously_true
                    )
        except Exception:
            logger.exception("Sweep failed")
        await asyncio.sleep(settings.sweep_interval_minutes * 60)
