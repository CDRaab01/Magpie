import dataclasses
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.admin import RenormalizeResultOut
from app.security import LedgerUser
from app.services.renormalize_service import renormalize_merchants

router = APIRouter(prefix="/admin", tags=["admin"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/renormalize", response_model=RenormalizeResultOut)
async def renormalize(
    current_user: LedgerUser,
    db: DbSession,
    dry_run: Annotated[bool, Query()] = True,
):
    """Recompute `merchant_norm` from `merchant_raw` with today's normalizer (ROADMAP #25a).

    A derived-data recompute, the `merchant_norm` analogue of `POST /ingest/replay`: no financial
    fact is touched. `dry_run=true` (the default) reports exactly what a real run would change and
    writes nothing. It aborts with 409 rather than commit if any row would normalize to an empty
    key — a blank comparison key silently breaks rule matching, so a normalizer regression fails
    loudly here instead of corrupting the ledger.
    """
    try:
        summary = await renormalize_merchants(db, current_user.id, dry_run=dry_run)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return RenormalizeResultOut(**dataclasses.asdict(summary))
