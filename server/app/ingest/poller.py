"""The in-process background poller (CLAUDE.md §3/§10 — one container beats a worker sidecar
at this scale, the same call Cookbook and Spotter's schedulers made). Wired into `app/main.py`'s
lifespan; only starts when IMAP settings are present, matching the suite's "absence disables
the feature" pattern (`suite_jwks_url` in Phase 1, `imap_host` here).
"""

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.ingest.imap_client import RealImapFetcher
from app.models.user import User
from app.services.ingest_service import run_ingest_poll

logger = logging.getLogger("magpie.ingest")


async def _resolve_ingest_user_id():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == settings.ingest_user_email))
        user = result.scalar_one_or_none()
        return user.id if user else None


async def poll_loop() -> None:
    """Runs until cancelled. A single failed poll (network blip, a transient IMAP error) is
    logged and the loop keeps going — a paused pipeline is invisible and quietly stale data is
    the failure mode CLAUDE.md calls out as worst, so this must not die on the first hiccup."""
    fetcher = RealImapFetcher(
        host=settings.imap_host,
        port=settings.imap_port,
        user=settings.imap_user,
        password=settings.imap_password,
        label=settings.imap_label,
    )
    while True:
        try:
            user_id = await _resolve_ingest_user_id()
            if user_id is None:
                logger.warning(
                    "Ingest poll skipped: no user found for ingest_user_email=%s",
                    settings.ingest_user_email,
                )
            else:
                async with AsyncSessionLocal() as db:
                    summary = await run_ingest_poll(db, user_id, fetcher)
                    logger.info(
                        "Ingest poll: fetched=%d created=%d duplicate=%d unparsed=%d",
                        summary.fetched,
                        summary.created,
                        summary.duplicate,
                        summary.unparsed,
                    )
        except Exception:
            logger.exception("Ingest poll failed")
        await asyncio.sleep(settings.imap_poll_interval_minutes * 60)
