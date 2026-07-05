from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.ingest.imap_client import RealImapFetcher
from app.models.ingest_event import INGEST_OUTCOMES, IngestEvent
from app.schemas.ingest import IngestEventOut, IngestPollResultOut
from app.security import CurrentUser
from app.services.ingest_service import run_ingest_poll

router = APIRouter(prefix="/ingest", tags=["ingest"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/events", response_model=list[IngestEventOut])
async def list_ingest_events(
    current_user: CurrentUser,
    db: DbSession,
    outcome: Annotated[str | None, Query()] = None,
):
    """The unparsed-backlog operator view (CLAUDE.md §4/§9) — a silently broken parser is the
    pipeline's worst failure mode, so this stays a plain authenticated GET rather than
    something that needs its own admin surface."""
    if outcome is not None and outcome not in INGEST_OUTCOMES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown outcome: {outcome}")
    query = select(IngestEvent).where(IngestEvent.user_id == current_user.id)
    if outcome is not None:
        query = query.where(IngestEvent.outcome == outcome)
    result = await db.execute(query.order_by(IngestEvent.received_at.desc()))
    return list(result.scalars().all())


@router.post("/poll", response_model=IngestPollResultOut)
async def trigger_poll(current_user: CurrentUser, db: DbSession):
    """Manual trigger for the same poll the lifespan task runs on a schedule — useful for
    verifying the pipeline without waiting out `imap_poll_interval_minutes`."""
    if not settings.imap_host or not settings.imap_user or not settings.imap_password:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email ingestion is not configured")
    fetcher = RealImapFetcher(
        host=settings.imap_host,
        port=settings.imap_port,
        user=settings.imap_user,
        password=settings.imap_password,
        label=settings.imap_label,
    )
    summary = await run_ingest_poll(db, current_user.id, fetcher)
    return IngestPollResultOut(
        fetched=summary.fetched,
        created=summary.created,
        duplicate=summary.duplicate,
        unparsed=summary.unparsed,
    )
